from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    CAPABILITY_FORBIDDEN_NAME_SUFFIXES,
    ArchitectureContext,
    class_definition_base_index,
    class_has_foundation_base_at,
    class_unit_of_work_field_names,
    context_self_fields,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    violation,
)


class CapabilitiesDoNotOwnWorkflowsOrOtherPortRolesRule(ArchitectureRuleBase):
    """Prevent capabilities from pretending to be workflows or ports.

    A capability should be small and replaceable; it must not own UoW lifecycle
    or take on repository, gateway, use-case, service, helper, or manager roles.
    """

    id: SpecxRuleId = SpecxRuleId.CAPABILITIES_DO_NOT_OWN_WORKFLOWS_OR_OTHER_PORT_ROLES

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in context.source_paths():
            if "foundation" in path.relative_to(context.src_root).parts:
                continue
            tree = context.tree(path)
            aliases = context.aliases(path)
            for class_node in [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]:
                if not class_has_foundation_base_at(
                    class_node,
                    "BaseCapability",
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                ):
                    continue
                role_name = class_node.name.removesuffix("Capability")
                forbidden_suffix = next(
                    (
                        suffix
                        for suffix in CAPABILITY_FORBIDDEN_NAME_SUFFIXES
                        if class_node.name.endswith(suffix) or role_name.endswith(suffix)
                    ),
                    None,
                )
                if forbidden_suffix is not None:
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message=f"uses {forbidden_suffix} role name",
                            symbol=class_node.name,
                        )
                    )
                for incompatible_base in ("BaseRepository", "BaseGateway", "BaseUseCase"):
                    if class_has_foundation_base_at(
                        class_node,
                        incompatible_base,
                        source_path=path,
                        context=context,
                        definition_index=definition_index,
                    ):
                        violations.append(
                            violation(
                                self.id,
                                path=path,
                                message=f"also inherits {incompatible_base}",
                                symbol=class_node.name,
                            )
                        )
                uow_fields = class_unit_of_work_field_names(class_node, aliases)
                if uow_fields:
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message=f"depends on {sorted(uow_fields)}",
                            symbol=class_node.name,
                        )
                    )
                for child in class_node.body:
                    if not isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef)):
                        continue
                    context_fields = context_self_fields(child, uow_fields)
                    if context_fields:
                        violations.append(
                            violation(
                                self.id,
                                path=path,
                                message=f"opens {sorted(context_fields)}",
                                symbol=class_node.name,
                            )
                        )
        return tuple(violations)
