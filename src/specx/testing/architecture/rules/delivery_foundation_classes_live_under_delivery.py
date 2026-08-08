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


class DeliveryFoundationClassesLiveUnderDeliveryRule(ArchitectureRuleBase):
    """Place delivery foundation subclasses under the top-level delivery package."""

    id: SpecxRuleId = SpecxRuleId.DELIVERY_FOUNDATION_CLASSES_LIVE_UNDER_DELIVERY
    remediation: str | None = (
        "Move controllers, delivery services, schemas, and lifecycles under `delivery/`."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        definition_index = class_definition_base_index(context)
        bases = {"BaseController", "BaseDeliveryService", "BaseFastAPISchema", "BaseLifecycle"}
        findings: list[SpecxArchitectureViolation] = []
        for path in context.source_paths():
            relative = path.relative_to(context.src_root)
            if relative.parts[:1] == ("delivery",):
                continue
            for node in ast.walk(context.tree(path)):
                if not isinstance(node, ast.ClassDef):
                    continue
                if any(
                    class_has_foundation_base_at(
                        node,
                        base,
                        source_path=path,
                        context=context,
                        definition_index=definition_index,
                    )
                    for base in bases
                ):
                    findings.append(
                        violation(
                            self.id,
                            path=path,
                            symbol=node.name,
                            node=node,
                            message=(
                                "delivery foundation subclass lives outside top-level delivery/"
                            ),
                        )
                    )
        return tuple(findings)
