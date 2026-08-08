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
from specx.testing.architecture.rules._call_analysis import (
    MethodBinding,
    class_hierarchy,
    class_method_declarations,
)
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
        checked_declarations: set[tuple[Path, int, MethodBinding]] = set()
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
                    for method_name, group in class_method_declarations(
                        method_owner,
                        path=method_path,
                        context=context,
                    ).items():
                        if method_name.startswith("_") or method_name in seen_methods:
                            continue
                        if group.always_bound:
                            seen_methods.add(method_name)
                        for method_declaration in group.declarations:
                            if method_declaration.descriptor_component is not None:
                                continue
                            declaration_key = (
                                method_declaration.path,
                                id(method_declaration.function),
                                method_declaration.binding,
                            )
                            if declaration_key in checked_declarations:
                                continue
                            checked_declarations.add(declaration_key)
                            findings.extend(
                                _method_findings(
                                    self.id,
                                    path=method_declaration.path,
                                    class_node=class_node,
                                    method=method_declaration.function,
                                    method_name=method_name,
                                    binding=method_declaration.binding,
                                )
                            )
        return tuple(findings)


def _method_findings(
    rule_id: SpecxRuleId,
    *,
    path: Path,
    class_node: ast.ClassDef,
    method: ast.FunctionDef | ast.AsyncFunctionDef,
    method_name: str,
    binding: MethodBinding,
) -> list[SpecxArchitectureViolation]:
    positional_arguments = [*method.args.posonlyargs, *method.args.args]
    if positional_arguments and binding != "static":
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
            symbol=f"{class_node.name}.{method_name}",
            node=method,
            message=f"public parameters must be keyword-only: {positional}",
        )
    ]
