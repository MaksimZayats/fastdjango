from __future__ import annotations

import ast
import configparser
import re
import shlex
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_has_foundation_base_at,
    class_has_sqlalchemy_mapping_at,
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
                or class_has_sqlalchemy_mapping_at(
                    node,
                    source_path=path,
                    context=context,
                )
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
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        valid_entrypoints = {
            function_name
            for function_name in {"run_migrations_offline", "run_migrations_online"}
            if function_name in functions
            and _env_entrypoint_has_migration_evidence(
                function_name,
                functions=functions,
                bindings=bindings,
            )
        }
        return bool(valid_entrypoints) and any(
            _qualified_call_name(call, bindings, scope=tree) in valid_entrypoints
            for call in _module_executable_calls(tree, bindings=bindings)
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
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    bindings = _import_bindings(tree)
    upgrade = functions.get("upgrade")
    has_alembic_operation = any(
        _qualified_call_name(call, bindings, scope=upgrade).startswith("alembic.op.")
        for call in (
            _calls_in_executable_scope(upgrade, bindings=bindings) if upgrade is not None else ()
        )
    )
    return (
        assigned_revision and {"upgrade", "downgrade"} <= functions.keys() and has_alembic_operation
    )


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
    if _test_is_unconditionally_skipped_or_xfailed(function, bindings=bindings):
        return False
    calls = _calls_in_executable_scope(
        function,
        bindings=bindings,
        exclude_swallowing=True,
    )
    return any(
        _qualified_call_name(call, bindings, scope=function) == "alembic.command.upgrade"
        for call in calls
    ) and any(
        _qualified_call_name(call, bindings, scope=function)
        in {
            "alembic.autogenerate.compare_metadata",
            "alembic.autogenerate.produce_migrations",
            "alembic.command.check",
        }
        for call in calls
    )


def _test_is_unconditionally_skipped_or_xfailed(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    bindings: dict[str, str],
) -> bool:
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        qualified = _qualified_expression_name(target, bindings)
        if qualified == "pytest.mark.skip":
            return True
        if qualified == "pytest.mark.xfail":
            if not isinstance(decorator, ast.Call):
                return True
            condition = _marker_condition(decorator)
            return condition is None or _is_statically_true(condition)
        if (
            qualified == "pytest.mark.skipif"
            and isinstance(decorator, ast.Call)
            and (condition := _marker_condition(decorator)) is not None
            and _is_statically_true(condition)
        ):
            return True
    return False


def _marker_condition(decorator: ast.Call) -> ast.expr | None:
    if decorator.args:
        return decorator.args[0]
    return next(
        (keyword.value for keyword in decorator.keywords if keyword.arg == "condition"),
        None,
    )


def _qualified_expression_name(expression: ast.expr, bindings: dict[str, str]) -> str:
    parts: list[str] = []
    current = expression
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return ast.unparse(expression)
    return ".".join((bindings.get(current.id, current.id), *reversed(parts)))


def _calls_in_executable_scope(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    bindings: dict[str, str] | None = None,
    exclude_swallowing: bool = False,
) -> tuple[ast.Call, ...]:
    return tuple(
        node
        for node in _executable_scope_nodes(
            function,
            bindings=bindings or {},
            exclude_swallowing=exclude_swallowing,
        )
        if isinstance(node, ast.Call)
    )


def _env_entrypoint_has_migration_evidence(
    entrypoint: str,
    *,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    bindings: dict[str, str],
) -> bool:
    pending = [entrypoint]
    visited: set[str] = set()
    calls: list[tuple[ast.Call, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    while pending:
        function_name = pending.pop()
        if function_name in visited:
            continue
        visited.add(function_name)
        function = functions[function_name]
        function_calls = _calls_in_executable_scope(function, bindings=bindings)
        calls.extend((call, function) for call in function_calls)
        for call in function_calls:
            pending.extend(
                referenced
                for referenced in _referenced_local_functions(
                    call,
                    function=function,
                    functions=functions,
                )
                if referenced not in visited
            )

    qualified_calls = {
        _qualified_call_name(call, bindings, scope=function) for call, function in calls
    }
    return {
        "alembic.context.configure",
        "alembic.context.run_migrations",
    } <= qualified_calls


def _referenced_local_functions(
    call: ast.Call,
    *,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
) -> set[str]:
    references: set[str] = set()
    if (
        isinstance(call.func, ast.Name)
        and call.func.id in functions
        and not _function_binds_name(function, call.func.id)
    ):
        references.add(call.func.id)
    if isinstance(call.func, ast.Attribute) and call.func.attr == "run_sync":
        for expression in (*call.args, *(keyword.value for keyword in call.keywords)):
            references.update(
                node.id
                for node in ast.walk(expression)
                if isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Load)
                and node.id in functions
                and not _function_binds_name(function, node.id)
            )
    return references


def _function_binds_name(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    name: str,
) -> bool:
    arguments = (
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    )
    if any(argument.arg == name for argument in arguments):
        return True
    if function.args.vararg is not None and function.args.vararg.arg == name:
        return True
    if function.args.kwarg is not None and function.args.kwarg.arg == name:
        return True

    bound = False

    def visit(node: ast.AST) -> None:
        nonlocal bound
        if bound:
            return
        if node is not function and isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            bound = node.name == name
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == name:
            bound = True
            return
        if isinstance(node, ast.Import):
            bound = any((alias.asname or alias.name.split(".")[0]) == name for alias in node.names)
            return
        if isinstance(node, ast.ImportFrom):
            bound = any((alias.asname or alias.name) == name for alias in node.names)
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(function)
    return bound


def _module_executable_calls(
    tree: ast.Module,
    *,
    bindings: dict[str, str],
) -> tuple[ast.Call, ...]:
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
    return _calls_in_executable_scope(wrapper, bindings=bindings)


def _executable_scope_nodes(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    bindings: dict[str, str],
    exclude_swallowing: bool = False,
) -> tuple[ast.AST, ...]:
    nodes: list[ast.AST] = []

    def visit_block(statements: list[ast.stmt]) -> None:
        for statement in statements:
            visit(statement)
            if _statement_always_terminates(statement, bindings=bindings):
                break

    def visit(node: ast.AST) -> None:
        if node is not function and isinstance(
            node,
            (
                ast.ClassDef,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.Lambda,
                ast.ListComp,
                ast.SetComp,
                ast.DictComp,
                ast.GeneratorExp,
            ),
        ):
            return
        nodes.append(node)
        if node is function:
            visit_block(function.body)
            return
        if isinstance(node, ast.If):
            visit(node.test)
            if _is_statically_false(node.test, bindings=bindings):
                visit_block(node.orelse)
            elif _is_statically_true(node.test):
                visit_block(node.body)
            else:
                visit_block(node.body)
                visit_block(node.orelse)
            return
        if isinstance(node, ast.While):
            visit(node.test)
            if _is_statically_false(node.test, bindings=bindings):
                visit_block(node.orelse)
            else:
                visit_block(node.body)
                visit_block(node.orelse)
            return
        if isinstance(node, (ast.For, ast.AsyncFor)):
            visit(node.target)
            visit(node.iter)
            visit_block(node.body)
            visit_block(node.orelse)
            return
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                visit(item.context_expr)
                if item.optional_vars is not None:
                    visit(item.optional_vars)
            if not (
                exclude_swallowing
                and _with_expects_exception(node, bindings=bindings, scope=function)
            ):
                visit_block(node.body)
            return
        if isinstance(node, ast.Try):
            if not (exclude_swallowing and _try_swallows_exceptions(node)):
                visit_block(node.body)
                for handler in node.handlers:
                    if handler.type is not None:
                        visit(handler.type)
                    visit_block(handler.body)
            visit_block(node.orelse)
            visit_block(node.finalbody)
            return
        if isinstance(node, ast.Match):
            visit(node.subject)
            for case in node.cases:
                if case.guard is not None:
                    visit(case.guard)
                visit_block(case.body)
            return
        for descendant in ast.iter_child_nodes(node):
            if isinstance(descendant, ast.stmt):
                continue
            visit(descendant)

    visit(function)
    return tuple(nodes)


def _statement_always_terminates(statement: ast.stmt, *, bindings: dict[str, str]) -> bool:
    if isinstance(statement, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
        return True
    if isinstance(statement, ast.If):
        if _is_statically_true(statement.test):
            return _block_always_terminates(statement.body, bindings=bindings)
        if _is_statically_false(statement.test, bindings=bindings):
            return _block_always_terminates(statement.orelse, bindings=bindings)
        return (
            bool(statement.orelse)
            and _block_always_terminates(
                statement.body,
                bindings=bindings,
            )
            and _block_always_terminates(statement.orelse, bindings=bindings)
        )
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return _block_always_terminates(statement.body, bindings=bindings)
    return False


def _block_always_terminates(
    statements: list[ast.stmt],
    *,
    bindings: dict[str, str],
) -> bool:
    return any(
        _statement_always_terminates(statement, bindings=bindings) for statement in statements
    )


def _with_expects_exception(
    statement: ast.With | ast.AsyncWith,
    *,
    bindings: dict[str, str],
    scope: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    return any(
        isinstance(item.context_expr, ast.Call)
        and _qualified_call_name(item.context_expr, bindings, scope=scope) == "pytest.raises"
        for item in statement.items
    )


def _try_swallows_exceptions(statement: ast.Try) -> bool:
    return any(not _block_guarantees_raise(handler.body) for handler in statement.handlers)


def _block_guarantees_raise(statements: list[ast.stmt]) -> bool:
    if not statements:
        return False
    last = statements[-1]
    if isinstance(last, ast.Raise):
        return True
    if isinstance(last, ast.If):
        return (
            bool(last.orelse)
            and _block_guarantees_raise(
                last.body,
            )
            and _block_guarantees_raise(last.orelse)
        )
    return False


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
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    bindings.pop(target.id, None)
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            bindings.pop(node.name, None)
    return bindings


def _qualified_call_name(
    call: ast.Call,
    bindings: dict[str, str],
    *,
    scope: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | None = None,
) -> str:
    parts: list[str] = []
    expression: ast.expr = call.func
    while isinstance(expression, ast.Attribute):
        parts.append(expression.attr)
        expression = expression.value
    if not isinstance(expression, ast.Name):
        return ast.unparse(call.func)
    root = (
        expression.id
        if scope is not None and _name_is_shadowed(expression.id, call=call, scope=scope)
        else bindings.get(expression.id, expression.id)
    )
    return ".".join((root, *reversed(parts)))


def _name_is_shadowed(
    name: str,
    *,
    call: ast.Call,
    scope: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        arguments = (
            *scope.args.posonlyargs,
            *scope.args.args,
            *scope.args.kwonlyargs,
        )
        if any(argument.arg == name for argument in arguments):
            return True
        if scope.args.vararg is not None and scope.args.vararg.arg == name:
            return True
        if scope.args.kwarg is not None and scope.args.kwarg.arg == name:
            return True
        return any(
            isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == name
            for node in _executable_scope_nodes(scope, bindings={})
        )
    call_position = (call.lineno, call.col_offset)
    return any(
        isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Store)
        and node.id == name
        and (node.lineno, node.col_offset) < call_position
        for node in _module_scope_nodes(scope)
    )


def _module_scope_nodes(tree: ast.Module) -> tuple[ast.AST, ...]:
    nodes: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        if node is not tree and isinstance(
            node,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        ):
            return
        nodes.append(node)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return tuple(nodes)


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
    if remaining[:1] == ("env",):
        remaining = _strip_env_prefix(remaining[1:])
    if remaining[:2] in {("uv", "run"), ("poetry", "run")}:
        remaining = remaining[2:]
        options_with_values = {
            "--directory",
            "--group",
            "--only-group",
            "--project",
            "--python",
            "--with",
            "--with-requirements",
        }
        while remaining and remaining[0].startswith("-"):
            option = remaining[0].split("=", maxsplit=1)[0]
            width = 2 if option in options_with_values and "=" not in remaining[0] else 1
            remaining = remaining[width:]
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
    return len(remaining) >= 2 and Path(remaining[0]).name == "alembic" and remaining[1] == action


def _strip_env_prefix(tokens: tuple[str, ...]) -> tuple[str, ...]:
    remaining = tokens
    options_with_values = {"-u", "--unset", "-C", "--chdir"}
    while remaining:
        token = remaining[0]
        if token == "--":
            return remaining[1:]
        option = token.split("=", maxsplit=1)[0]
        if option in options_with_values:
            if "=" in token or (option in {"-u", "-C"} and token != option):
                remaining = remaining[1:]
                continue
            if len(remaining) < 2:
                return ()
            remaining = remaining[2:]
            continue
        if token.startswith("-") or ("=" in token and not token.startswith("=")):
            remaining = remaining[1:]
            continue
        return remaining
    return ()


def _is_statically_false(expression: ast.expr, *, bindings: dict[str, str]) -> bool:
    if isinstance(expression, ast.Constant):
        return not bool(expression.value)
    if isinstance(expression, (ast.Name, ast.Attribute)):
        parts: list[str] = []
        current: ast.expr = expression
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            qualified = ".".join((bindings.get(current.id, current.id), *reversed(parts)))
            return qualified in {"TYPE_CHECKING", "typing.TYPE_CHECKING"}
    return False


def _is_statically_true(expression: ast.expr) -> bool:
    return isinstance(expression, ast.Constant) and bool(expression.value)
