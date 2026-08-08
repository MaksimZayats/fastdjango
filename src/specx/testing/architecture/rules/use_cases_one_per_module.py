from __future__ import annotations

import ast

from specx.testing.architecture.context import ArchitectureContext, class_definition_base_index
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    is_use_case_class_at,
    violation,
)


class UseCaseModulesDefineOneUseCaseRule(ArchitectureRuleBase):
    """Require each managed use-case module to define only one use case.

    One use case per module gives project management commands a stable
    component/module resource ID without introducing a separate registry.
    """

    id: SpecxRuleId = SpecxRuleId.USE_CASE_MODULES_DEFINE_ONE_USE_CASE

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in (context.src_root / "core").glob("*/use_cases/**/*.py"):
            if path.name == "__init__.py" or path not in context.ast_project.files:
                continue
            use_cases = [
                node
                for node in context.tree(path).body
                if isinstance(node, ast.ClassDef)
                and is_use_case_class_at(
                    node,
                    path=path,
                    context=context,
                    definition_index=definition_index,
                )
            ]
            if len(use_cases) != 1:
                violations.append(
                    violation(
                        self.id,
                        path=path,
                        message=f"module defines {len(use_cases)} use cases; expected one",
                        node=use_cases[1] if use_cases else None,
                    )
                )
        return tuple(violations)
