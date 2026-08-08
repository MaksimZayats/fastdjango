from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    ArchitectureContext,
    active_repository_names,
    active_uow_names,
    annotation_name,
    call_is_rooted_in_names,
    call_is_rooted_in_self_attributes,
    class_definition_base_index,
    class_has_foundation_base_from_path,
    class_injected_repository_field_names_at,
    execute_methods_with_classes,
    repository_mutator_method_names,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    violation,
)


class QueryUseCasesDoNotCallRepositoryMutatorsRule(ArchitectureRuleBase):
    """Keep query use cases read-only by rejecting repository mutator calls.

    Query inputs promise observation rather than state change, so mutating
    repository calls should remain in command use cases.
    """

    id: SpecxRuleId = SpecxRuleId.QUERY_USE_CASES_DO_NOT_CALL_REPOSITORY_MUTATORS

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        mutator_names = repository_mutator_method_names(context)
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in (context.src_root / "core").glob("*/use_cases/**/*.py"):
            if path.name == "__init__.py" or path not in context.ast_project.files:
                continue
            tree = context.tree(path)
            aliases = context.aliases(path)
            for class_node, execute in execute_methods_with_classes(tree):
                if len(execute.args.kwonlyargs) != 1 or execute.args.kwonlyargs[0].arg != "query":
                    continue
                query_annotation = annotation_name(execute.args.kwonlyargs[0].annotation, aliases)
                if not class_has_foundation_base_from_path(
                    query_annotation,
                    "BaseQuery",
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                ):
                    continue
                repository_fields = class_injected_repository_field_names_at(
                    class_node,
                    aliases,
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                )
                repository_roots = active_uow_names(execute) | active_repository_names(
                    execute,
                    self_attribute_names=repository_fields,
                )
                mutator_calls = [
                    call.func.attr
                    for call in ast.walk(execute)
                    if isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr in mutator_names
                    and (
                        call_is_rooted_in_names(call, repository_roots)
                        or call_is_rooted_in_self_attributes(call, repository_fields)
                    )
                ]
                if mutator_calls:
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message=f"calls {sorted(set(mutator_calls))}",
                            symbol=class_node.name,
                        )
                    )
        return tuple(violations)
