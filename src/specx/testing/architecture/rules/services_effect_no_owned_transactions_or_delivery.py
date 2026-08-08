from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    EFFECT_SERVICE_FORBIDDEN_IMPORT_PARTS,
    EFFECT_SERVICE_FORBIDDEN_IMPORT_ROOTS,
    ArchitectureContext,
    annotation_name,
    class_definition_base_index,
    class_has_foundation_base_at,
    class_injected_unit_of_work_manager_field_names,
    module_has_forbidden_parts,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    violation,
)


class EffectServicesDoNotOwnTransactionsOrImportDeliveryRule(ArchitectureRuleBase):
    """Keep effect services inside use-case-owned transaction boundaries.

    Effect services may coordinate side effects, but they should not open UoWs,
    commit or roll back transactions, return entities, or import delivery code.
    """

    id: SpecxRuleId = SpecxRuleId.EFFECT_SERVICES_DO_NOT_OWN_TRANSACTIONS_OR_IMPORT_DELIVERY

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in context.core_service_paths():
            tree = context.tree(path)
            aliases = context.aliases(path)
            effect_services = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)
                and class_has_foundation_base_at(
                    node,
                    "BaseEffectService",
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                )
            ]
            if not effect_services:
                continue
            for module in context.imports(path):
                if module_has_forbidden_parts(
                    module,
                    roots=EFFECT_SERVICE_FORBIDDEN_IMPORT_ROOTS,
                    parts=EFFECT_SERVICE_FORBIDDEN_IMPORT_PARTS,
                ):
                    violations.append(violation(self.id, path=path, message=f"imports {module}"))
            for class_node in effect_services:
                manager_fields = class_injected_unit_of_work_manager_field_names(
                    class_node, aliases
                )
                if manager_fields:
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message=f"injects {sorted(manager_fields)}",
                            symbol=class_node.name,
                        )
                    )
                for child in class_node.body:
                    if not isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef)):
                        continue
                    return_annotation = annotation_name(child.returns, aliases)
                    if "Entity" in return_annotation:
                        violations.append(
                            violation(
                                self.id,
                                path=path,
                                message=f"returns {return_annotation}",
                                symbol=class_node.name,
                            )
                        )
                    for call in (node for node in ast.walk(child) if isinstance(node, ast.Call)):
                        if isinstance(call.func, ast.Attribute) and call.func.attr in {
                            "commit",
                            "rollback",
                        }:
                            violations.append(
                                violation(
                                    self.id,
                                    path=path,
                                    message=f"calls {call.func.attr}",
                                    symbol=class_node.name,
                                )
                            )
        return tuple(violations)
