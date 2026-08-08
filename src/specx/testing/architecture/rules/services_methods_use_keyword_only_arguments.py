from __future__ import annotations

import ast
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_has_foundation_base_at,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._call_analysis import class_hierarchy
from specx.testing.architecture.rules._shared import ArchitectureRuleBase, violation


class ServiceMethodsUseKeywordOnlyArgumentsRule(ArchitectureRuleBase):
    """Require public service methods to expose explicit keyword-only arguments after self."""

    id: SpecxRuleId = SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS
    remediation: str | None = (
        "Insert `*` before public service parameters so callers must name each value."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        definition_index = class_definition_base_index(context)
        service_bases = {"BasePureService", "BaseReadService", "BaseEffectService"}
        findings: list[SpecxArchitectureViolation] = []
        checked_declarations: set[tuple[Path, int]] = set()
        for path in context.source_paths():
            for class_node in (
                node for node in ast.walk(context.tree(path)) if isinstance(node, ast.ClassDef)
            ):
                if not any(
                    class_has_foundation_base_at(
                        class_node,
                        base,
                        source_path=path,
                        context=context,
                        definition_index=definition_index,
                    )
                    for base in service_bases
                ):
                    continue
                seen_methods: set[str] = set()
                for method_path, method_owner in class_hierarchy(
                    class_node,
                    path=path,
                    context=context,
                ):
                    declarations_by_name: dict[
                        str,
                        list[ast.FunctionDef | ast.AsyncFunctionDef],
                    ] = {}
                    for child in method_owner.body:
                        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            continue
                        if child.name.startswith("_"):
                            continue
                        declarations_by_name.setdefault(child.name, []).append(child)
                    for method_name, declarations in declarations_by_name.items():
                        if method_name in seen_methods:
                            continue
                        seen_methods.add(method_name)
                        for method in declarations:
                            declaration = (method_path, id(method))
                            if declaration in checked_declarations:
                                continue
                            checked_declarations.add(declaration)
                            findings.extend(
                                _method_findings(
                                    self.id,
                                    path=method_path,
                                    class_node=class_node,
                                    method=method,
                                    context=context,
                                )
                            )
        return tuple(findings)


def _method_findings(
    rule_id: SpecxRuleId,
    *,
    path: Path,
    class_node: ast.ClassDef,
    method: ast.FunctionDef | ast.AsyncFunctionDef,
    context: ArchitectureContext,
) -> list[SpecxArchitectureViolation]:
    positional_arguments = [*method.args.posonlyargs, *method.args.args]
    if positional_arguments and not _is_static_method(method, path=path, context=context):
        positional_arguments = positional_arguments[1:]
    positional = [argument.arg for argument in positional_arguments]
    if method.args.vararg is not None:
        positional.append(f"*{method.args.vararg.arg}")
    if not positional:
        return []
    return [
        violation(
            rule_id,
            path=path,
            symbol=f"{class_node.name}.{method.name}",
            node=method,
            message=f"public parameters must be keyword-only: {positional}",
        )
    ]


def _is_static_method(
    method: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    return any(
        context.qualified_name(
            path,
            decorator.func if isinstance(decorator, ast.Call) else decorator,
        )
        in {"builtins.staticmethod", "staticmethod"}
        for decorator in method.decorator_list
    )
