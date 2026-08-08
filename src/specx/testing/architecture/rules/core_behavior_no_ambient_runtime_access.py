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
    ambient_environment_nodes,
    ambient_runtime_value_nodes,
    class_hierarchy,
    class_method_declarations,
    function_behavior_nodes,
    is_ambient_runtime_call,
    resolved_call_name,
)
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    violation,
)


class CoreBehaviorNoAmbientRuntimeAccessRule(ArchitectureRuleBase):
    """Prevent use cases and services from obtaining ambient runtime behavior directly."""

    id: SpecxRuleId = SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS
    remediation: str | None = (
        "Inject a capability or gateway that owns time, randomness, identifiers, environment, "
        "filesystem, process, or network access."
    )
    detection_boundary = (
        "Recognizes common standard-library and client effect APIs through static aliases; "
        "project-specific effect wrappers require architectural review."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        definition_index = class_definition_base_index(context)
        findings: list[SpecxArchitectureViolation] = []
        for path in context.source_paths():
            tree = context.tree(path)
            behavior_classes = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)
                and not class_is_statically_abstract_at(
                    node,
                    source_path=path,
                    context=context,
                )
                and (
                    class_has_foundation_base_at(
                        node,
                        "BaseUseCase",
                        source_path=path,
                        context=context,
                        definition_index=definition_index,
                    )
                    or any(
                        class_has_foundation_base_at(
                            node,
                            base,
                            source_path=path,
                            context=context,
                            definition_index=definition_index,
                        )
                        for base in {"BasePureService", "BaseReadService", "BaseEffectService"}
                    )
                )
            ]
            for behavior_class in behavior_classes:
                seen_methods: set[str] = set()
                for method_path, method_owner in class_hierarchy(
                    behavior_class,
                    path=path,
                    context=context,
                ):
                    for method_name, declarations in class_method_declarations(
                        method_owner,
                        path=method_path,
                        context=context,
                    ).items():
                        if method_name in seen_methods:
                            continue
                        seen_methods.add(method_name)
                        function_path, function = declarations[-1]
                        findings.extend(
                            _ambient_method_findings(
                                self.id,
                                context=context,
                                path=function_path,
                                behavior_path=path,
                                behavior_class=behavior_class,
                                function=function,
                            )
                        )
        return _deduplicate_declaration_findings(findings)


def _ambient_method_findings(
    rule_id: SpecxRuleId,
    *,
    context: ArchitectureContext,
    path: Path,
    behavior_path: Path,
    behavior_class: ast.ClassDef,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[SpecxArchitectureViolation]:
    findings: list[SpecxArchitectureViolation] = []
    ambient_candidates = [
        call
        for call in function_behavior_nodes(function)
        if isinstance(call, ast.Call)
        and is_ambient_runtime_call(
            call,
            path=path,
            context=context,
            function=function,
            class_node=behavior_class,
            class_path=behavior_path,
        )
    ]
    ambient_calls = [
        call
        for call in ambient_candidates
        if not any(
            call is not outer and any(call is node for node in ast.walk(outer))
            for outer in ambient_candidates
        )
    ]
    for call in ambient_calls:
        findings.append(
            violation(
                rule_id,
                path=path,
                symbol=behavior_class.name,
                node=call,
                message=(
                    "direct ambient runtime call "
                    f"{resolved_call_name(call, path=path, context=context)!r}"
                ),
            )
        )
    tree = context.tree(path)
    behavior_node_ids = {id(node) for node in function_behavior_nodes(function)}
    for node in ambient_environment_nodes(tree, path=path, context=context):
        if any(node in ast.walk(call) for call in ambient_calls):
            continue
        if id(node) in behavior_node_ids:
            findings.append(
                violation(
                    rule_id,
                    path=path,
                    symbol=behavior_class.name,
                    node=node,
                    message="direct environment-state access 'os.environ'",
                )
            )
    for node in ambient_runtime_value_nodes(tree, path=path, context=context):
        if any(node in ast.walk(call) for call in ambient_calls):
            continue
        if id(node) in behavior_node_ids:
            findings.append(
                violation(
                    rule_id,
                    path=path,
                    symbol=behavior_class.name,
                    node=node,
                    message=(
                        f"direct ambient runtime value {context.qualified_name(path, node)!r}"
                    ),
                )
            )
    return findings


def _deduplicate_declaration_findings(
    findings: list[SpecxArchitectureViolation],
) -> tuple[SpecxArchitectureViolation, ...]:
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
