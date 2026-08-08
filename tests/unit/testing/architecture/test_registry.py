from __future__ import annotations

import importlib
import inspect
import pkgutil
from inspect import getdoc
from pathlib import Path
from typing import cast

import pytest

from specx.testing.architecture import (
    ArchitectureContext,
    BaseRule,
    SpecxArchitectureViolation,
    SpecxRuleId,
    SpecxRuleRegistryError,
)
from specx.testing.architecture.guidance import BUILTIN_RULE_GUIDANCE
from specx.testing.architecture.models import ArchitectureRuleType
from specx.testing.architecture.registry import SpecxRuleRegistry
from specx.testing.architecture.rules import BUILT_IN_RULES


class DuplicateCoreRule(BaseRule[SpecxRuleId, ArchitectureContext, SpecxArchitectureViolation]):
    """Duplicate rule used to prove registry IDs remain unique."""

    id = BUILT_IN_RULES[0]().id

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        return ()


def test_registry_rejects_duplicate_rule_ids() -> None:
    with pytest.raises(SpecxRuleRegistryError, match="duplicate architecture rule id"):
        SpecxRuleRegistry.build(extra_rules=(DuplicateCoreRule,))


def test_every_builtin_rule_has_useful_docstring() -> None:
    missing = [
        rule.__name__
        for rule in BUILT_IN_RULES
        if (docstring := getdoc(rule)) is None or len(docstring.split()) < 8
    ]

    assert missing == []


def test_builtin_rule_ids_are_unique() -> None:
    rule_ids = [str(rule().id) for rule in BUILT_IN_RULES]

    assert len(rule_ids) == len(set(rule_ids))
    assert set(rule_ids) == {str(rule_id) for rule_id in SpecxRuleId}


def test_rule_package_has_exactly_one_registered_rule_per_module() -> None:
    package = importlib.import_module("specx.testing.architecture.rules")
    discovered_rules: list[ArchitectureRuleType] = []
    module_names = sorted(
        module.name
        for module in pkgutil.iter_modules(package.__path__)
        if not module.name.startswith("_")
    )
    for module_name in module_names:
        module = importlib.import_module(f"{package.__name__}.{module_name}")
        module_rules = [
            cast(ArchitectureRuleType, value)
            for _, value in inspect.getmembers(module, inspect.isclass)
            if value.__module__ == module.__name__ and issubclass(value, BaseRule)
        ]

        assert len(module_rules) == 1, module.__name__
        discovered_rules.extend(module_rules)

    assert set(discovered_rules) == set(BUILT_IN_RULES)


def test_rules_do_not_use_lossy_simple_name_inheritance_index() -> None:
    package = importlib.import_module("specx.testing.architecture.rules")
    package_root = Path(next(iter(package.__path__)))
    offenders = [
        path.name
        for path in package_root.glob("*.py")
        if "class_base_name_index" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_every_builtin_rule_has_selection_metadata() -> None:
    metadata = [rule.metadata() for rule in BUILT_IN_RULES]

    assert all(item.family in {"neutral", "fastapi"} for item in metadata)
    assert all(item.summary for item in metadata)
    assert {str(item.rule_id) for item in metadata if not item.default_enabled} == {
        str(SpecxRuleId.FASTAPI_ROOT_AGENTS_MD_DOCUMENTS_ENTRYPOINT),
        str(SpecxRuleId.PUBLIC_ROUTES_USE_FULL_API_V1_PATHS),
    }
    assert all(item.remediation for item in metadata)
    assert all(
        item.remediation is not None and not item.remediation.startswith("Address this rule:")
        for item in metadata
    )
    assert all("see the rule documentation" not in item.detection_boundary for item in metadata)
    assert all(
        item.documentation_url is not None
        and item.documentation_url.startswith(
            "https://specx.dev/docs/reference/architecture-rules/#"
        )
        for item in metadata
    )
    assert set(BUILTIN_RULE_GUIDANCE) == {str(item.rule_id) for item in metadata}


def test_all_selector_enables_every_builtin_rule() -> None:
    registry = SpecxRuleRegistry.build()

    enabled = registry.enabled_rules(
        disabled_rules=frozenset(),
        select=frozenset({"ALL"}),
    )

    assert enabled == BUILT_IN_RULES


def test_explicit_empty_select_disables_default_rules() -> None:
    registry = SpecxRuleRegistry.build()

    enabled = registry.enabled_rules(
        disabled_rules=frozenset(),
        select=frozenset(),
    )

    assert enabled == ()
