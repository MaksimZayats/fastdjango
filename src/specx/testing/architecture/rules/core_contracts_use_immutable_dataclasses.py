from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_has_foundation_base_at,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import ArchitectureRuleBase, violation


class CoreContractsUseImmutableDataclassesRule(ArchitectureRuleBase):
    """Require project core contracts and entities to use immutable keyword-only dataclasses."""

    id: SpecxRuleId = SpecxRuleId.CORE_CONTRACTS_USE_IMMUTABLE_DATACLASSES
    remediation: str | None = (
        "Add `@dataclass(frozen=True, kw_only=True, slots=True)` to the project class."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        definition_index = class_definition_base_index(context)
        required_bases = {"BaseCommand", "BaseQuery", "BaseDTO", "BaseEntity"}
        findings: list[SpecxArchitectureViolation] = []
        for path in context.source_paths():
            for node in ast.walk(context.tree(path)):
                if not isinstance(node, ast.ClassDef) or not any(
                    class_has_foundation_base_at(
                        node,
                        base,
                        source_path=path,
                        context=context,
                        definition_index=definition_index,
                    )
                    for base in required_bases
                ):
                    continue
                decorator = next(
                    (
                        item
                        for item in node.decorator_list
                        if (
                            isinstance(item, ast.Name)
                            and context.qualified_name(path, item).endswith("dataclasses.dataclass")
                        )
                        or (
                            isinstance(item, ast.Call)
                            and context.qualified_name(path, item.func).endswith(
                                "dataclasses.dataclass"
                            )
                        )
                    ),
                    None,
                )
                valid = isinstance(decorator, ast.Call) and all(
                    any(
                        keyword.arg == flag
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                        for keyword in decorator.keywords
                    )
                    for flag in ("frozen", "kw_only", "slots")
                )
                if not valid:
                    findings.append(
                        violation(
                            self.id,
                            path=path,
                            symbol=node.name,
                            node=node,
                            message="requires @dataclass(frozen=True, kw_only=True, slots=True)",
                        )
                    )
        return tuple(findings)
