from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_ambient_callable_defaults_follow_reaching_parameter_bindings(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/clock.py"),
        "import time\n"
        "from collections.abc import Callable\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "def safe_clock() -> float: return 1.0\n"
        "def other_safe_clock() -> float: return 2.0\n\n"
        "class ClockService(BaseEffectService):\n"
        "    def replaced(self, *, clock: Callable[[], float] = time.time) -> float:\n"
        "        clock = safe_clock\n"
        "        return clock()\n"
        "    def replaced_on_both_branches(\n"
        "        self, *, enabled: bool, clock: Callable[[], float] = time.time\n"
        "    ) -> float:\n"
        "        if enabled:\n"
        "            clock = safe_clock\n"
        "        else:\n"
        "            clock = other_safe_clock\n"
        "        return clock()\n"
        "    def maybe_replaced(\n"
        "        self, *, enabled: bool, clock: Callable[[], float] = time.time\n"
        "    ) -> float:\n"
        "        if enabled:\n"
        "            clock = safe_clock\n"
        "        return clock()\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    )

    assert len(report.violations) == 1
    assert report.violations[0].line == 25
    assert "time.time" in report.violations[0].message


def test_property_accessor_components_remain_effective_behavior(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/properties.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class GetterService(BaseEffectService):\n"
        "    @property\n"
        "    def now(self) -> float:\n"
        "        return time.time()\n"
        "    @now.deleter\n"
        "    def now(self) -> None:\n"
        "        del self._now\n\n"
        "class SetterService(BaseEffectService):\n"
        "    @property\n"
        "    def now(self) -> float:\n"
        "        return self._now\n"
        "    @now.setter\n"
        "    def now(self, value: float) -> None:\n"
        "        self._now = value + time.time()\n\n"
        "class ReplacedGetterService(BaseEffectService):\n"
        "    @property\n"
        "    def now(self) -> float:\n"
        "        return time.monotonic()\n"
        "    @now.getter\n"
        "    def now(self) -> float:\n"
        "        return 1.0\n",
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
        "GetterService",
        "SetterService",
    }
    assert all(
        item.rule_id is SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS
        for item in report.violations
    )
    assert all("time.monotonic" not in item.message for item in report.violations)


def test_use_case_property_accessors_are_checked_for_orchestration(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/current.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class CurrentUseCase(BaseUseCase):\n"
        "    @property\n"
        "    def result(self) -> int:\n"
        "        return len(())\n"
        "    @result.deleter\n"
        "    def result(self) -> None:\n"
        "        pass\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert len(report.violations) == 1
    assert "builtins.len" in report.violations[0].message


def test_annotated_callable_payloads_are_functions_but_collaborators_are_allowed(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "contracts.py"),
        "from collections.abc import Callable\n"
        "from typing import Annotated, TypeAlias\n\n"
        "ImportedFormatter: TypeAlias = Annotated[Callable[[str], str], 'formatter']\n"
        "QuotedFormatter: TypeAlias = \"Annotated[Callable[[str], str], 'formatter']\"\n",
    )
    _write(
        _source(tmp_path, "core/orders/use_cases/format_order.py"),
        "from collections.abc import Callable\n"
        "from typing import Annotated\n"
        "from diwire import Injected\n"
        "from demo_service.contracts import ImportedFormatter, QuotedFormatter\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class Worker:\n"
        "    def run(self, *, value: str) -> str: return value\n\n"
        "class FormatOrderUseCase(BaseUseCase):\n"
        "    direct: Injected[Annotated[Callable[[str], str], 'formatter']]\n"
        "    imported: Injected[ImportedFormatter]\n"
        "    quoted: 'Injected[QuotedFormatter]'\n"
        "    worker: Injected[Annotated[Worker, 'collaborator']]\n"
        "    def execute(self, *, value: str) -> str:\n"
        "        self.worker.run(value=value)\n"
        "        return self.direct(self.imported(self.quoted(value)))\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert len(report.violations) == 3
    messages = "\n".join(item.message for item in report.violations)
    assert "self.direct" in messages
    assert "self.imported" in messages
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
