from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    ArchitectureContext,
    annotation_name,
    call_from_expression,
    call_is_rooted_in_self_attributes,
    class_definition_base_index,
    class_injected_repository_field_names_at,
    execute_methods_with_classes,
    expression_is_rooted_in_names,
    repository_result_variable_names,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    violation,
)


class UseCasesDoNotImportOrReturnEntitiesRule(ArchitectureRuleBase):
    """Prevent use cases from exposing persistence entities as application results.

    Use cases may coordinate repositories internally, but delivery-facing results
    should be DTOs rather than entities or raw repository return values.
    """

    id: SpecxRuleId = SpecxRuleId.USE_CASES_DO_NOT_IMPORT_OR_RETURN_ENTITIES

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in (context.src_root / "core").glob("*/use_cases/**/*.py"):
            if path.name == "__init__.py" or path not in context.ast_project.files:
                continue
            tree = context.tree(path)
            aliases = context.aliases(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if "entities" in alias.name.split("."):
                            violations.append(
                                violation(self.id, path=path, message=f"imports {alias.name}"),
                            )
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    imports_entity_module = "entities" in module.split(".")
                    imports_entity_name = any(alias.name.endswith("Entity") for alias in node.names)
                    if imports_entity_module or (node.level > 0 and imports_entity_name):
                        violations.append(
                            violation(self.id, path=path, message=f"imports {module}"),
                        )

            for class_node, execute in execute_methods_with_classes(tree):
                repository_fields = class_injected_repository_field_names_at(
                    class_node,
                    aliases,
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                )
                return_annotation = annotation_name(execute.returns, aliases)
                if "Entity" in return_annotation:
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message=f"execute returns {return_annotation}",
                            symbol=class_node.name,
                        ),
                    )
                repository_results = repository_result_variable_names(
                    execute,
                    self_attribute_names=repository_fields,
                )
                for return_node in ast.walk(execute):
                    if not isinstance(return_node, ast.Return):
                        continue
                    if (
                        isinstance(return_node.value, ast.Name)
                        and return_node.value.id in repository_results
                    ):
                        violations.append(
                            violation(
                                self.id,
                                path=path,
                                message="returns repository result directly",
                                symbol=class_node.name,
                            ),
                        )
                    if expression_is_rooted_in_names(return_node.value, repository_results):
                        violations.append(
                            violation(
                                self.id,
                                path=path,
                                message="returns repository result expression",
                                symbol=class_node.name,
                            ),
                        )
                    call = call_from_expression(return_node.value)
                    if call is not None and call_is_rooted_in_self_attributes(
                        call, repository_fields
                    ):
                        violations.append(
                            violation(
                                self.id,
                                path=path,
                                message="returns repository call directly",
                                symbol=class_node.name,
                            ),
                        )
        return tuple(violations)
