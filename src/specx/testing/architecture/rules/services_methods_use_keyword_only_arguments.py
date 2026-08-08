from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_has_foundation_base_at,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
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
                for method in (
                    child
                    for child in class_node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not child.name.startswith("_")
                ):
                    positional = [
                        argument.arg
                        for argument in (*method.args.posonlyargs, *method.args.args)
                        if argument.arg not in {"self", "cls"}
                    ]
                    if positional:
                        findings.append(
                            violation(
                                self.id,
                                path=path,
                                symbol=f"{class_node.name}.{method.name}",
                                node=method,
                                message=f"public parameters must be keyword-only: {positional}",
                            )
                        )
        return tuple(findings)
