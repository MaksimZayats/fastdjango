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
    ambient_environment_nodes,
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
            for class_node in behavior_classes:
                for function in (
                    child
                    for child in class_node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                ):
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
                                    self.id,
                                    path=path,
                                    symbol=class_node.name,
                                    node=call,
                                    message=(
                                        "direct ambient runtime call "
                                        f"{resolved_call_name(call, path=path, context=context)!r}"
                                    ),
                                )
                            )
                    for node in ambient_environment_nodes(tree, path=path, context=context):
                        if any(node in ast.walk(call) for call in ambient_calls):
                            continue
                        if any(node is descendant for descendant in ast.walk(function)):
                            findings.append(
                                violation(
                                    self.id,
                                    path=path,
                                    symbol=class_node.name,
                                    node=node,
                                    message="direct environment-state access 'os.environ'",
                                )
                            )
        return tuple(findings)
