from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_property_constructor_maps_positional_and_keyword_project_functions(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/property_functions.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "def read_now(_self: object) -> float: return time.time()\n"
        "def write_now(_self: object, value: float) -> None: pass\n\n"
        "class ClockService(BaseEffectService):\n"
        "    now = property(read_now, write_now)\n",
    )
    _write(
        _source(tmp_path, "core/orders/use_cases/property_functions.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def read_result(_self: object) -> int: return len(())\n\n"
        "class ResultUseCase(BaseUseCase):\n"
        "    result = property(fget=read_result)\n",
    )

    report = _check_selected(
        tmp_path,
        {
            SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
            SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS,
            SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
        },
    )

    assert len(report.violations) == 2
    assert {item.symbol for item in report.violations} == {
        "ClockService",
        "ResultUseCase",
    }
    assert all(
        item.rule_id is not SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS
        for item in report.violations
    )


def test_property_constructor_inline_lambdas_are_behavior_and_shadow_inherited(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/property_lambdas.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class AmbientMixin:\n"
        "    @property\n"
        "    def value(self) -> float: return time.time()\n\n"
        "class SafeService(AmbientMixin, BaseEffectService):\n"
        "    value = property(lambda self: 1.0)\n\n"
        "class AmbientService(BaseEffectService):\n"
        "    value = property(fget=lambda self: time.monotonic())\n",
    )
    _write(
        _source(tmp_path, "core/orders/use_cases/property_lambdas.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class ResultUseCase(BaseUseCase):\n"
        "    result = property(lambda self: len(()))\n",
    )

    report = _check_selected(
        tmp_path,
        {
            SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
            SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
        },
    )

    assert len(report.violations) == 2
    assert {item.symbol for item in report.violations} == {
        "AmbientService",
        "ResultUseCase",
    }
    messages = "\n".join(item.message for item in report.violations)
    assert "time.monotonic" in messages
    assert "builtins.len" in messages
    assert "time.time" not in messages


def test_property_constructor_abstractness_uses_accessor_components(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/abstract_property.py"),
        "import time\n"
        "from abc import abstractmethod\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "@abstractmethod\n"
        "def read_value(_self: object) -> float: return time.time()\n"
        "def write_value(_self: object, value: float) -> None: pass\n\n"
        "class AbstractService(BaseEffectService):\n"
        "    value = property(read_value, write_value)\n\n"
        "class ConcreteService(AbstractService):\n"
        "    value = property(lambda self: 1.0, write_value)\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
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
