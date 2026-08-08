from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_inherited_property_components_follow_c3_and_fresh_properties_shadow_all(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/properties.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class AmbientGetterMixin:\n"
        "    @property\n"
        "    def now(self) -> float: return time.time()\n"
        "    @now.setter\n"
        "    def now(self, value: float) -> None:\n"
        "        self._now = value + time.monotonic()\n\n"
        "class SetterOverrideService(AmbientGetterMixin, BaseEffectService):\n"
        "    @AmbientGetterMixin.now.setter\n"
        "    def now(self, value: float) -> None: self._now = value\n\n"
        "class FreshPropertyService(AmbientGetterMixin, BaseEffectService):\n"
        "    @property\n"
        "    def now(self) -> float: return 1.0\n\n"
        "class AmbientSetterMixin:\n"
        "    @property\n"
        "    def value(self) -> float: return 1.0\n"
        "    @value.setter\n"
        "    def value(self, new_value: float) -> None:\n"
        "        self._value = new_value + time.perf_counter()\n\n"
        "class GetterOverrideService(AmbientSetterMixin, BaseEffectService):\n"
        "    @AmbientSetterMixin.value.getter\n"
        "    def value(self) -> float: return self._value\n",
    )

    report = _check_selected(
        tmp_path,
        {
            SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
            SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS,
        },
    )

    assert len(report.violations) == 2
    assert {item.symbol for item in report.violations} == {
        "GetterOverrideService",
        "SetterOverrideService",
    }
    messages = "\n".join(item.message for item in report.violations)
    assert "time.time" in messages
    assert "time.perf_counter" in messages
    assert "time.monotonic" not in messages
    assert all(
        item.rule_id is SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS
        for item in report.violations
    )


def test_inherited_property_components_remain_use_case_behavior(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/result.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def helper() -> int: return 1\n\n"
        "class ResultMixin:\n"
        "    @property\n"
        "    def result(self) -> int: return 1\n"
        "    @result.setter\n"
        "    def result(self, value: int) -> None:\n"
        "        self._result = helper() + value\n\n"
        "class GetterOverrideUseCase(ResultMixin, BaseUseCase):\n"
        "    @ResultMixin.result.getter\n"
        "    def result(self) -> int: return self._result\n\n"
        "class FreshPropertyUseCase(ResultMixin, BaseUseCase):\n"
        "    @property\n"
        "    def result(self) -> int: return self._result\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert len(report.violations) == 1
    assert report.violations[0].symbol == "GetterOverrideUseCase"
    assert "helper" in report.violations[0].message


def test_callable_classification_recurses_through_composite_type_aliases(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "contracts.py"),
        "from typing import Annotated, Callable, Optional, TypeAlias, Union\n\n"
        "OptionalFormatter: TypeAlias = Optional[Callable[[str], str]]\n"
        "UnionFormatter: TypeAlias = Union[int, Callable[[str], str]]\n"
        "QuotedFormatter: TypeAlias = (\n"
        "    \"Annotated[Optional[Callable[[str], str]], 'formatter']\"\n"
        ")\n\n"
        "class PrimaryWorker:\n"
        "    def run(self, *, value: str) -> str: return value\n"
        "class BackupWorker:\n"
        "    def run(self, *, value: str) -> str: return value\n"
        "WorkerPort: TypeAlias = Union[PrimaryWorker, BackupWorker]\n",
    )
    _write(
        _source(tmp_path, "core/orders/use_cases/format_order.py"),
        "from collections.abc import Callable\n"
        "from diwire import Injected\n"
        "from demo_service.contracts import (\n"
        "    OptionalFormatter, QuotedFormatter, UnionFormatter, WorkerPort,\n"
        ")\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class FormatOrderUseCase(BaseUseCase):\n"
        "    direct: Injected[Callable[[str], str] | None]\n"
        "    optional: Injected[OptionalFormatter]\n"
        "    union: Injected[UnionFormatter]\n"
        "    quoted: 'Injected[QuotedFormatter]'\n"
        "    worker: Injected[WorkerPort]\n"
        "    def execute(self, *, value: str) -> str:\n"
        "        self.worker.run(value=value)\n"
        "        return self.direct(self.optional(self.union(self.quoted(value))))\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert len(report.violations) == 4
    messages = "\n".join(item.message for item in report.violations)
    assert "self.direct" in messages
    assert "self.optional" in messages
    assert "self.union" in messages
    assert "self.quoted" in messages
    assert "self.worker.run" not in messages


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
