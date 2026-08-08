from __future__ import annotations

import ast
import configparser
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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

_CONFIGURE_EVIDENCE = "alembic.context.configure"
_RUN_MIGRATIONS_EVIDENCE = "alembic.context.run_migrations"
_UPGRADE_EVIDENCE = "alembic.command.upgrade"
_DRIFT_EVIDENCE = frozenset(
    {
        "alembic.autogenerate.compare_metadata",
        "alembic.autogenerate.produce_migrations",
        "alembic.command.check",
    }
)
_REVISION_EFFECT_METHODS = frozenset(
    {
        "add_column",
        "alter_column",
        "bulk_insert",
        "create_check_constraint",
        "create_exclude_constraint",
        "create_foreign_key",
        "create_index",
        "create_primary_key",
        "create_table",
        "create_table_comment",
        "create_unique_constraint",
        "drop_column",
        "drop_constraint",
        "drop_index",
        "drop_table",
        "drop_table_comment",
        "execute",
        "rename_table",
    }
)
_FlowTermination = Literal["next", "return", "raise", "break", "continue"]


@dataclass(frozen=True, slots=True)
class _EvidencePath:
    evidence: frozenset[str]
    termination: _FlowTermination = "next"


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
                (
                    (
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
                )
                or (
                    class_has_sqlalchemy_mapping_at(
                        node,
                        source_path=path,
                        context=context,
                    )
                    and class_has_foundation_base_at(
                        node,
                        "sqlalchemy.orm.DeclarativeBase",
                        source_path=path,
                        context=context,
                        definition_index=definition_index,
                    )
                )
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
        return bool(valid_entrypoints) and _module_invokes_entrypoint_at_import(
            tree,
            entrypoints=valid_entrypoints,
            bindings=bindings,
        )
    bindings = _import_bindings(tree)
    if _pytestmark_body_is_disabled(tree.body, bindings=bindings):
        return False
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
            and _test_function_has_migration_evidence(node, bindings=bindings)
        ):
            return True
        if not isinstance(node, ast.ClassDef) or not node.name.startswith("Test"):
            continue
        if _pytest_decorators_disable(node.decorator_list, bindings=bindings):
            continue
        if _pytestmark_body_is_disabled(node.body, bindings=bindings):
            continue
        if any(
            isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            and child.name.startswith("test_")
            and _test_function_has_migration_evidence(child, bindings=bindings)
            for child in node.body
        ):
            return True
    return False


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
    assigned_down_revision = any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "down_revision"
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
        and node.value is not None
        for node in tree.body
    )
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    bindings = _import_bindings(tree)
    upgrade = functions.get("upgrade")
    passing_paths = (
        _passing_evidence_paths(
            upgrade,
            bindings=bindings,
            functions=functions,
        )
        if upgrade is not None
        else ()
    )
    has_alembic_operation = bool(passing_paths) and all(
        any(
            evidence.rsplit(".", maxsplit=1)[-1] in _REVISION_EFFECT_METHODS
            and evidence.startswith("alembic.op.")
            for evidence in path
        )
        for path in passing_paths
    )
    return (
        assigned_revision
        and assigned_down_revision
        and {"upgrade", "downgrade"} <= functions.keys()
        and has_alembic_operation
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
    passing_paths = _passing_evidence_paths(
        function,
        bindings=bindings,
    )
    return bool(passing_paths) and all(
        _UPGRADE_EVIDENCE in path and bool(path & _DRIFT_EVIDENCE) for path in passing_paths
    )


def _test_is_unconditionally_skipped_or_xfailed(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    bindings: dict[str, str],
) -> bool:
    return _pytest_decorators_disable(function.decorator_list, bindings=bindings)


def _pytest_decorators_disable(
    decorators: list[ast.expr],
    *,
    bindings: dict[str, str],
) -> bool:
    return any(_pytest_marker_disables(decorator, bindings=bindings) for decorator in decorators)


def _pytestmark_body_is_disabled(
    body: list[ast.stmt],
    *,
    bindings: dict[str, str],
) -> bool:
    return any(
        isinstance(statement, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "pytestmark"
            for target in (
                statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            )
        )
        and statement.value is not None
        and _pytestmark_expression_disables(statement.value, bindings=bindings)
        for statement in body
    )


def _pytestmark_expression_disables(
    expression: ast.expr,
    *,
    bindings: dict[str, str],
) -> bool:
    if isinstance(expression, (ast.List, ast.Tuple, ast.Set)):
        return any(
            _pytestmark_expression_disables(element, bindings=bindings)
            for element in expression.elts
        )
    return _pytest_marker_disables(expression, bindings=bindings)


def _pytest_marker_disables(
    decorator: ast.expr,
    *,
    bindings: dict[str, str],
) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    qualified = _qualified_expression_name(target, bindings)
    if qualified == "pytest.mark.skip":
        return True
    if qualified == "pytest.mark.xfail":
        if not isinstance(decorator, ast.Call):
            return True
        condition = _marker_condition(decorator)
        return condition is None or _is_statically_true(condition)
    return bool(
        qualified == "pytest.mark.skipif"
        and isinstance(decorator, ast.Call)
        and (condition := _marker_condition(decorator)) is not None
        and _is_statically_true(condition)
    )


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


def _passing_evidence_paths(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    bindings: dict[str, str],
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] | None = None,
    visited: frozenset[str] = frozenset(),
) -> tuple[frozenset[str], ...]:
    function_key = function.name
    if function_key in visited:
        return (frozenset(),)
    paths = _flow_block(
        function.body,
        (_EvidencePath(frozenset()),),
        scope=function,
        bindings=bindings,
        functions=functions or {},
        visited=visited | {function_key},
        batch_aliases=_batch_operation_aliases(function, bindings=bindings),
    )
    return tuple(path.evidence for path in paths if path.termination in {"next", "return"})


def _flow_block(
    statements: list[ast.stmt],
    paths: tuple[_EvidencePath, ...],
    *,
    scope: ast.FunctionDef | ast.AsyncFunctionDef,
    bindings: dict[str, str],
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    visited: frozenset[str],
    batch_aliases: frozenset[str],
) -> tuple[_EvidencePath, ...]:
    current = paths
    for statement in statements:
        continuing = tuple(path for path in current if path.termination == "next")
        terminal = tuple(path for path in current if path.termination != "next")
        if not continuing:
            break
        current = _deduplicate_paths(
            (
                *terminal,
                *_flow_statement(
                    statement,
                    continuing,
                    scope=scope,
                    bindings=bindings,
                    functions=functions,
                    visited=visited,
                    batch_aliases=batch_aliases,
                ),
            )
        )
    return current


def _flow_statement(
    statement: ast.stmt,
    paths: tuple[_EvidencePath, ...],
    *,
    scope: ast.FunctionDef | ast.AsyncFunctionDef,
    bindings: dict[str, str],
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    visited: frozenset[str],
    batch_aliases: frozenset[str],
) -> tuple[_EvidencePath, ...]:
    if isinstance(statement, ast.Return):
        return _terminate_paths(
            _add_expression_evidence(
                paths,
                statement.value,
                scope=scope,
                bindings=bindings,
                functions=functions,
                visited=visited,
                batch_aliases=batch_aliases,
            ),
            "return",
        )
    if isinstance(statement, ast.Raise):
        return _terminate_paths(
            _add_expression_evidence(
                paths,
                statement.exc,
                scope=scope,
                bindings=bindings,
                functions=functions,
                visited=visited,
                batch_aliases=batch_aliases,
            ),
            "raise",
        )
    if isinstance(statement, ast.Break):
        return _terminate_paths(paths, "break")
    if isinstance(statement, ast.Continue):
        return _terminate_paths(paths, "continue")
    if isinstance(statement, ast.If):
        tested = _add_expression_evidence(
            paths,
            statement.test,
            scope=scope,
            bindings=bindings,
            functions=functions,
            visited=visited,
            batch_aliases=batch_aliases,
        )
        truth = _static_truth(statement.test, bindings=bindings)
        branches = (
            (statement.body,)
            if truth is True
            else (statement.orelse,)
            if truth is False
            else (statement.body, statement.orelse)
        )
        return _deduplicate_paths(
            tuple(
                path
                for branch in branches
                for path in _flow_block(
                    branch,
                    tested,
                    scope=scope,
                    bindings=bindings,
                    functions=functions,
                    visited=visited,
                    batch_aliases=batch_aliases,
                )
            )
        )
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        entered = paths
        for item in statement.items:
            entered = _add_expression_evidence(
                entered,
                item.context_expr,
                scope=scope,
                bindings=bindings,
                functions=functions,
                visited=visited,
                batch_aliases=batch_aliases,
            )
        if _with_swallows_exceptions(statement, bindings=bindings, scope=scope):
            return entered
        return _flow_block(
            statement.body,
            entered,
            scope=scope,
            bindings=bindings,
            functions=functions,
            visited=visited,
            batch_aliases=batch_aliases,
        )
    if isinstance(statement, ast.Try):
        return _flow_try(
            statement,
            paths,
            scope=scope,
            bindings=bindings,
            functions=functions,
            visited=visited,
            batch_aliases=batch_aliases,
        )
    if isinstance(statement, (ast.For, ast.AsyncFor)):
        iterated = _add_expression_evidence(
            paths,
            statement.iter,
            scope=scope,
            bindings=bindings,
            functions=functions,
            visited=visited,
            batch_aliases=batch_aliases,
        )
        body_paths = _flow_block(
            statement.body,
            iterated,
            scope=scope,
            bindings=bindings,
            functions=functions,
            visited=visited,
            batch_aliases=batch_aliases,
        )
        breaks = tuple(
            _EvidencePath(path.evidence) for path in body_paths if path.termination == "break"
        )
        completes = tuple(
            _EvidencePath(path.evidence)
            for path in body_paths
            if path.termination in {"next", "continue"}
        )
        terminal = tuple(path for path in body_paths if path.termination in {"return", "raise"})
        else_inputs = _deduplicate_paths((*iterated, *completes))
        else_paths = _flow_block(
            statement.orelse,
            else_inputs,
            scope=scope,
            bindings=bindings,
            functions=functions,
            visited=visited,
            batch_aliases=batch_aliases,
        )
        return _deduplicate_paths((*terminal, *breaks, *else_paths))
    if isinstance(statement, ast.While):
        tested = _add_expression_evidence(
            paths,
            statement.test,
            scope=scope,
            bindings=bindings,
            functions=functions,
            visited=visited,
            batch_aliases=batch_aliases,
        )
        truth = _static_truth(statement.test, bindings=bindings)
        if truth is False:
            return _flow_block(
                statement.orelse,
                tested,
                scope=scope,
                bindings=bindings,
                functions=functions,
                visited=visited,
                batch_aliases=batch_aliases,
            )
        body_paths = _flow_block(
            statement.body,
            tested,
            scope=scope,
            bindings=bindings,
            functions=functions,
            visited=visited,
            batch_aliases=batch_aliases,
        )
        breaks = tuple(
            _EvidencePath(path.evidence) for path in body_paths if path.termination == "break"
        )
        terminal = tuple(path for path in body_paths if path.termination in {"return", "raise"})
        if truth is True:
            return _deduplicate_paths((*terminal, *breaks))
        completes = tuple(
            _EvidencePath(path.evidence)
            for path in body_paths
            if path.termination in {"next", "continue"}
        )
        else_paths = _flow_block(
            statement.orelse,
            _deduplicate_paths((*tested, *completes)),
            scope=scope,
            bindings=bindings,
            functions=functions,
            visited=visited,
            batch_aliases=batch_aliases,
        )
        return _deduplicate_paths((*terminal, *breaks, *else_paths))
    if isinstance(statement, ast.Match):
        matched = _add_expression_evidence(
            paths,
            statement.subject,
            scope=scope,
            bindings=bindings,
            functions=functions,
            visited=visited,
            batch_aliases=batch_aliases,
        )
        case_paths = tuple(
            path
            for case in statement.cases
            for path in _flow_block(
                case.body,
                _add_expression_evidence(
                    matched,
                    case.guard,
                    scope=scope,
                    bindings=bindings,
                    functions=functions,
                    visited=visited,
                    batch_aliases=batch_aliases,
                ),
                scope=scope,
                bindings=bindings,
                functions=functions,
                visited=visited,
                batch_aliases=batch_aliases,
            )
        )
        exhaustive = any(
            isinstance(case.pattern, ast.MatchAs)
            and case.pattern.pattern is None
            and case.guard is None
            for case in statement.cases
        )
        return _deduplicate_paths((*case_paths, *(() if exhaustive else matched)))
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return paths
    return _add_expression_evidence(
        paths,
        statement,
        scope=scope,
        bindings=bindings,
        functions=functions,
        visited=visited,
        batch_aliases=batch_aliases,
    )


def _flow_try(
    statement: ast.Try,
    paths: tuple[_EvidencePath, ...],
    *,
    scope: ast.FunctionDef | ast.AsyncFunctionDef,
    bindings: dict[str, str],
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    visited: frozenset[str],
    batch_aliases: frozenset[str],
) -> tuple[_EvidencePath, ...]:
    body_paths = _flow_block(
        statement.body,
        paths,
        scope=scope,
        bindings=bindings,
        functions=functions,
        visited=visited,
        batch_aliases=batch_aliases,
    )
    normal_body = tuple(path for path in body_paths if path.termination == "next")
    non_normal_body = tuple(path for path in body_paths if path.termination != "next")
    normal_paths = _flow_block(
        statement.orelse,
        normal_body,
        scope=scope,
        bindings=bindings,
        functions=functions,
        visited=visited,
        batch_aliases=batch_aliases,
    )
    handler_paths = tuple(
        path
        for handler in statement.handlers
        for path in _flow_block(
            handler.body,
            paths,
            scope=scope,
            bindings=bindings,
            functions=functions,
            visited=visited,
            batch_aliases=batch_aliases,
        )
    )
    carried = _deduplicate_paths(
        (
            *normal_paths,
            *handler_paths,
            *(
                path
                for path in non_normal_body
                if path.termination != "raise" or not statement.handlers
            ),
        )
    )
    if not statement.finalbody:
        return carried
    finalized: list[_EvidencePath] = []
    for path in carried:
        final_paths = _flow_block(
            statement.finalbody,
            (_EvidencePath(path.evidence),),
            scope=scope,
            bindings=bindings,
            functions=functions,
            visited=visited,
            batch_aliases=batch_aliases,
        )
        finalized.extend(
            _EvidencePath(
                final_path.evidence,
                path.termination if final_path.termination == "next" else final_path.termination,
            )
            for final_path in final_paths
        )
    return _deduplicate_paths(tuple(finalized))


def _add_expression_evidence(
    paths: tuple[_EvidencePath, ...],
    expression: ast.AST | None,
    *,
    scope: ast.FunctionDef | ast.AsyncFunctionDef,
    bindings: dict[str, str],
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    visited: frozenset[str],
    batch_aliases: frozenset[str],
) -> tuple[_EvidencePath, ...]:
    current = paths
    for call in _expression_calls(expression):
        call_name = _call_evidence_name(
            call,
            bindings=bindings,
            scope=scope,
            batch_aliases=batch_aliases,
        )
        current = tuple(
            _EvidencePath(path.evidence | {call_name}, path.termination) for path in current
        )
        for helper_name in _referenced_local_functions(
            call,
            function=scope,
            functions=functions,
        ):
            if helper_name in visited:
                continue
            helper_paths = _passing_evidence_paths(
                functions[helper_name],
                bindings=bindings,
                functions=functions,
                visited=visited,
            )
            if not helper_paths:
                current = ()
                break
            current = _deduplicate_paths(
                tuple(
                    _EvidencePath(path.evidence | helper_evidence, path.termination)
                    for path in current
                    for helper_evidence in helper_paths
                )
            )
    return current


def _expression_calls(expression: ast.AST | None) -> tuple[ast.Call, ...]:
    if expression is None:
        return ()
    calls: list[ast.Call] = []

    def visit(node: ast.AST) -> None:
        if node is not expression and isinstance(
            node,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        ):
            return
        if isinstance(node, ast.Call):
            calls.append(node)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                continue
            visit(child)

    visit(expression)
    return tuple(calls)


def _call_evidence_name(
    call: ast.Call,
    *,
    bindings: dict[str, str],
    scope: ast.FunctionDef | ast.AsyncFunctionDef,
    batch_aliases: frozenset[str],
) -> str:
    if (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id in batch_aliases
    ):
        return f"alembic.op.{call.func.attr}"
    return _qualified_call_name(call, bindings, scope=scope)


def _batch_operation_aliases(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    bindings: dict[str, str],
) -> frozenset[str]:
    aliases: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        for item in node.items:
            if (
                isinstance(item.context_expr, ast.Call)
                and _qualified_call_name(item.context_expr, bindings, scope=function)
                == "alembic.op.batch_alter_table"
                and isinstance(item.optional_vars, ast.Name)
            ):
                aliases.add(item.optional_vars.id)
    return frozenset(aliases)


def _terminate_paths(
    paths: tuple[_EvidencePath, ...],
    termination: _FlowTermination,
) -> tuple[_EvidencePath, ...]:
    return tuple(_EvidencePath(path.evidence, termination) for path in paths)


def _deduplicate_paths(paths: tuple[_EvidencePath, ...]) -> tuple[_EvidencePath, ...]:
    return tuple(dict.fromkeys(paths))


def _static_truth(expression: ast.expr, *, bindings: dict[str, str]) -> bool | None:
    if _is_statically_true(expression):
        return True
    if _is_statically_false(expression, bindings=bindings):
        return False
    return None


def _with_swallows_exceptions(
    statement: ast.With | ast.AsyncWith,
    *,
    bindings: dict[str, str],
    scope: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    swallowing_contexts = {"contextlib.suppress", "pytest.raises"}
    return any(
        isinstance(item.context_expr, ast.Call)
        and _qualified_call_name(item.context_expr, bindings, scope=scope) in swallowing_contexts
        for item in statement.items
    )


def _env_entrypoint_has_migration_evidence(
    entrypoint: str,
    *,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    bindings: dict[str, str],
) -> bool:
    passing_paths = _passing_evidence_paths(
        functions[entrypoint],
        bindings=bindings,
        functions=functions,
    )
    required = {_CONFIGURE_EVIDENCE, _RUN_MIGRATIONS_EVIDENCE}
    return bool(passing_paths) and all(required <= path for path in passing_paths)


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


def _module_invokes_entrypoint_at_import(
    tree: ast.Module,
    *,
    entrypoints: set[str],
    bindings: dict[str, str],
) -> bool:
    return any(
        _qualified_call_name(call, bindings, scope=tree) in entrypoints
        and _node_reachable_at_module_import(tree.body, call, bindings=bindings)
        for call in _module_executable_calls(tree, bindings=bindings)
    )


def _node_reachable_at_module_import(
    statements: list[ast.stmt],
    target: ast.AST,
    *,
    bindings: dict[str, str],
) -> bool:
    for statement in statements:
        if not any(node is target for node in ast.walk(statement)):
            if _statement_always_terminates(statement, bindings=bindings):
                return False
            continue
        if isinstance(statement, ast.If):
            if any(node is target for node in ast.walk(statement.test)):
                return True
            truth = _module_import_truth(statement.test, bindings=bindings)
            branches = (
                (statement.body,)
                if truth is True
                else (statement.orelse,)
                if truth is False
                else (statement.body, statement.orelse)
            )
            return any(
                _node_reachable_at_module_import(branch, target, bindings=bindings)
                for branch in branches
            )
        if isinstance(statement, (ast.With, ast.AsyncWith)):
            return _node_reachable_at_module_import(
                statement.body,
                target,
                bindings=bindings,
            )
        if isinstance(statement, ast.Try):
            return any(
                _node_reachable_at_module_import(block, target, bindings=bindings)
                for block in (
                    statement.body,
                    *(handler.body for handler in statement.handlers),
                    statement.orelse,
                    statement.finalbody,
                )
            )
        if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
            return any(
                _node_reachable_at_module_import(block, target, bindings=bindings)
                for block in (statement.body, statement.orelse)
            )
        if isinstance(statement, ast.Match):
            return any(
                _node_reachable_at_module_import(case.body, target, bindings=bindings)
                for case in statement.cases
            )
        return True
    return False


def _module_import_truth(
    expression: ast.expr,
    *,
    bindings: dict[str, str],
) -> bool | None:
    if (
        isinstance(expression, ast.Compare)
        and len(expression.ops) == 1
        and len(expression.comparators) == 1
    ):
        left, right = expression.left, expression.comparators[0]
        values = (left, right)
        if any(isinstance(value, ast.Name) and value.id == "__name__" for value in values):
            literal = next(
                (
                    value.value
                    for value in values
                    if isinstance(value, ast.Constant) and isinstance(value.value, str)
                ),
                None,
            )
            if literal == "__main__":
                if isinstance(expression.ops[0], ast.Eq):
                    return False
                if isinstance(expression.ops[0], ast.NotEq):
                    return True
    return _static_truth(expression, bindings=bindings)


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
    if isinstance(statement, ast.Try):
        if _block_always_terminates(statement.finalbody, bindings=bindings):
            return True
        handlers_terminate = all(
            _block_always_terminates(handler.body, bindings=bindings)
            for handler in statement.handlers
        )
        normal_terminates = _block_always_terminates(
            statement.body,
            bindings=bindings,
        ) or (
            bool(statement.orelse) and _block_always_terminates(statement.orelse, bindings=bindings)
        )
        return normal_terminates and handlers_terminate
    if isinstance(statement, ast.Match):
        exhaustive = any(
            isinstance(case.pattern, ast.MatchAs)
            and case.pattern.pattern is None
            and case.guard is None
            for case in statement.cases
        )
        return exhaustive and all(
            _block_always_terminates(case.body, bindings=bindings) for case in statement.cases
        )
    if isinstance(statement, ast.While) and _is_statically_true(statement.test):
        return not _contains_loop_break(statement.body)
    return False


def _block_always_terminates(
    statements: list[ast.stmt],
    *,
    bindings: dict[str, str],
) -> bool:
    return any(
        _statement_always_terminates(statement, bindings=bindings) for statement in statements
    )


def _contains_loop_break(statements: list[ast.stmt]) -> bool:
    found = False

    def visit(node: ast.AST) -> None:
        nonlocal found
        if found:
            return
        if isinstance(node, ast.Break):
            found = True
            return
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    for statement in statements:
        visit(statement)
    return found


def _with_expects_exception(
    statement: ast.With | ast.AsyncWith,
    *,
    bindings: dict[str, str],
    scope: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    return any(
        isinstance(item.context_expr, ast.Call)
        and _qualified_call_name(item.context_expr, bindings, scope=scope)
        in {"contextlib.suppress", "pytest.raises"}
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
