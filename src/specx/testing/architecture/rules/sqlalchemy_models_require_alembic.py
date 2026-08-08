from __future__ import annotations

import ast
import configparser
import re
import shlex
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_declares_sqlalchemy_mapping,
    class_definition_base_index,
    class_has_foundation_base_at,
    class_is_statically_abstract_at,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import ArchitectureRuleBase, violation


class SQLAlchemyModelsRequireAlembicRule(ArchitectureRuleBase):
    """Require Alembic configuration, revisions, commands, and tests for concrete models."""

    id: SpecxRuleId = SpecxRuleId.SQLALCHEMY_MODELS_REQUIRE_ALEMBIC
    remediation: str | None = (
        "Add meaningful Alembic config, environment and revision files, `migrate`, "
        "`makemigrations`, and `migration-check` recipes, plus an upgrade-and-drift test."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        if not _has_concrete_model(context):
            return ()
        required_files = _required_files(context)
        missing = sorted(name for name, path in required_files.items() if not path.is_file())
        invalid = sorted(
            name
            for name, path in required_files.items()
            if path.is_file() and not _has_required_markers(name, path.read_text(encoding="utf-8"))
        )
        versions = context.project_root / "migrations" / "versions"
        revisions = (
            tuple(
                path
                for path in versions.iterdir()
                if path.suffix == ".py" and path.name != "__init__.py"
            )
            if versions.is_dir()
            else ()
        )
        if not revisions:
            missing.append("migrations/versions/<revision>.py")
        elif not any(_valid_revision(path.read_text(encoding="utf-8")) for path in revisions):
            invalid.append("migrations/versions/<revision>.py")
        required_targets = {"migrate", "makemigrations", "migration-check"}
        missing_targets = sorted(required_targets - context.makefile_targets())
        invalid_targets = sorted(
            target
            for target in required_targets - set(missing_targets)
            if not _valid_make_recipe(target, context.makefile_target_recipes().get(target, ""))
        )
        if not missing and not invalid and not missing_targets and not invalid_targets:
            return ()
        details: list[str] = []
        if missing:
            details.append(f"missing files {missing}")
        if invalid:
            details.append(f"invalid or placeholder files {invalid}")
        if missing_targets:
            details.append(f"missing Make targets {missing_targets}")
        if invalid_targets:
            details.append(f"Make targets without Alembic recipes {invalid_targets}")
        return (
            violation(
                self.id,
                path=context.project_root,
                message="; ".join(details),
            ),
        )


def _has_concrete_model(context: ArchitectureContext) -> bool:
    definition_index = class_definition_base_index(context)
    for path in context.source_paths():
        if any(
            isinstance(node, ast.ClassDef)
            and (
                not class_is_statically_abstract_at(
                    node,
                    source_path=path,
                    context=context,
                )
                or class_declares_sqlalchemy_mapping(node)
            )
            and class_has_foundation_base_at(
                node,
                "BaseSQLAlchemyModel",
                source_path=path,
                context=context,
                definition_index=definition_index,
            )
            for node in ast.walk(context.tree(path))
        ):
            return True
    return False


def _required_files(context: ArchitectureContext) -> dict[str, Path]:
    return {
        "alembic.ini": context.project_root / "alembic.ini",
        "migrations/env.py": context.project_root / "migrations" / "env.py",
        "migrations/script.py.mako": context.project_root / "migrations" / "script.py.mako",
        "tests/integration/migrations/test_migrations.py": (
            context.project_root / "tests" / "integration" / "migrations" / "test_migrations.py"
        ),
    }


def _has_required_markers(name: str, text: str) -> bool:
    if name == "alembic.ini":
        parser = configparser.ConfigParser()
        try:
            parser.read_string(text)
        except configparser.Error:
            return False
        return parser.has_section("alembic") and bool(
            parser.get("alembic", "script_location", fallback="").strip()
        )
    if name == "migrations/script.py.mako":
        executable = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        return all(
            re.search(rf"^\s*def\s+{function}\s*\(", executable, re.MULTILINE)
            for function in ("upgrade", "downgrade")
        )
    tree = _parse_python(text)
    if tree is None:
        return False
    if name == "migrations/env.py":
        bindings = _import_bindings(tree)
        valid_entrypoints = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {"run_migrations_offline", "run_migrations_online"}
            and any(
                _qualified_call_name(call, bindings) == "alembic.context.configure"
                for call in _calls_in_executable_scope(node)
            )
            and any(
                _qualified_call_name(call, bindings) == "alembic.context.run_migrations"
                for call in _calls_in_executable_scope(node)
            )
        }
        return bool(valid_entrypoints) and any(
            _qualified_call_name(call, bindings) in valid_entrypoints
            for call in _module_executable_calls(tree)
        )
    bindings = _import_bindings(tree)
    return any(
        _test_function_has_migration_evidence(node, bindings=bindings)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )


def _valid_revision(text: str) -> bool:
    tree = _parse_python(text)
    if tree is None:
        return False
    assigned_revision = any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "revision"
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        and bool(node.value.value)
        for node in tree.body
    )
    functions = {
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    bindings = _import_bindings(tree)
    migration_functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"upgrade", "downgrade"}
    ]
    has_alembic_operation = any(
        _qualified_call_name(call, bindings).startswith("alembic.op.")
        for function in migration_functions
        for call in _calls_in_executable_scope(function)
    )
    return assigned_revision and {"upgrade", "downgrade"} <= functions and has_alembic_operation


def _valid_make_recipe(target: str, recipe: str) -> bool:
    required_fragments = {
        "migrate": ("alembic", "upgrade"),
        "makemigrations": ("alembic", "revision"),
        "migration-check": ("alembic", "check"),
    }
    commands = [
        _shell_tokens(line.lstrip("\t@- "))
        for line in recipe.splitlines()
        if line.startswith("\t") and not line.lstrip("\t@- ").startswith("#")
    ]
    return any(
        _invokes_alembic(command, action=required_fragments[target][1]) for command in commands
    )


def _parse_python(text: str) -> ast.Module | None:
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def _test_function_has_migration_evidence(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    bindings: dict[str, str],
) -> bool:
    calls = _calls_in_executable_scope(function)
    return any(
        _qualified_call_name(call, bindings) == "alembic.command.upgrade" for call in calls
    ) and any(
        _qualified_call_name(call, bindings)
        in {
            "alembic.autogenerate.compare_metadata",
            "alembic.autogenerate.produce_migrations",
            "alembic.command.check",
        }
        for call in calls
    )


def _calls_in_executable_scope(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[ast.Call, ...]:
    return tuple(node for node in _executable_scope_nodes(function) if isinstance(node, ast.Call))


def _module_executable_calls(tree: ast.Module) -> tuple[ast.Call, ...]:
    wrapper = ast.FunctionDef(
        name="<module>",
        args=ast.arguments(
            posonlyargs=[],
            args=[],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=tree.body,
        decorator_list=[],
    )
    return _calls_in_executable_scope(wrapper)


def _executable_scope_nodes(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[ast.AST, ...]:
    nodes: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        if node is not function and isinstance(
            node,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        ):
            return
        nodes.append(node)
        if isinstance(node, ast.If) and _is_statically_false(node.test):
            for statement in node.orelse:
                visit(statement)
            return
        if isinstance(node, ast.If) and _is_statically_true(node.test):
            for statement in node.body:
                visit(statement)
            return
        for descendant in ast.iter_child_nodes(node):
            visit(descendant)

    visit(function)
    return tuple(nodes)


def _import_bindings(tree: ast.Module) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return bindings


def _qualified_call_name(call: ast.Call, bindings: dict[str, str]) -> str:
    parts: list[str] = []
    expression: ast.expr = call.func
    while isinstance(expression, ast.Attribute):
        parts.append(expression.attr)
        expression = expression.value
    if not isinstance(expression, ast.Name):
        return ast.unparse(call.func)
    root = bindings.get(expression.id, expression.id)
    return ".".join((root, *reversed(parts)))


def _shell_tokens(command: str) -> tuple[str, ...]:
    try:
        return tuple(shlex.split(command, comments=True, posix=True))
    except ValueError:
        return ()


def _invokes_alembic(tokens: tuple[str, ...], *, action: str) -> bool:
    if not tokens:
        return False
    index = 0
    while index < len(tokens) and "=" in tokens[index] and not tokens[index].startswith("="):
        index += 1
    remaining = tokens[index:]
    if remaining[:2] in {("uv", "run"), ("poetry", "run")}:
        remaining = remaining[2:]
    executable = Path(remaining[0]).name if remaining else ""
    if (
        len(remaining) >= 3
        and executable.startswith("python")
        and remaining[1:3]
        == (
            "-m",
            "alembic",
        )
    ):
        remaining = remaining[2:]
    return len(remaining) >= 2 and remaining[0] == "alembic" and remaining[1] == action


def _is_statically_false(expression: ast.expr) -> bool:
    return isinstance(expression, ast.Constant) and expression.value is False


def _is_statically_true(expression: ast.expr) -> bool:
    return isinstance(expression, ast.Constant) and expression.value is True
