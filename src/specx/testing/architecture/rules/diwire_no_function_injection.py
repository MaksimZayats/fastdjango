from __future__ import annotations

import ast
from pathlib import Path

from specx.testing.architecture.context import ArchitectureContext
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import ArchitectureRuleBase, violation


class DIWireNoFunctionInjectionRule(ArchitectureRuleBase):
    """Reject function-level DI while preserving constructor fields and ordinary fixtures."""

    id: SpecxRuleId = SpecxRuleId.DIWIRE_NO_FUNCTION_INJECTION
    remediation: str | None = (
        "Use `Injected[...]` constructor fields on project classes; tests should use ordinary "
        "pytest fixtures and resolve targets from the native container fixture."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        findings: list[SpecxArchitectureViolation] = []
        for path in sorted(context.ast_project.files):
            tree = context.tree(path)
            functions = tuple(
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
            decorator_calls = {
                id(decorator)
                for function in functions
                for decorator in function.decorator_list
                if isinstance(decorator, ast.Call)
                and _is_inject_expression(decorator, path=path, context=context)
            }
            for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
                if id(call) not in decorator_calls and _is_function_di_expression(
                    call,
                    path=path,
                    context=context,
                ):
                    findings.append(
                        violation(
                            self.id,
                            path=path,
                            node=call,
                            message="resolver_context performs function-level DI",
                        )
                    )
            for function in functions:
                variadic_arguments = tuple(
                    argument
                    for argument in (function.args.vararg, function.args.kwarg)
                    if argument is not None
                )
                injected = [
                    argument.arg
                    for argument in (
                        *function.args.posonlyargs,
                        *function.args.args,
                        *function.args.kwonlyargs,
                        *variadic_arguments,
                    )
                    if _is_injected_annotation(
                        argument.annotation,
                        path=path,
                        context=context,
                    )
                ]
                decorated = any(
                    _is_inject_expression(decorator, path=path, context=context)
                    for decorator in function.decorator_list
                )
                if injected or decorated:
                    reasons: list[str] = []
                    if decorated:
                        reasons.append("uses resolver_context.inject")
                    if injected:
                        reasons.append(f"parameters use DIWire injection: {injected}")
                    findings.append(
                        violation(
                            self.id,
                            path=path,
                            symbol=function.name,
                            node=function,
                            message="; ".join(reasons),
                        )
                    )
        return tuple(findings)


def _is_inject_expression(
    expression: ast.expr,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    target = expression.func if isinstance(expression, ast.Call) else expression
    return "diwire.resolver_context.inject" in context.qualified_names(path, target)


def _is_function_di_expression(
    expression: ast.expr,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    target = expression.func if isinstance(expression, ast.Call) else expression
    return bool(
        context.qualified_names(path, target)
        & {
            "diwire.resolver_context.inject",
            "diwire.resolver_context.resolve",
            "diwire.resolver_context.aresolve",
        }
    )


def _is_injected_annotation(
    annotation: ast.expr | None,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    return _annotation_is_injected(
        annotation,
        path=path,
        context=context,
        visited=frozenset(),
    )


def _annotation_is_injected(
    annotation: ast.expr | None,
    *,
    path: Path,
    context: ArchitectureContext,
    visited: frozenset[str],
) -> bool:
    if annotation is None:
        return False
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        parsed = _parse_string_annotation(annotation)
        return parsed is not None and _annotation_is_injected(
            parsed,
            path=path,
            context=context,
            visited=visited,
        )
    qualified = context.qualified_name(path, annotation)
    if qualified == "diwire.Injected":
        return True
    if qualified not in visited:
        alias = _project_alias_expression(qualified, context=context)
        if alias is not None:
            alias_path, expression = alias
            return _annotation_is_injected(
                expression,
                path=alias_path,
                context=context,
                visited=visited | {qualified},
            )
    if not isinstance(annotation, ast.Subscript):
        return False
    if context.qualified_name(path, annotation.value) == "diwire.Injected":
        return True
    if context.qualified_name(path, annotation.value) not in {
        "typing.Annotated",
        "typing_extensions.Annotated",
    }:
        return False
    elements = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else ()
    return any(
        context.qualified_name(
            path,
            element.func if isinstance(element, ast.Call) else element,
        )
        == "diwire._internal.markers.InjectedMarker"
        for element in elements[1:]
    )


def _parse_string_annotation(annotation: ast.Constant) -> ast.expr | None:
    value = annotation.value
    if not isinstance(value, str):
        return None
    try:
        parsed = ast.parse(value, mode="eval").body
    except SyntaxError:
        return None
    for node in ast.walk(parsed):
        ast.copy_location(node, annotation)
    return parsed


def _project_alias_expression(
    qualified_name: str,
    *,
    context: ArchitectureContext,
) -> tuple[Path, ast.expr] | None:
    for alias_path in context.source_paths():
        module = ".".join(
            (
                context.config.package_name,
                *alias_path.relative_to(context.src_root).with_suffix("").parts,
            )
        )
        for statement in context.tree(alias_path).body:
            alias_name: str | None = None
            value: ast.expr | None = None
            type_alias_name = getattr(statement, "name", None)
            type_alias_value = getattr(statement, "value", None)
            if (
                type(statement).__name__ == "TypeAlias"
                and isinstance(type_alias_name, ast.Name)
                and isinstance(type_alias_value, ast.expr)
            ):
                alias_name, value = type_alias_name.id, type_alias_value
            elif (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
            ):
                alias_name, value = statement.targets[0].id, statement.value
            elif (
                isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and statement.value is not None
            ):
                alias_name, value = statement.target.id, statement.value
            if (
                alias_name is not None
                and value is not None
                and qualified_name in {alias_name, f"{module}.{alias_name}"}
            ):
                return alias_path, value
    return None
