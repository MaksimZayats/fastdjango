from __future__ import annotations

import ast
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_has_foundation_base_at,
    class_is_statically_abstract_at,
    qualified_class_name,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    flat_test_path_for_source_path,
    violation,
)


class TestsCoreBehaviorResolvesFromContainerRule(ArchitectureRuleBase):
    """Require mirrored core-behavior tests to resolve every concrete target from DIWire."""

    id: SpecxRuleId = SpecxRuleId.TESTS_CORE_BEHAVIOR_RESOLVES_FROM_CONTAINER
    remediation: str | None = (
        "Add a test using the native `container` fixture and call "
        "`container.resolve(Target)` for every concrete behavior in the mirrored module."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        definition_index = class_definition_base_index(context)
        target_bases = {
            "BaseUseCase",
            "BaseCapability",
            "BasePureService",
            "BaseReadService",
            "BaseEffectService",
        }
        unit_root = context.project_root / "tests" / "unit"
        native_container_available = _has_native_container_fixture(context, unit_root=unit_root)
        findings: list[SpecxArchitectureViolation] = []
        for source_path in context.source_paths():
            targets = [
                node
                for node in ast.walk(context.tree(source_path))
                if isinstance(node, ast.ClassDef)
                and not class_is_statically_abstract_at(
                    node,
                    source_path=source_path,
                    context=context,
                )
                and any(
                    class_has_foundation_base_at(
                        node,
                        base,
                        source_path=source_path,
                        context=context,
                        definition_index=definition_index,
                    )
                    for base in target_bases
                )
            ]
            if not targets:
                continue
            test_path = flat_test_path_for_source_path(
                source_path,
                test_root=unit_root,
                src_root=context.src_root,
            )
            test_tree = context.tree(test_path) if test_path in context.ast_project.files else None
            for target in targets:
                if (
                    test_tree is None
                    or not native_container_available
                    or _defines_container_fixture(
                        test_tree,
                        path=test_path,
                        context=context,
                    )
                    or _has_shadowing_container_fixture(
                        context,
                        test_path=test_path,
                        unit_root=unit_root,
                    )
                    or not _target_resolved_by_container(
                        test_tree,
                        qualified_class_name(
                            target,
                            source_path=source_path,
                            context=context,
                        ),
                        test_path=test_path,
                        context=context,
                    )
                ):
                    findings.append(
                        violation(
                            self.id,
                            path=test_path,
                            symbol=target.name,
                            message=(
                                f"mirrored unit test does not resolve {target.name} from container"
                            ),
                        )
                    )
        return tuple(findings)


def _target_resolved_by_container(
    tree: ast.Module,
    target_qualified_name: str,
    *,
    test_path: Path,
    context: ArchitectureContext,
) -> bool:
    module_disabled = _pytestmark_disables_tests(
        tree.body,
        path=test_path,
        context=context,
    )
    for function, owner_classes in _test_functions_with_owners(tree):
        arguments = (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)
        if (
            not any(argument.arg == "container" for argument in arguments)
            or _container_is_defaulted(function)
            or _container_is_parametrized(function)
            or module_disabled
            or _test_is_disabled(
                function,
                owner_classes=owner_classes,
                path=test_path,
                context=context,
            )
        ):
            continue
        executable_nodes = _executable_function_nodes(function)
        terminal_pytest_call_ids = frozenset(
            id(node)
            for node in executable_nodes
            if isinstance(node, ast.Call)
            and context.qualified_name(test_path, node.func) in {"pytest.skip", "pytest.xfail"}
        )
        awaited_call_ids = {
            id(node.value)
            for node in executable_nodes
            if isinstance(node, ast.Await) and isinstance(node.value, ast.Call)
        }
        for call in (node for node in executable_nodes if isinstance(node, ast.Call)):
            if not _node_is_reachable(
                function.body,
                call,
                terminal_call_ids=terminal_pytest_call_ids,
            ):
                continue
            if not (
                isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "container"
                and call.func.attr in {"resolve", "aresolve"}
                and call.args
            ):
                continue
            if call.func.attr == "aresolve" and id(call) not in awaited_call_ids:
                continue
            if _container_reassigned_before(
                function,
                call,
            ) or _resolution_exception_is_swallowed(
                function,
                call,
                path=test_path,
                context=context,
            ):
                continue
            argument = call.args[0]
            if (
                isinstance(argument, (ast.Name, ast.Attribute))
                and context.qualified_name(test_path, argument) == target_qualified_name
            ):
                return True
    return False


def _test_functions_with_owners(
    tree: ast.Module,
) -> tuple[
    tuple[
        ast.FunctionDef | ast.AsyncFunctionDef,
        tuple[ast.ClassDef, ...],
    ],
    ...,
]:
    found: list[
        tuple[
            ast.FunctionDef | ast.AsyncFunctionDef,
            tuple[ast.ClassDef, ...],
        ]
    ] = []

    def collect(statements: list[ast.stmt], owners: tuple[ast.ClassDef, ...]) -> None:
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if statement.name.startswith("test_"):
                    found.append((statement, owners))
                continue
            if isinstance(statement, ast.ClassDef):
                collect(statement.body, (*owners, statement))

    collect(tree.body, ())
    return tuple(found)


def _node_is_reachable(
    statements: list[ast.stmt],
    target: ast.AST,
    *,
    terminal_call_ids: frozenset[int] = frozenset(),
) -> bool:
    for statement in statements:
        if any(node is target for node in ast.walk(statement)):
            return _target_is_reachable_in_statement(
                statement,
                target,
                terminal_call_ids=terminal_call_ids,
            )
        if not _statement_can_fall_through(
            statement,
            terminal_call_ids=terminal_call_ids,
        ):
            return False
    return False


def _target_is_reachable_in_statement(
    statement: ast.stmt,
    target: ast.AST,
    *,
    terminal_call_ids: frozenset[int],
) -> bool:
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return False
    if isinstance(statement, (ast.If, ast.While)):
        if _expression_contains_reachable_target(
            statement.test,
            target,
            terminal_call_ids=terminal_call_ids,
        ):
            return True
        if _expression_guarantees_terminal_call(
            statement.test,
            terminal_call_ids=terminal_call_ids,
        ):
            return False
        branches = (
            (statement.orelse,)
            if _is_statically_false(statement.test)
            else (statement.body,)
            if _is_statically_true(statement.test)
            else (statement.body, statement.orelse)
        )
        return any(
            _node_is_reachable(
                branch,
                target,
                terminal_call_ids=terminal_call_ids,
            )
            for branch in branches
        )
    if isinstance(statement, (ast.For, ast.AsyncFor)):
        if _expression_contains_reachable_target(
            statement.iter,
            target,
            terminal_call_ids=terminal_call_ids,
        ):
            return True
        if _expression_guarantees_terminal_call(
            statement.iter,
            terminal_call_ids=terminal_call_ids,
        ):
            return False
        return _node_is_reachable(
            statement.body,
            target,
            terminal_call_ids=terminal_call_ids,
        ) or _node_is_reachable(
            statement.orelse,
            target,
            terminal_call_ids=terminal_call_ids,
        )
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        if any(
            _expression_contains_reachable_target(
                item.context_expr,
                target,
                terminal_call_ids=terminal_call_ids,
            )
            for item in statement.items
        ):
            return True
        if any(
            _expression_guarantees_terminal_call(
                item.context_expr,
                terminal_call_ids=terminal_call_ids,
            )
            for item in statement.items
        ):
            return False
        return _node_is_reachable(
            statement.body,
            target,
            terminal_call_ids=terminal_call_ids,
        )
    if isinstance(statement, ast.Try):
        body_outcomes = _block_exit_kinds(
            statement.body,
            terminal_call_ids=terminal_call_ids,
        )
        if _node_is_reachable(
            statement.body,
            target,
            terminal_call_ids=terminal_call_ids,
        ):
            return True
        if "raise" in body_outcomes and any(
            _node_is_reachable(
                handler.body,
                target,
                terminal_call_ids=terminal_call_ids,
            )
            for handler in statement.handlers
        ):
            return True
        if "fall" in body_outcomes and _node_is_reachable(
            statement.orelse,
            target,
            terminal_call_ids=terminal_call_ids,
        ):
            return True
        return _node_is_reachable(
            statement.finalbody,
            target,
            terminal_call_ids=terminal_call_ids,
        )
    if isinstance(statement, ast.Match):
        if _expression_contains_reachable_target(
            statement.subject,
            target,
            terminal_call_ids=terminal_call_ids,
        ):
            return True
        if _expression_guarantees_terminal_call(
            statement.subject,
            terminal_call_ids=terminal_call_ids,
        ):
            return False
        return any(
            _node_is_reachable(
                case.body,
                target,
                terminal_call_ids=terminal_call_ids,
            )
            for case in statement.cases
        )
    return _expression_contains_reachable_target(
        statement,
        target,
        terminal_call_ids=terminal_call_ids,
    )


def _expression_contains_reachable_target(
    node: ast.AST,
    target: ast.AST,
    *,
    terminal_call_ids: frozenset[int],
) -> bool:
    if node is target:
        return True
    if isinstance(node, ast.Call) and id(node) in terminal_call_ids:
        return False
    if isinstance(node, ast.BoolOp):
        for value in node.values:
            if _expression_contains_reachable_target(
                value,
                target,
                terminal_call_ids=terminal_call_ids,
            ):
                return True
            if _expression_guarantees_terminal_call(
                value,
                terminal_call_ids=terminal_call_ids,
            ):
                return False
            if isinstance(node.op, ast.Or) and _is_statically_true(value):
                return False
            if isinstance(node.op, ast.And) and _is_statically_false(value):
                return False
        return False
    if isinstance(node, ast.IfExp):
        if _expression_contains_reachable_target(
            node.test,
            target,
            terminal_call_ids=terminal_call_ids,
        ):
            return True
        if _expression_guarantees_terminal_call(
            node.test,
            terminal_call_ids=terminal_call_ids,
        ):
            return False
        branches = (
            (node.orelse,)
            if _is_statically_false(node.test)
            else (node.body,)
            if _is_statically_true(node.test)
            else (node.body, node.orelse)
        )
        return any(
            _expression_contains_reachable_target(
                branch,
                target,
                terminal_call_ids=terminal_call_ids,
            )
            for branch in branches
        )
    for child in ast.iter_child_nodes(node):
        if _expression_contains_reachable_target(
            child,
            target,
            terminal_call_ids=terminal_call_ids,
        ):
            return True
        if _expression_guarantees_terminal_call(
            child,
            terminal_call_ids=terminal_call_ids,
        ):
            return False
    return False


def _statement_can_fall_through(
    statement: ast.stmt,
    *,
    terminal_call_ids: frozenset[int] = frozenset(),
) -> bool:
    return "fall" in _statement_exit_kinds(
        statement,
        terminal_call_ids=terminal_call_ids,
    )


def _statement_exit_kinds(
    statement: ast.stmt,
    *,
    terminal_call_ids: frozenset[int] = frozenset(),
) -> set[str]:
    if isinstance(statement, ast.Return):
        return {"return"}
    if isinstance(statement, ast.Raise):
        return {"raise"}
    if isinstance(statement, ast.Break):
        return {"break"}
    if isinstance(statement, ast.Continue):
        return {"continue"}
    if isinstance(statement, ast.If):
        if _expression_guarantees_terminal_call(
            statement.test,
            terminal_call_ids=terminal_call_ids,
        ):
            return {"raise"}
        if _is_statically_false(statement.test):
            return _block_exit_kinds(
                statement.orelse,
                terminal_call_ids=terminal_call_ids,
            )
        if _is_statically_true(statement.test):
            return _block_exit_kinds(
                statement.body,
                terminal_call_ids=terminal_call_ids,
            )
        return _block_exit_kinds(
            statement.body,
            terminal_call_ids=terminal_call_ids,
        ) | _block_exit_kinds(
            statement.orelse,
            terminal_call_ids=terminal_call_ids,
        )
    if isinstance(statement, ast.While):
        if _expression_guarantees_terminal_call(
            statement.test,
            terminal_call_ids=terminal_call_ids,
        ):
            return {"raise"}
        if _is_statically_false(statement.test):
            return _block_exit_kinds(
                statement.orelse,
                terminal_call_ids=terminal_call_ids,
            )
        body_outcomes = _block_exit_kinds(
            statement.body,
            terminal_call_ids=terminal_call_ids,
        )
        outcomes = body_outcomes - {"break", "continue", "fall"}
        if "break" in body_outcomes:
            outcomes.add("fall")
        if not _is_statically_true(statement.test):
            outcomes.update(
                _block_exit_kinds(
                    statement.orelse,
                    terminal_call_ids=terminal_call_ids,
                )
            )
        return outcomes
    if isinstance(statement, (ast.For, ast.AsyncFor)):
        if _expression_guarantees_terminal_call(
            statement.iter,
            terminal_call_ids=terminal_call_ids,
        ):
            return {"raise"}
        body_outcomes = _block_exit_kinds(
            statement.body,
            terminal_call_ids=terminal_call_ids,
        )
        outcomes = body_outcomes - {"break", "continue", "fall"}
        if "break" in body_outcomes:
            outcomes.add("fall")
        outcomes.update(
            _block_exit_kinds(
                statement.orelse,
                terminal_call_ids=terminal_call_ids,
            )
        )
        return outcomes
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        if any(
            _expression_guarantees_terminal_call(
                item.context_expr,
                terminal_call_ids=terminal_call_ids,
            )
            for item in statement.items
        ):
            return {"raise"}
        outcomes = _block_exit_kinds(
            statement.body,
            terminal_call_ids=terminal_call_ids,
        )
        if any(
            isinstance(node, ast.Call)
            for item in statement.items
            for node in ast.walk(item.context_expr)
        ):
            outcomes.add("raise")
        return outcomes
    if isinstance(statement, ast.Try):
        body_outcomes = _block_exit_kinds(
            statement.body,
            terminal_call_ids=terminal_call_ids,
        )
        before_finally = body_outcomes - {"fall"}
        if "fall" in body_outcomes:
            before_finally.update(
                _block_exit_kinds(
                    statement.orelse,
                    terminal_call_ids=terminal_call_ids,
                )
            )
        if "raise" in body_outcomes and statement.handlers:
            before_finally.update(
                outcome
                for handler in statement.handlers
                for outcome in _block_exit_kinds(
                    handler.body,
                    terminal_call_ids=terminal_call_ids,
                )
            )
        final_outcomes = _block_exit_kinds(
            statement.finalbody,
            terminal_call_ids=terminal_call_ids,
        )
        outcomes = final_outcomes - {"fall"}
        if "fall" in final_outcomes:
            outcomes.update(before_finally)
        return outcomes
    if isinstance(statement, ast.Match):
        if _expression_guarantees_terminal_call(
            statement.subject,
            terminal_call_ids=terminal_call_ids,
        ):
            return {"raise"}
        exhaustive = any(
            case.guard is None and _pattern_is_irrefutable(case.pattern) for case in statement.cases
        )
        outcomes = {
            outcome
            for case in statement.cases
            for outcome in _block_exit_kinds(
                case.body,
                terminal_call_ids=terminal_call_ids,
            )
        }
        if not exhaustive:
            outcomes.add("fall")
        return outcomes
    if _expression_guarantees_terminal_call(statement, terminal_call_ids=terminal_call_ids):
        return {"raise"}
    outcomes = {"fall"}
    if any(isinstance(node, ast.Call) for node in _statement_scope_nodes(statement)):
        outcomes.add("raise")
    return outcomes


def _statement_scope_nodes(statement: ast.stmt) -> tuple[ast.AST, ...]:
    nodes: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        if node is not statement and isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
        ):
            return
        nodes.append(node)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(statement)
    return tuple(nodes)


def _expression_guarantees_terminal_call(
    node: ast.AST,
    *,
    terminal_call_ids: frozenset[int],
) -> bool:
    if isinstance(node, ast.Call) and id(node) in terminal_call_ids:
        return True
    if isinstance(node, ast.BoolOp):
        for value in node.values:
            if _expression_guarantees_terminal_call(
                value,
                terminal_call_ids=terminal_call_ids,
            ):
                return True
            if isinstance(node.op, ast.Or) and not _is_statically_false(value):
                return False
            if isinstance(node.op, ast.And) and not _is_statically_true(value):
                return False
        return False
    if isinstance(node, ast.IfExp):
        if _expression_guarantees_terminal_call(
            node.test,
            terminal_call_ids=terminal_call_ids,
        ):
            return True
        if _is_statically_false(node.test):
            return _expression_guarantees_terminal_call(
                node.orelse,
                terminal_call_ids=terminal_call_ids,
            )
        if _is_statically_true(node.test):
            return _expression_guarantees_terminal_call(
                node.body,
                terminal_call_ids=terminal_call_ids,
            )
        return all(
            _expression_guarantees_terminal_call(
                branch,
                terminal_call_ids=terminal_call_ids,
            )
            for branch in (node.body, node.orelse)
        )
    return any(
        _expression_guarantees_terminal_call(
            child,
            terminal_call_ids=terminal_call_ids,
        )
        for child in ast.iter_child_nodes(node)
    )


def _block_exit_kinds(
    statements: list[ast.stmt],
    *,
    terminal_call_ids: frozenset[int] = frozenset(),
) -> set[str]:
    outcomes = {"fall"}
    for statement in statements:
        if "fall" not in outcomes:
            break
        outcomes.remove("fall")
        outcomes.update(
            _statement_exit_kinds(
                statement,
                terminal_call_ids=terminal_call_ids,
            )
        )
    return outcomes


def _pattern_is_irrefutable(pattern: ast.pattern) -> bool:
    if isinstance(pattern, ast.MatchAs):
        return pattern.pattern is None or _pattern_is_irrefutable(pattern.pattern)
    if isinstance(pattern, ast.MatchOr):
        return any(_pattern_is_irrefutable(child) for child in pattern.patterns)
    return False


def _test_is_disabled(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    owner_classes: tuple[ast.ClassDef, ...],
    path: Path,
    context: ArchitectureContext,
) -> bool:
    if any(
        _marker_disables_test(decorator, path=path, context=context)
        for decorator in function.decorator_list
    ):
        return True
    return any(
        any(
            _marker_disables_test(decorator, path=path, context=context)
            for decorator in owner.decorator_list
        )
        or _pytestmark_disables_tests(owner.body, path=path, context=context)
        for owner in owner_classes
    )


def _pytestmark_disables_tests(
    statements: list[ast.stmt],
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    return any(
        _marker_disables_test(marker, path=path, context=context)
        for statement in statements
        for marker in _pytestmark_expressions(statement)
    )


def _pytestmark_expressions(statement: ast.stmt) -> tuple[ast.expr, ...]:
    value: ast.expr | None = None
    if (
        isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "pytestmark"
            for target in statement.targets
        )
    ) or (
        isinstance(statement, ast.AnnAssign)
        and isinstance(statement.target, ast.Name)
        and statement.target.id == "pytestmark"
    ):
        value = statement.value
    if value is None:
        return ()
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return tuple(value.elts)
    return (value,)


def _marker_disables_test(
    marker: ast.expr,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    target = marker.func if isinstance(marker, ast.Call) else marker
    qualified = context.qualified_name(path, target)
    if qualified == "pytest.mark.skip":
        return True
    if qualified == "pytest.mark.xfail":
        if not isinstance(marker, ast.Call):
            return True
        condition = _marker_condition(marker)
        return condition is None or _is_statically_true(condition)
    if qualified != "pytest.mark.skipif" or not isinstance(marker, ast.Call):
        return False
    condition = _marker_condition(marker)
    return condition is not None and _is_statically_true(condition)


def _marker_condition(marker: ast.Call) -> ast.expr | None:
    if marker.args:
        return marker.args[0]
    return next(
        (keyword.value for keyword in marker.keywords if keyword.arg == "condition"),
        None,
    )


def _has_native_container_fixture(
    context: ArchitectureContext,
    *,
    unit_root: Path,
) -> bool:
    path = unit_root / "conftest.py"
    if path not in context.ast_project.files:
        return False
    tree = context.tree(path)
    fixtures = tuple(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _fixture_exposed_name(node, path=path, context=context) == "container"
    )
    return bool(fixtures) and all(
        _fixture_has_native_container_provenance(
            function,
            path=path,
            context=context,
        )
        for function in fixtures
    )


def _has_shadowing_container_fixture(
    context: ArchitectureContext,
    *,
    test_path: Path,
    unit_root: Path,
) -> bool:
    parent = test_path.parent
    while parent != unit_root and parent.is_relative_to(unit_root):
        conftest = parent / "conftest.py"
        if conftest in context.ast_project.files and _defines_container_fixture(
            context.tree(conftest),
            path=conftest,
            context=context,
        ):
            return True
        parent = parent.parent
    return False


def _defines_container_fixture(
    tree: ast.Module,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    return any(
        _fixture_exposed_name(function, path=path, context=context) == "container"
        for function in _fixture_functions(tree.body)
    )


def _fixture_functions(
    statements: list[ast.stmt],
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]:
    functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for statement in statements:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(statement)
        elif isinstance(statement, ast.ClassDef):
            functions.extend(_fixture_functions(statement.body))
    return tuple(functions)


def _fixture_exposed_name(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> str | None:
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if context.qualified_name(path, target) != "pytest.fixture":
            continue
        if not isinstance(decorator, ast.Call):
            return function.name
        explicit_name = next(
            (keyword.value for keyword in decorator.keywords if keyword.arg == "name"),
            None,
        )
        if explicit_name is None:
            return function.name
        if isinstance(explicit_name, ast.Constant) and isinstance(explicit_name.value, str):
            return explicit_name.value
        return None
    return None


def _fixture_has_native_container_provenance(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    outcomes, falls_through = _fixture_block_outcomes(function.body)
    has_yield = any(isinstance(outcome, (ast.Yield, ast.YieldFrom)) for outcome in outcomes)
    return (
        bool(outcomes)
        and (has_yield or not falls_through)
        and all(
            _is_direct_project_container_call(
                outcome.value,
                path=path,
                context=context,
            )
            for outcome in outcomes
        )
    )


def _fixture_statement_outcomes(
    statement: ast.stmt,
) -> tuple[tuple[ast.Return | ast.Yield | ast.YieldFrom, ...], bool]:
    if isinstance(statement, ast.Return):
        return (statement, *_yield_nodes(statement.value)), False
    if isinstance(statement, ast.Raise):
        return _yield_nodes(statement.exc), False
    if isinstance(statement, ast.If):
        if _is_statically_false(statement.test):
            return _fixture_block_outcomes(statement.orelse)
        if _is_statically_true(statement.test):
            return _fixture_block_outcomes(statement.body)
        body_outcomes, body_reachable = _fixture_block_outcomes(statement.body)
        else_outcomes, else_reachable = _fixture_block_outcomes(statement.orelse)
        return (*body_outcomes, *else_outcomes), body_reachable or else_reachable
    if isinstance(statement, ast.While) and _is_statically_false(statement.test):
        return _fixture_block_outcomes(statement.orelse)
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return _fixture_block_outcomes(statement.body)
    if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
        body_outcomes, _body_reachable = _fixture_block_outcomes(statement.body)
        else_outcomes, _else_reachable = _fixture_block_outcomes(statement.orelse)
        return (*body_outcomes, *else_outcomes), True
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return (), True
    if isinstance(statement, ast.Try):
        blocks = (
            statement.body,
            *(handler.body for handler in statement.handlers),
            statement.orelse,
            statement.finalbody,
        )
        outcomes = tuple(
            outcome for block in blocks for outcome in _fixture_block_outcomes(block)[0]
        )
        return outcomes, True
    if isinstance(statement, ast.Match):
        return (
            tuple(
                outcome
                for case in statement.cases
                for outcome in _fixture_block_outcomes(case.body)[0]
            ),
            True,
        )
    return _yield_nodes(statement), True


def _fixture_block_outcomes(
    statements: list[ast.stmt],
) -> tuple[tuple[ast.Return | ast.Yield | ast.YieldFrom, ...], bool]:
    outcomes: list[ast.Return | ast.Yield | ast.YieldFrom] = []
    reachable = True
    for statement in statements:
        if not reachable:
            break
        statement_outcomes, reachable = _fixture_statement_outcomes(statement)
        outcomes.extend(statement_outcomes)
    return tuple(outcomes), reachable


def _yield_nodes(expression: ast.AST | None) -> tuple[ast.Yield | ast.YieldFrom, ...]:
    if expression is None:
        return ()
    yields: list[ast.Yield | ast.YieldFrom] = []

    def visit(node: ast.AST) -> None:
        if node is not expression and isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
        ):
            return
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            yields.append(node)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(expression)
    return tuple(yields)


def _is_direct_project_container_call(
    value: ast.expr | None,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    return (
        isinstance(value, ast.Call)
        and context.qualified_name(path, value.func)
        == f"{context.config.package_name}.ioc.container.get_container"
    )


def _container_is_defaulted(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    positional = (*function.args.posonlyargs, *function.args.args)
    defaulted = {
        argument.arg for argument in positional[len(positional) - len(function.args.defaults) :]
    }
    defaulted.update(
        argument.arg
        for argument, default in zip(
            function.args.kwonlyargs,
            function.args.kw_defaults,
            strict=True,
        )
        if default is not None
    )
    return "container" in defaulted


def _container_is_parametrized(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call) or not decorator.args:
            continue
        chain = ast.unparse(decorator.func)
        if not chain.endswith("parametrize"):
            continue
        names = decorator.args[0]
        if (
            isinstance(names, ast.Constant)
            and isinstance(names.value, str)
            and "container" in {name.strip() for name in names.value.split(",")}
        ):
            return True
        if isinstance(names, (ast.List, ast.Tuple)) and any(
            isinstance(element, ast.Constant) and element.value == "container"
            for element in names.elts
        ):
            return True
    return False


def _container_reassigned_before(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    call: ast.Call,
) -> bool:
    call_position = (call.lineno, call.col_offset)
    for node in _executable_function_nodes(function):
        position = (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))
        if position >= call_position:
            continue
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Store)
            and node.id == "container"
        ):
            return True
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Store)
            and isinstance(node.value, ast.Name)
            and node.value.id == "container"
        ):
            return True
        if isinstance(node, ast.Call) and _call_mutates_container(node):
            return True
    return False


def _call_mutates_container(
    call: ast.Call,
) -> bool:
    target = call.args[0] if call.args else _call_keyword(call, "target")
    if not isinstance(target, ast.Name) or target.id != "container":
        return False
    if isinstance(call.func, ast.Name) and call.func.id == "setattr":
        return True
    return isinstance(call.func, ast.Attribute) and call.func.attr == "setattr"


def _call_patches_container_resolver(
    call: ast.Call,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    target = call.args[0] if call.args else _call_keyword(call, "target")
    if not isinstance(target, ast.Name) or target.id != "container":
        return False
    attribute = call.args[1] if len(call.args) >= 2 else _call_keyword(call, "attribute")
    if not (isinstance(attribute, ast.Constant) and attribute.value in {"resolve", "aresolve"}):
        return False
    qualified = context.qualified_name(path, call.func)
    return qualified == "unittest.mock.patch.object" or ast.unparse(call.func).endswith(
        ".patch.object"
    )


def _call_keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)


def _resolution_exception_is_swallowed(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    call: ast.Call,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Try)
            and any(not _handler_guarantees_raise(handler) for handler in node.handlers)
            and any(
                any(descendant is call for descendant in ast.walk(statement))
                for statement in node.body
            )
        ):
            return True
        if (
            isinstance(node, (ast.With, ast.AsyncWith))
            and any(
                isinstance(item.context_expr, ast.Call)
                and (
                    context.qualified_name(path, item.context_expr.func)
                    in {"contextlib.suppress", "pytest.raises"}
                    or _call_patches_container_resolver(
                        item.context_expr,
                        path=path,
                        context=context,
                    )
                )
                for item in node.items
            )
            and any(
                any(descendant is call for descendant in ast.walk(statement))
                for statement in node.body
            )
        ):
            return True
    return False


def _handler_guarantees_raise(handler: ast.ExceptHandler) -> bool:
    return _block_guarantees_raise(handler.body)


def _block_guarantees_raise(statements: list[ast.stmt]) -> bool:
    return _block_exit_kinds(statements) == {"raise"}


def _executable_function_nodes(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[ast.AST, ...]:
    nodes: list[ast.AST] = []

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
        if isinstance(node, (ast.If, ast.While)) and _is_statically_false(node.test):
            for statement in node.orelse:
                visit(statement)
            return
        if isinstance(node, (ast.If, ast.While)) and _is_statically_true(node.test):
            for statement in node.body:
                visit(statement)
            return
        for descendant in ast.iter_child_nodes(node):
            visit(descendant)

    visit(function)
    return tuple(nodes)


def _is_statically_false(expression: ast.expr) -> bool:
    return (
        (
            isinstance(expression, ast.Constant)
            and (expression.value is False or expression.value == 0)
        )
        or (isinstance(expression, ast.Name) and expression.id == "TYPE_CHECKING")
        or (
            isinstance(expression, ast.Attribute)
            and isinstance(expression.value, ast.Name)
            and expression.value.id == "typing"
            and expression.attr == "TYPE_CHECKING"
        )
    )


def _is_statically_true(expression: ast.expr) -> bool:
    return isinstance(expression, ast.Constant) and bool(expression.value)
