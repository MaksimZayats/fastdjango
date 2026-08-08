from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    READ_SERVICE_FORBIDDEN_CALL_NAMES,
    READ_SERVICE_FORBIDDEN_CALL_PREFIXES,
    ArchitectureContext,
    active_repository_names,
    call_is_rooted_in_names,
    calls_forbidden_method,
    class_definition_base_index,
    class_has_foundation_base_at,
    class_injected_unit_of_work_manager_field_names,
    repository_mutator_method_names,
    unit_of_work_argument_names,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    violation,
)


class ReadServicesDoNotPerformWritesOrOwnTransactionsRule(ArchitectureRuleBase):
    """Keep read services from writing data or owning transactions.

    Read services may compose read operations, but use cases own transaction
    lifecycle and write operations belong in command flows or effect services.
    """

    id: SpecxRuleId = SpecxRuleId.READ_SERVICES_DO_NOT_PERFORM_WRITES_OR_OWN_TRANSACTIONS

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        mutator_names = repository_mutator_method_names(context)
        for path in context.core_service_paths():
            tree = context.tree(path)
            aliases = context.aliases(path)
            read_services = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)
                and class_has_foundation_base_at(
                    node,
                    "BaseReadService",
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                )
            ]
            for class_node in read_services:
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
                    uow_args = unit_of_work_argument_names(child, aliases)
                    repository_roots = uow_args | active_repository_names(
                        child, root_names=uow_args
                    )
                    for call in (node for node in ast.walk(child) if isinstance(node, ast.Call)):
                        call_method = call.func.attr if isinstance(call.func, ast.Attribute) else ""
                        if calls_forbidden_method(
                            call,
                            READ_SERVICE_FORBIDDEN_CALL_NAMES,
                            READ_SERVICE_FORBIDDEN_CALL_PREFIXES,
                        ):
                            violations.append(
                                violation(
                                    self.id,
                                    path=path,
                                    message=f"calls {call_method}",
                                    symbol=class_node.name,
                                )
                            )
                        if (
                            isinstance(call.func, ast.Attribute)
                            and call.func.attr in mutator_names
                            and call_is_rooted_in_names(call, repository_roots)
                        ):
                            violations.append(
                                violation(
                                    self.id,
                                    path=path,
                                    message=f"calls repository mutator {call.func.attr}",
                                    symbol=class_node.name,
                                )
                            )
        return tuple(violations)
