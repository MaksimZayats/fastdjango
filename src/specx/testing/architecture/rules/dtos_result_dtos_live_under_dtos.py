from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_suffix_from_base,
    nearest_foundation_base_names_for_class_at,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    violation,
)


class ResultDTOClassesLiveUnderScopeDTOsPackageRule(ArchitectureRuleBase):
    """Require DTO classes to live in the scope `dtos` package.

    Use-case output DTOs are application boundary objects and should not be
    hidden inside use-case modules or other implementation packages.
    """

    id: SpecxRuleId = SpecxRuleId.RESULT_DTO_CLASSES_LIVE_UNDER_SCOPE_DTOS_PACKAGE

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in (context.src_root / "core").glob("*/**/*.py"):
            if path.name == "__init__.py" or path not in context.ast_project.files:
                continue
            relative_parts = path.relative_to(context.src_root / "core").parts
            if len(relative_parts) < 2:
                continue
            tree = context.tree(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                nearest_bases = nearest_foundation_base_names_for_class_at(
                    node,
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                )
                is_dto = any(
                    class_suffix_from_base(found_base.rsplit(".", maxsplit=1)[-1]) == "DTO"
                    for found_base in nearest_bases
                )
                if is_dto and relative_parts[1] != "dtos":
                    violations.append(
                        violation(self.id, path=path, message="DTO outside dtos", symbol=node.name)
                    )
        return tuple(violations)
