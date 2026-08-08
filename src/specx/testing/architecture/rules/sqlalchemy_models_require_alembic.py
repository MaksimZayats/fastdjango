from __future__ import annotations

import ast
import configparser
import re
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
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
            and not class_is_statically_abstract_at(
                node,
                source_path=path,
                context=context,
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
        return _has_call(tree, "context.configure") and any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("run_migrations")
            for node in ast.walk(tree)
        )
    return (
        any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
            for node in ast.walk(tree)
        )
        and any(_call_name(call).endswith("upgrade") for call in _calls(tree))
        and any(
            any(
                marker in _call_name(call)
                for marker in ("compare_metadata", "produce_migrations", "check", "drift")
            )
            for call in _calls(tree)
        )
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
    return assigned_revision and {"upgrade", "downgrade"} <= functions


def _valid_make_recipe(target: str, recipe: str) -> bool:
    required_fragments = {
        "migrate": ("alembic", "upgrade"),
        "makemigrations": ("alembic", "revision"),
        "migration-check": ("alembic", "check"),
    }
    commands = [
        line.lstrip("\t@- ")
        for line in recipe.splitlines()
        if line.startswith("\t") and not line.lstrip("\t@- ").startswith("#")
    ]
    return any(
        all(fragment in command for fragment in required_fragments[target]) for command in commands
    )


def _parse_python(text: str) -> ast.Module | None:
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def _calls(tree: ast.Module) -> tuple[ast.Call, ...]:
    return tuple(node for node in ast.walk(tree) if isinstance(node, ast.Call))


def _call_name(call: ast.Call) -> str:
    return ast.unparse(call.func)


def _has_call(tree: ast.Module, name: str) -> bool:
    return any(_call_name(call).endswith(name) for call in _calls(tree))
