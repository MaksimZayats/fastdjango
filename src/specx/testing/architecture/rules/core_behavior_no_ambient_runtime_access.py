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
    ambient_environment_nodes,
    ambient_runtime_value_nodes,
    class_hierarchy,
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
        scanned_methods: set[tuple[Path, int]] = set()
        for path in context.source_paths():
            tree = context.tree(path)
            behavior_classes = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)
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
                for method_path, class_node in class_hierarchy(
                    behavior_class,
                    path=path,
                    context=context,
                ):
                    for function in (
                        child
                        for child in class_node.body
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ):
                        method_key = (method_path, id(function))
                        if method_key in scanned_methods:
                            continue
                        scanned_methods.add(method_key)
                        findings.extend(
                            _ambient_method_findings(
                                self.id,
                                context=context,
                                path=method_path,
                                class_node=class_node,
                                function=function,
                            )
                        )
        return tuple(findings)


def _ambient_method_findings(
    rule_id: SpecxRuleId,
    *,
    context: ArchitectureContext,
    path: Path,
    class_node: ast.ClassDef,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[SpecxArchitectureViolation]:
    findings: list[SpecxArchitectureViolation] = []
    ambient_calls: list[ast.Call] = []
    for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
        if is_ambient_runtime_call(
            call,
            path=path,
            context=context,
            function=function,
            class_node=class_node,
        ):
            ambient_calls.append(call)
            findings.append(
                violation(
                    rule_id,
                    path=path,
                    symbol=class_node.name,
                    node=call,
                    message=(
                        "direct ambient runtime call "
                        f"{resolved_call_name(call, path=path, context=context)!r}"
                    ),
                )
            )
    tree = context.tree(path)
    for node in ambient_environment_nodes(tree, path=path, context=context):
        if any(node in ast.walk(call) for call in ambient_calls):
            continue
        if any(node is descendant for descendant in ast.walk(function)):
            findings.append(
                violation(
                    rule_id,
                    path=path,
                    symbol=class_node.name,
                    node=node,
                    message="direct environment-state access 'os.environ'",
                )
            )
    for node in ambient_runtime_value_nodes(tree, path=path, context=context):
        if any(node is descendant for descendant in ast.walk(function)):
            findings.append(
                violation(
                    rule_id,
                    path=path,
                    symbol=class_node.name,
                    node=node,
                    message=(
                        f"direct ambient runtime value {context.qualified_name(path, node)!r}"
                    ),
                )
            )
    return findings
