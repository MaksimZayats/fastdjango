from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    ArchitectureContext,
    annotation_name,
    class_definition_base_index,
    class_injected_unit_of_work_manager_field_names,
    injected_type_name,
    uow_manager_context_fields,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    is_use_case_class_at,
    violation,
)


class UseCasesInjectUnitOfWorkManagersRule(ArchitectureRuleBase):
    """Require persistence use cases to inject managers, not active UoWs or providers.

    A use case should receive an injected `*UnitOfWorkManager` and open the
    active unit of work inside `execute(...)`.
    """

    id: SpecxRuleId = SpecxRuleId.USE_CASES_INJECT_UNIT_OF_WORK_MANAGERS

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in (context.src_root / "core").glob("*/use_cases/**/*.py"):
            if path.name == "__init__.py" or path not in context.ast_project.files:
                continue
            tree = context.tree(path)
            aliases = context.aliases(path)
            for class_node in [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]:
                if not is_use_case_class_at(
                    class_node,
                    path=path,
                    context=context,
                    definition_index=definition_index,
                ):
                    continue
                injected_manager_fields = class_injected_unit_of_work_manager_field_names(
                    class_node,
                    aliases,
                )
                bad_dependency_fields: list[str] = []
                for child in class_node.body:
                    if not isinstance(child, ast.AnnAssign):
                        continue
                    annotation = annotation_name(child.annotation, aliases)
                    injected_name = injected_type_name(child.annotation, aliases)
                    field_name = child.target.id if isinstance(child.target, ast.Name) else ""
                    if "Provider" in annotation:
                        bad_dependency_fields.append(f"{field_name}:{annotation}")
                    if "UnitOfWork" in annotation and "UnitOfWorkManager" not in annotation:
                        bad_dependency_fields.append(f"{field_name}:{annotation}")
                    if "UnitOfWorkManager" in annotation:
                        if injected_name.endswith("UnitOfWorkManager"):
                            continue
                        bad_dependency_fields.append(f"{field_name}:{annotation}")
                for child in class_node.body:
                    if (
                        isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef))
                        and child.name == "execute"
                    ):
                        context_fields = uow_manager_context_fields(child, injected_manager_fields)
                        unknown_context_fields = context_fields - injected_manager_fields
                        if unknown_context_fields:
                            bad_dependency_fields.append(
                                "opens non-injected manager fields "
                                f"{sorted(unknown_context_fields)}",
                            )
                        if injected_manager_fields and not context_fields:
                            bad_dependency_fields.append("injects UoW manager but does not open it")
                if bad_dependency_fields:
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message=str(bad_dependency_fields),
                            symbol=class_node.name,
                        )
                    )
        return tuple(violations)
