from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_has_foundation_base_at,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._call_analysis import (
    call_is_injected_collaborator_or_uow,
    is_ambient_runtime_call,
    is_statically_recognized_constructor,
    resolved_call_name,
)
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    violation,
)


class UseCasesOrchestrateThroughCollaboratorsRule(ArchitectureRuleBase):
    """Require use-case execution to orchestrate injected collaborators and typed objects."""

    id: SpecxRuleId = SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS
    remediation: str | None = (
        "Move behavior behind an injected service or capability, construct a typed object, "
        "or approve the exact qualified function in `[tool.specx.call-policy]`."
    )
    detection_boundary = (
        "Checks calls in concrete use-case methods and resolves static imports and aliases; "
        "dynamic dispatch and runtime monkeypatching are intentionally not inferred."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        definition_index = class_definition_base_index(context)
        findings: list[SpecxArchitectureViolation] = []
        for path in context.source_paths():
            tree = context.tree(path)
            for class_node in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
                if not class_has_foundation_base_at(
                    class_node,
                    "BaseUseCase",
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                ):
                    continue
                for function in (
                    child
                    for child in class_node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not child.name.startswith("__")
                ):
                    for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
                        qualified_name = resolved_call_name(call, path=path, context=context)
                        if is_ambient_runtime_call(
                            call,
                            path=path,
                            context=context,
                            function=function,
                            class_node=class_node,
                        ):
                            continue
                        if qualified_name in context.config.allowed_use_case_functions:
                            continue
                        if is_statically_recognized_constructor(call, path=path, context=context):
                            continue
                        if call_is_injected_collaborator_or_uow(
                            call,
                            function=function,
                            class_node=class_node,
                            path=path,
                            context=context,
                        ):
                            continue
                        findings.append(
                            violation(
                                self.id,
                                path=path,
                                symbol=class_node.name,
                                node=call,
                                message=(
                                    f"direct call {qualified_name!r} is not an approved "
                                    "constructor or collaborator call"
                                ),
                            )
                        )
        return tuple(findings)
