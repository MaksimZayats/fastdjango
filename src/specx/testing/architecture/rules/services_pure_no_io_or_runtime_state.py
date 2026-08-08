from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    PURE_SERVICE_FORBIDDEN_DEPENDENCY_FRAGMENTS,
    PURE_SERVICE_FORBIDDEN_IMPORT_PARTS,
    PURE_SERVICE_FORBIDDEN_IMPORT_ROOTS,
    ArchitectureContext,
    class_definition_base_index,
    class_dependency_annotations,
    class_has_foundation_base_at,
    forbidden_dependency_fragments,
    module_has_forbidden_parts,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    violation,
)


class PureServicesDoNotDependOnIOOrRuntimeStateRule(ArchitectureRuleBase):
    """Keep pure services deterministic and independent from IO or runtime state.

    Pure services should be easy to unit test directly and must not depend on
    repositories, gateways, settings, clocks, randomness, or technical libraries.
    """

    id: SpecxRuleId = SpecxRuleId.PURE_SERVICES_DO_NOT_DEPEND_ON_IO_OR_RUNTIME_STATE

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in context.core_service_paths():
            tree = context.tree(path)
            aliases = context.aliases(path)
            pure_services = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)
                and class_has_foundation_base_at(
                    node,
                    "BasePureService",
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                )
            ]
            if not pure_services:
                continue
            for module in context.imports(path):
                if module_has_forbidden_parts(
                    module,
                    roots=PURE_SERVICE_FORBIDDEN_IMPORT_ROOTS,
                    parts=PURE_SERVICE_FORBIDDEN_IMPORT_PARTS,
                ):
                    violations.append(violation(self.id, path=path, message=f"imports {module}"))
            for class_node in pure_services:
                for dependency_name in class_dependency_annotations(class_node, aliases):
                    fragments = forbidden_dependency_fragments(
                        dependency_name,
                        PURE_SERVICE_FORBIDDEN_DEPENDENCY_FRAGMENTS,
                    )
                    if fragments:
                        violations.append(
                            violation(
                                self.id,
                                path=path,
                                message=f"uses {dependency_name}",
                                symbol=class_node.name,
                            )
                        )
        return tuple(violations)
