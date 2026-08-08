from __future__ import annotations

import ast
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    uses_diwire_container,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    class_can_inject_container,
    class_injects_diwire_container,
    is_delivery_composition_module,
    violation,
)


class OnlyIOCDeliveryAppAndTestsImportContainerRule(ArchitectureRuleBase):
    """Restrict `diwire.Container` imports to composition and tests.

    Application classes should receive dependencies rather than importing the
    container or resolving collaborators directly. A delivery lifecycle is the
    narrow exception because it owns app shutdown and closes the container.
    """

    id: SpecxRuleId = SpecxRuleId.ONLY_IOC_DELIVERY_APP_AND_TESTS_IMPORT_CONTAINER

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in context.source_paths():
            if not uses_diwire_container(context.tree(path)):
                continue
            relative = path.relative_to(context.src_root)
            allowed = relative == Path("ioc/container.py") or is_delivery_composition_module(
                relative
            )
            if not allowed:
                violations.append(
                    violation(
                        self.id,
                        path=path,
                        message="imports diwire.Container outside allowed composition modules",
                    )
                )

            aliases = context.aliases(path)
            for class_node in [
                node for node in ast.walk(context.tree(path)) if isinstance(node, ast.ClassDef)
            ]:
                if class_injects_diwire_container(
                    class_node,
                    aliases,
                ) and not class_can_inject_container(
                    relative,
                    class_node,
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                ):
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message="injects diwire.Container outside delivery lifecycle",
                            symbol=class_node.name,
                        )
                    )
        return tuple(violations)
