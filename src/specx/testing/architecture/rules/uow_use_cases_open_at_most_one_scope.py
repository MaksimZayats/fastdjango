from __future__ import annotations

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_injected_unit_of_work_manager_field_names,
    execute_methods_with_classes,
    uow_manager_context_count,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    is_use_case_class_at,
    violation,
)


class UseCasesOpenAtMostOneUnitOfWorkScopeRule(ArchitectureRuleBase):
    """Limit each use-case execution to one unit-of-work manager scope.

    Repeated transaction scopes in one use-case make lifecycle and rollback
    behavior hard to reason about.
    """

    id: SpecxRuleId = SpecxRuleId.USE_CASES_OPEN_AT_MOST_ONE_UNIT_OF_WORK_SCOPE

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in (context.src_root / "core").glob("*/use_cases/**/*.py"):
            if path.name == "__init__.py" or path not in context.ast_project.files:
                continue
            tree = context.tree(path)
            aliases = context.aliases(path)
            for class_node, execute in execute_methods_with_classes(tree):
                if not is_use_case_class_at(
                    class_node,
                    path=path,
                    context=context,
                    definition_index=definition_index,
                ):
                    continue
                manager_fields = class_injected_unit_of_work_manager_field_names(
                    class_node,
                    aliases,
                )
                count = uow_manager_context_count(execute, manager_fields)
                if count > 1:
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message=f"opens {count} UoWs",
                            symbol=class_node.name,
                        )
                    )
        return tuple(violations)
