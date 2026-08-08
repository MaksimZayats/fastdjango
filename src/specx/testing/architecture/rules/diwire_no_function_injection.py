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
                if id(call) not in decorator_calls and _is_inject_expression(
                    call, path=path, context=context
                ):
                    findings.append(
                        violation(
                            self.id,
                            path=path,
                            node=call,
                            message="resolver_context.inject performs function-level DI",
                        )
                    )
            for function in functions:
                injected = [
                    argument.arg
                    for argument in (
                        *function.args.posonlyargs,
                        *function.args.args,
                        *function.args.kwonlyargs,
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
    return context.qualified_name(path, target) == "diwire.resolver_context.inject"


def _is_injected_annotation(
    annotation: ast.expr | None,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    if annotation is None:
        return False
    if context.qualified_name(path, annotation) == "diwire.Injected":
        return True
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
    return any("Injected" in context.qualified_name(path, element) for element in elements[1:])
