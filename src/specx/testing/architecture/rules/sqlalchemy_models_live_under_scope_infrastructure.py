from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_has_foundation_base_at,
    class_has_sqlalchemy_mapping_at,
    class_is_statically_abstract_at,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import ArchitectureRuleBase, violation


class SQLAlchemyModelsLiveUnderScopeInfrastructureRule(ArchitectureRuleBase):
    """Place concrete SQLAlchemy models under their owning scope infrastructure package."""

    id: SpecxRuleId = SpecxRuleId.SQLALCHEMY_MODELS_LIVE_UNDER_SCOPE_INFRASTRUCTURE
    remediation: str | None = (
        "Move the concrete model under `core/<scope>/infrastructure/<technology>/`; "
        "keep only the project declarative base in the project foundation."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        definition_index = class_definition_base_index(context)
        findings: list[SpecxArchitectureViolation] = []
        for path in context.source_paths():
            relative = path.relative_to(context.src_root)
            correctly_placed = (
                len(relative.parts) >= 5
                and relative.parts[0] == "core"
                and relative.parts[2] == "infrastructure"
            )
            for node in ast.walk(context.tree(path)):
                if not isinstance(node, ast.ClassDef) or (
                    class_is_statically_abstract_at(
                        node,
                        source_path=path,
                        context=context,
                    )
                    and not class_has_sqlalchemy_mapping_at(
                        node,
                        source_path=path,
                        context=context,
                    )
                ):
                    continue
                is_specx_model = class_has_foundation_base_at(
                    node,
                    "BaseSQLAlchemyModel",
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                )
                is_raw_mapped_model = class_has_sqlalchemy_mapping_at(
                    node,
                    source_path=path,
                    context=context,
                ) and class_has_foundation_base_at(
                    node,
                    "sqlalchemy.orm.DeclarativeBase",
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                )
                if not correctly_placed and (is_specx_model or is_raw_mapped_model):
                    findings.append(
                        violation(
                            self.id,
                            path=path,
                            symbol=node.name,
                            node=node,
                            message="concrete SQLAlchemy model lives outside scope infrastructure",
                        )
                    )
        return tuple(findings)
