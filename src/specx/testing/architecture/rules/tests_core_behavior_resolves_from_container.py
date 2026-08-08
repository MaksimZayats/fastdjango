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
                    or _defines_local_container(test_tree)
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
    for function in (
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ):
        arguments = (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)
        if (
            not any(argument.arg == "container" for argument in arguments)
            or _container_is_defaulted(function)
            or _container_is_parametrized(function)
        ):
            continue
        executable_nodes = _executable_function_nodes(function)
        awaited_call_ids = {
            id(node.value)
            for node in executable_nodes
            if isinstance(node, ast.Await) and isinstance(node.value, ast.Call)
        }
        for call in (node for node in executable_nodes if isinstance(node, ast.Call)):
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
            if _container_reassigned_before(function, call):
                continue
            argument = call.args[0]
            if (
                isinstance(argument, (ast.Name, ast.Attribute))
                and context.qualified_name(test_path, argument) == target_qualified_name
            ):
                return True
    return False


def _has_native_container_fixture(
    context: ArchitectureContext,
    *,
    unit_root: Path,
) -> bool:
    path = unit_root / "conftest.py"
    if path not in context.ast_project.files:
        return False
    tree = context.tree(path)
    for function in (
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "container"
    ):
        if not any(
            context.qualified_name(
                path, decorator.func if isinstance(decorator, ast.Call) else decorator
            ).endswith("pytest.fixture")
            for decorator in function.decorator_list
        ):
            continue
        for statement in function.body:
            value = statement.value if isinstance(statement, (ast.Return, ast.Expr)) else None
            if isinstance(value, (ast.Yield, ast.YieldFrom)):
                value = value.value
            if (
                isinstance(value, ast.Call)
                and context.qualified_name(path, value.func)
                == f"{context.config.package_name}.ioc.container.get_container"
            ):
                return True
    return False


def _has_shadowing_container_fixture(
    context: ArchitectureContext,
    *,
    test_path: Path,
    unit_root: Path,
) -> bool:
    parent = test_path.parent
    while parent != unit_root and parent.is_relative_to(unit_root):
        conftest = parent / "conftest.py"
        if conftest in context.ast_project.files and _defines_local_container(
            context.tree(conftest)
        ):
            return True
        parent = parent.parent
    return False


def _defines_local_container(tree: ast.Module) -> bool:
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "container"
        for node in tree.body
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
    return any(
        isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Store)
        and node.id == "container"
        and (node.lineno, node.col_offset) < call_position
        for node in _executable_function_nodes(function)
    )


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


def _is_statically_false(expression: ast.expr) -> bool:
    return (isinstance(expression, ast.Constant) and expression.value is False) or (
        isinstance(expression, ast.Name) and expression.id == "TYPE_CHECKING"
    )


def _is_statically_true(expression: ast.expr) -> bool:
    return isinstance(expression, ast.Constant) and expression.value is True
