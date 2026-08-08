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


class CapabilitiesLiveInExpectedPackagesAndUseExpectedSuffixesRule(ArchitectureRuleBase):
    """Keep capability classes in capability packages with capability naming.

    Capabilities are narrow injectable abilities, so placement and suffix checks
    prevent them from drifting into services, repositories, gateways, or helpers.
    """

    id: SpecxRuleId = SpecxRuleId.CAPABILITIES_LIVE_IN_EXPECTED_PACKAGES_AND_USE_EXPECTED_SUFFIXES

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in context.source_paths():
            if "foundation" in path.relative_to(context.src_root).parts:
                continue
            relative_parts = path.relative_to(context.src_root).parts
            relative_layer = next(iter(relative_parts), "")
            tree = context.tree(path)
            aliases = context.aliases(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                if not class_has_foundation_base_at(
                    node,
                    "BaseCapability",
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                ):
                    continue
                if relative_layer == "core":
                    inner_package = relative_parts[2] if len(relative_parts) > 2 else ""
                    if inner_package != "capabilities":
                        violations.append(
                            violation(
                                self.id,
                                path=path,
                                message="capability outside capabilities",
                                symbol=node.name,
                            )
                        )
                elif relative_layer != "shared":
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message="capability outside core/shared",
                            symbol=node.name,
                        )
                    )
                if "BaseCapability" in class_direct_base_names(
                    node, aliases
                ) and not node.name.endswith("Capability"):
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message="direct BaseCapability subclass must end with Capability",
                            symbol=node.name,
                        )
                    )
        return tuple(violations)
