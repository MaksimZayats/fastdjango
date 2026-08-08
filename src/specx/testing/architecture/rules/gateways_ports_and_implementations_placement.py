from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_direct_base_names,
    class_has_foundation_base_at,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    violation,
)


class GatewayPortsAndImplementationsLiveInExpectedPackagesRule(ArchitectureRuleBase):
    """Keep gateway ports and concrete gateway implementations in distinct packages.

    Gateway ports belong under `gateways`; concrete external-system adapters
    belong under scope infrastructure so the boundary is clear.
    """

    id: SpecxRuleId = SpecxRuleId.GATEWAY_PORTS_AND_IMPLEMENTATIONS_LIVE_IN_EXPECTED_PACKAGES

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in context.core_paths():
            relative_parts = path.relative_to(context.src_root / "core").parts
            if len(relative_parts) < 2:
                continue
            inner_package = relative_parts[1]
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
                direct_bases = class_direct_base_names(node, aliases)
                if "BaseGateway" in direct_bases and inner_package != "gateways":
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message="gateway port outside gateways",
                            symbol=node.name,
                        )
                    )
                if "BaseGateway" not in direct_bases and inner_package != "infrastructure":
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message="gateway implementation outside infrastructure",
                            symbol=node.name,
                        )
                    )
        return tuple(violations)
