from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    CORE_SERVICE_BASE_NAMES,
    ArchitectureContext,
    class_definition_base_index,
    class_has_foundation_base_at,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    violation,
)


class CoreServicesUseEffectSpecificServiceBasesRule(ArchitectureRuleBase):
    """Require core services to choose pure, read, or effect service bases.

    The service base communicates whether a service is deterministic, read-only,
    or side-effecting, which makes transaction ownership easier to review.
    """

    id: SpecxRuleId = SpecxRuleId.CORE_SERVICES_USE_EFFECT_SPECIFIC_SERVICE_BASES

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in context.core_service_paths():
            tree = context.tree(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and not any(
                    class_has_foundation_base_at(
                        node,
                        base,
                        source_path=path,
                        context=context,
                        definition_index=definition_index,
                    )
                    for base in CORE_SERVICE_BASE_NAMES
                ):
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message="core service lacks effect-specific base",
                            symbol=node.name,
                        )
                    )
        return tuple(violations)
