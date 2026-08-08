from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_literal_branches_select_property_and_staticmethod_aliases(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/literal_property.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "def custom(function: object) -> object: return object()\n\n"
        "class ClockService(BaseEffectService):\n"
        "    if True:\n"
        "        descriptor = property\n"
        "    else:\n"
        "        descriptor = custom\n"
        "    now = descriptor(lambda self: time.time())\n",
    )
    _write(
        _source(tmp_path, "core/orders/use_cases/literal_staticmethod.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def custom(function: object) -> object: return object()\n\n"
        "class StaticUseCase(BaseUseCase):\n"
        "    if False:\n"
        "        wrapper = custom\n"
        "    else:\n"
        "        wrapper = staticmethod\n"
        "    execute = wrapper(lambda: len(()))\n",
    )

    report = _check_selected(
        tmp_path,
        {
            SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
            SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
        },
    )

    assert {item.symbol for item in report.violations} == {
        "ClockService",
        "StaticUseCase",
    }


def test_type_checking_branches_select_classmethod_aliases(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/type_checking_classmethod.py"),
        "from typing import TYPE_CHECKING\n"
        "from typing_extensions import TYPE_CHECKING as EXT_TYPE_CHECKING\n"
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "def custom(function: object) -> object: return object()\n\n"
        "class TypingService(BasePureService):\n"
        "    if TYPE_CHECKING:\n"
        "        wrapper = custom\n"
        "    else:\n"
        "        wrapper = classmethod\n"
        "    run = wrapper(lambda cls, value: value)\n\n"
        "class ExtensionsService(BasePureService):\n"
        "    if EXT_TYPE_CHECKING:\n"
        "        wrapper = custom\n"
        "    else:\n"
        "        wrapper = classmethod\n"
        "    run = wrapper(lambda cls, value: value)\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS,
    )

    assert {item.symbol for item in report.violations} == {
        "ExtensionsService.run",
        "TypingService.run",
    }
    assert all("['value']" in item.message for item in report.violations)


def test_while_false_selects_else_wrapper_binding(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/while_false.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def custom(function: object) -> object: return object()\n\n"
        "class StaticUseCase(BaseUseCase):\n"
        "    while False:\n"
        "        wrapper = custom\n"
        "    else:\n"
        "        wrapper = staticmethod\n"
        "    execute = wrapper(lambda: sum(()))\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert len(report.violations) == 1
    assert report.violations[0].symbol == "StaticUseCase"
    assert "builtins.sum" in report.violations[0].message


def test_unknown_wrapper_condition_remains_conservative(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/unknown_condition.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "USE_BUILTIN = True\n"
        "def custom(function: object) -> object: return object()\n\n"
        "class StaticUseCase(BaseUseCase):\n"
        "    if USE_BUILTIN:\n"
        "        wrapper = staticmethod\n"
        "    else:\n"
        "        wrapper = custom\n"
        "    execute = wrapper(lambda: len(()))\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert report.violations == ()


def _check_only(
    project_root: Path,
    rule_id: SpecxRuleId,
) -> SpecxArchitectureReport:
    return _check_selected(project_root, {rule_id})


def _check_selected(
    project_root: Path,
    rule_ids: set[SpecxRuleId],
) -> SpecxArchitectureReport:
    return check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=project_root,
            package_name="demo_service",
            disabled_rules=frozenset(
                candidate for candidate in SpecxRuleId if candidate not in rule_ids
            ),
        )
    )


def _source(project_root: Path, relative: str) -> Path:
    return project_root / "src/demo_service" / relative


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
