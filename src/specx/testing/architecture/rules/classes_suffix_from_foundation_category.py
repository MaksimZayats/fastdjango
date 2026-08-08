from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    ArchitectureContext,
    category_suffix_from_base_at,
    class_definition_base_index,
    nearest_foundation_base_names_for_class_at,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    violation,
)


class ClassesUseSuffixFromMostSpecificFoundationCategoryRule(ArchitectureRuleBase):
    """Require class names to use the suffix implied by their foundation base.

    Naming from the most-specific foundation category keeps class purpose visible
    and catches accidental use of broad or misleading base classes.
    """

    id: SpecxRuleId = SpecxRuleId.CLASSES_USE_SUFFIX_FROM_MOST_SPECIFIC_FOUNDATION_CATEGORY

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        definition_index = class_definition_base_index(context)
        violations: list[SpecxArchitectureViolation] = []
        for path in context.source_paths():
            if "foundation" in path.relative_to(context.src_root).parts:
                continue
            tree = context.tree(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                foundation_bases = nearest_foundation_base_names_for_class_at(
                    node,
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                )
                suffixes = {
                    suffix
                    for found_base in foundation_bases
                    if (
                        suffix := category_suffix_from_base_at(
                            found_base,
                            source_path=path,
                            context=context,
                            definition_index=definition_index,
                        )
                    )
                    is not None
                }
                if not suffixes:
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message="has no recognized category",
                            symbol=node.name,
                            node=node,
                        )
                    )
                    continue
                if not any(node.name.endswith(suffix) for suffix in suffixes):
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message=f"expected {sorted(suffixes)}",
                            symbol=node.name,
                            node=node,
                        )
                    )
        return tuple(violations)
