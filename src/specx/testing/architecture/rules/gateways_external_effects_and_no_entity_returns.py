from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    ArchitectureContext,
    annotation_name,
    class_definition_base_index,
    class_has_foundation_base_at,
    declares_external_effect,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    violation,
)


class GatewaysDeclareExternalEffectsAndDoNotReturnEntitiesRule(ArchitectureRuleBase):
    """Require gateway ports to document external effects and avoid entity returns.

    Gateways represent outbound business capabilities, so their public contract
    should say what external effect occurs and return DTOs or explicit results.
    """

    id: SpecxRuleId = SpecxRuleId.GATEWAYS_DECLARE_EXTERNAL_EFFECTS_AND_DO_NOT_RETURN_ENTITIES

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in context.core_paths():
            tree = context.tree(path)
            aliases = context.aliases(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                if not class_has_foundation_base_at(
                    node,
                    "BaseGateway",
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                ):
                    continue
                if not declares_external_effect(node):
                    violations.append(
                        violation(
                            self.id, path=path, message="missing external effect", symbol=node.name
                        )
                    )
                for child in node.body:
                    if not isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef)):
                        continue
                    return_annotation = annotation_name(child.returns, aliases)
                    if "Entity" in return_annotation:
                        violations.append(
                            violation(
                                self.id,
                                path=path,
                                message=f"{child.name} returns {return_annotation}",
                                symbol=node.name,
                            )
                        )
        return tuple(violations)
