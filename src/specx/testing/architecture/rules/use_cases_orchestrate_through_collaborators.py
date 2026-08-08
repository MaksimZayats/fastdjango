from __future__ import annotations

import ast
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_has_foundation_base_at,
    class_is_statically_abstract_at,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._call_analysis import (
    call_is_injected_collaborator_or_uow,
    class_hierarchy,
    class_method_declarations,
    function_behavior_nodes,
    is_ambient_runtime_call,
    is_statically_recognized_constructor,
    resolved_call_name,
    resolved_call_names,
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
        "Checks calls declared in use-case classes and resolves static imports and aliases; "
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
                ) or class_is_statically_abstract_at(
                    class_node,
                    source_path=path,
                    context=context,
                ):
                    continue
                seen_methods: set[str] = set()
                for method_path, method_owner in class_hierarchy(
                    class_node,
                    path=path,
                    context=context,
                ):
                    for method_name, declarations in class_method_declarations(
                        method_owner,
                        path=method_path,
                        context=context,
                    ).items():
                        if method_name.startswith("__") or method_name in seen_methods:
                            continue
                        seen_methods.add(method_name)
                        function_path, function = declarations[-1]
                        findings.extend(
                            self._check_method(
                                context,
                                path=function_path,
                                use_case_path=path,
                                use_case_class=class_node,
                                function=function,
                            )
                        )
        unique: dict[
            tuple[Path | None, int | None, int | None, str],
            SpecxArchitectureViolation,
        ] = {}
        for finding in findings:
            unique.setdefault(
                (finding.path, finding.line, finding.column, finding.message),
                finding,
            )
        return tuple(unique.values())

    def _check_method(
        self,
        context: ArchitectureContext,
        *,
        path: Path,
        use_case_path: Path,
        use_case_class: ast.ClassDef,
        function: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> list[SpecxArchitectureViolation]:
        findings: list[SpecxArchitectureViolation] = []
        for call in (
            node for node in function_behavior_nodes(function) if isinstance(node, ast.Call)
        ):
            qualified_name = resolved_call_name(call, path=path, context=context)
            if is_ambient_runtime_call(
                call,
                path=path,
                context=context,
                function=function,
                class_node=use_case_class,
                class_path=use_case_path,
            ):
                continue
            if (
                resolved_call_names(
                    call,
                    path=path,
                    context=context,
                )
                <= context.config.allowed_use_case_functions
            ):
                continue
            if is_statically_recognized_constructor(call, path=path, context=context):
                continue
            if call_is_injected_collaborator_or_uow(
                call,
                function=function,
                class_node=use_case_class,
                path=path,
                context=context,
                class_path=use_case_path,
            ):
                continue
            findings.append(
                violation(
                    self.id,
                    path=path,
                    symbol=use_case_class.name,
                    node=call,
                    message=(
                        f"direct call {qualified_name!r} is not an approved "
                        "constructor or collaborator call"
                    ),
                )
            )
        return findings
