from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_injected_repository_field_names_at,
    class_injected_unit_of_work_manager_field_names,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    forbidden_use_case_persistence_dependency_fields,
    is_use_case_class_at,
    repository_calls_outside_manager_owned_uow,
    use_case_imports_persistence_infrastructure,
    violation,
)


class UseCasesDoNotInjectRepositoriesOrInfrastructureRule(ArchitectureRuleBase):
    """Require persistence access to flow through use-case-owned UoW scopes.

    Use cases should inject services and UoW managers, not repositories,
    SQLAlchemy resources, or concrete infrastructure adapters that bypass
    transaction ownership.
    """

    id: SpecxRuleId = SpecxRuleId.USE_CASES_DO_NOT_INJECT_REPOSITORIES_OR_INFRASTRUCTURE

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in (context.src_root / "core").glob("*/use_cases/**/*.py"):
            if path.name == "__init__.py" or path not in context.ast_project.files:
                continue

            tree = context.tree(path)
            aliases = context.aliases(path)
            for module in sorted(context.imports(path)):
                if use_case_imports_persistence_infrastructure(module):
                    violations.append(violation(self.id, path=path, message=f"imports {module}"))

            for class_node in ast.walk(tree):
                if not isinstance(class_node, ast.ClassDef):
                    continue
                if not is_use_case_class_at(
                    class_node,
                    path=path,
                    context=context,
                    definition_index=definition_index,
                ):
                    continue

                messages: list[str] = []
                forbidden_fields = forbidden_use_case_persistence_dependency_fields(
                    class_node,
                    aliases,
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                )
                if forbidden_fields:
                    messages.append(f"injects {forbidden_fields}")

                manager_fields = class_injected_unit_of_work_manager_field_names(
                    class_node,
                    aliases,
                )
                repository_fields = class_injected_repository_field_names_at(
                    class_node,
                    aliases,
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                )
                for child in class_node.body:
                    if (
                        isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef))
                        and child.name == "execute"
                    ):
                        bad_calls = repository_calls_outside_manager_owned_uow(
                            child,
                            manager_fields=manager_fields,
                            repository_fields=repository_fields,
                        )
                        if bad_calls:
                            messages.append(
                                f"calls repositories outside manager-owned UoW {sorted(bad_calls)}",
                            )

                if messages:
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message="; ".join(messages),
                            symbol=class_node.name,
                        )
                    )
        return tuple(violations)
