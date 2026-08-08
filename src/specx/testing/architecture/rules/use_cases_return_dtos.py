from __future__ import annotations

from specx.testing.architecture.context import (
    ArchitectureContext,
    annotation_name,
    class_definition_base_index,
    execute_methods_with_classes,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    is_use_case_class_at,
    violation,
)


class UseCasesReturnDTOsRule(ArchitectureRuleBase):
    """Require use cases to return DTOs instead of entities or raw values.

    This keeps delivery-facing application results explicit and stable as the
    internal entity or repository model evolves.
    """

    id: SpecxRuleId = SpecxRuleId.USE_CASES_RETURN_DTOS

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
                return_annotation = annotation_name(execute.returns, aliases)
                if "DTO" not in return_annotation:
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message=f"execute returns {return_annotation}",
                            symbol=class_node.name,
                        ),
                    )
        return tuple(violations)
