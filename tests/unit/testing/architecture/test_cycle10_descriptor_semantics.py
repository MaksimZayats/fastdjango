from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_qualified_accessor_uses_explicit_non_first_descriptor_owner(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/selected_property.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class AmbientLeftMixin:\n"
        "    @property\n"
        "    def value(self) -> float: return time.time()\n\n"
        "class SafeRightMixin:\n"
        "    @property\n"
        "    def value(self) -> float: return 1.0\n\n"
        "class SafeService(AmbientLeftMixin, SafeRightMixin, BaseEffectService):\n"
        "    @SafeRightMixin.value.setter\n"
        "    def value(self, new_value: float) -> None: self._value = new_value\n\n"
        "class SafeLeftMixin:\n"
        "    @property\n"
        "    def value(self) -> float: return 1.0\n\n"
        "class AmbientRightMixin:\n"
        "    @property\n"
        "    def value(self) -> float: return time.monotonic()\n\n"
        "class AmbientService(SafeLeftMixin, AmbientRightMixin, BaseEffectService):\n"
        "    @AmbientRightMixin.value.setter\n"
        "    def value(self, new_value: float) -> None: self._value = new_value\n",
    )

    report = _check_selected(
        tmp_path,
        {
            SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
            SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS,
        },
    )

    assert len(report.violations) == 1
    assert report.violations[0].symbol == "AmbientService"
    assert "time.monotonic" in report.violations[0].message
    assert "time.time" not in report.violations[0].message


def test_use_case_qualified_accessor_uses_explicit_descriptor_owner(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/selected_property.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def helper() -> int: return 1\n\n"
        "class HelperLeftMixin:\n"
        "    @property\n"
        "    def result(self) -> int: return 1\n"
        "    @result.setter\n"
        "    def result(self, value: int) -> None: self._result = helper() + value\n\n"
        "class SafeRightMixin:\n"
        "    @property\n"
        "    def result(self) -> int: return 1\n\n"
        "class SafeUseCase(HelperLeftMixin, SafeRightMixin, BaseUseCase):\n"
        "    @SafeRightMixin.result.getter\n"
        "    def result(self) -> int: return self._result\n\n"
        "class SafeLeftMixin:\n"
        "    @property\n"
        "    def result(self) -> int: return 1\n\n"
        "class HelperRightMixin:\n"
        "    @property\n"
        "    def result(self) -> int: return 1\n"
        "    @result.setter\n"
        "    def result(self, value: int) -> None: self._result = helper() + value\n\n"
        "class HelperUseCase(SafeLeftMixin, HelperRightMixin, BaseUseCase):\n"
        "    @HelperRightMixin.result.getter\n"
        "    def result(self) -> int: return self._result\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert len(report.violations) == 1
    assert report.violations[0].symbol == "HelperUseCase"
    assert "helper" in report.violations[0].message


def test_property_abstractness_aggregates_effective_accessor_components(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/abstract_properties.py"),
        "import time\n"
        "from abc import abstractmethod\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class AbstractGetterService(BaseEffectService):\n"
        "    @property\n"
        "    @abstractmethod\n"
        "    def now(self) -> float: return time.time()\n"
        "    @now.setter\n"
        "    def now(self, value: float) -> None: self._now = value\n\n"
        "class ConcreteGetterService(AbstractGetterService):\n"
        "    @AbstractGetterService.now.getter\n"
        "    def now(self) -> float: return 1.0\n\n"
        "class AbstractSetterService(BaseEffectService):\n"
        "    @property\n"
        "    def value(self) -> float: return time.monotonic()\n"
        "    @value.setter\n"
        "    @abstractmethod\n"
        "    def value(self, new_value: float) -> None: ...\n\n"
        "class ConcreteSetterService(AbstractSetterService):\n"
        "    @AbstractSetterService.value.setter\n"
        "    def value(self, new_value: float) -> None: self._value = new_value\n",
    )

    report = _check_selected(
        tmp_path,
        {
            SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
            SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS,
        },
    )

    assert len(report.violations) == 1
    assert report.violations[0].symbol == "ConcreteSetterService"
    assert "time.monotonic" in report.violations[0].message
    assert "time.time" not in report.violations[0].message


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
