from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_function_di_resolves_project_aliases_without_annotated_false_positives(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "injected_alias.py"),
        "from diwire import Injected\n\nInjectedValue = Injected[int]\n",
    )
    _write(
        tmp_path / "tests/unit/test_handler.py",
        "from typing import Annotated\n"
        "from demo_service.injected_alias import InjectedValue\n\n"
        "def bad(value: InjectedValue): pass\n"
        "def good(value: Annotated[str, 'NotInjected']): pass\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.DIWIRE_NO_FUNCTION_INJECTION)

    assert [item.symbol for item in report.violations] == ["bad"]


def test_definition_time_policy_merges_branches_conservatively(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/dtos/order.py"),
        "import os\n"
        "from dataclasses import dataclass\n"
        "from specx.core.foundation.dto import BaseDTO\n\n"
        "def fake(cls=None, **kwargs): return cls\n"
        "deco = fake\n"
        "if os.getenv('REAL'): deco = dataclass\n"
        "@deco(frozen=True, kw_only=True, slots=True)\n"
        "class OrderDTO(BaseDTO): pass\n",
    )
    _write(
        tmp_path / "tests/unit/test_handler.py",
        "import os\n"
        "from diwire import resolver_context\n\n"
        "def fake(fn): return fn\n"
        "deco = fake\n"
        "if os.getenv('REAL'): deco = resolver_context.inject\n"
        "@deco\n"
        "def handler(): pass\n",
    )

    dataclasses = _check_only(
        tmp_path,
        SpecxRuleId.CORE_CONTRACTS_USE_IMMUTABLE_DATACLASSES,
    )
    injection = _check_only(tmp_path, SpecxRuleId.DIWIRE_NO_FUNCTION_INJECTION)

    assert [item.symbol for item in dataclasses.violations] == ["OrderDTO"]
    assert [item.symbol for item in injection.violations] == ["handler"]


def test_call_policy_requires_all_reaching_collaborator_bindings(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/place.py"),
        "from diwire import Injected\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class Worker:\n"
        "    def run(self): pass\n\n"
        "class PlaceUseCase(BaseUseCase):\n"
        "    worker: Injected[Worker]\n"
        "    def execute(self, *, command, flag: bool):\n"
        "        current = command.worker\n"
        "        if flag: current = self.worker\n"
        "        return current.run()\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert len(report.violations) == 1
    assert report.violations[0].line == 12


def test_ambient_alias_flow_preserves_loop_break_and_caught_raise_paths(
    tmp_path: Path,
) -> None:
    _write(_source(tmp_path, "safe.py"), "def time(): return 0.0\n")
    _write(
        _source(tmp_path, "core/orders/services/clock.py"),
        "import time\n"
        "from demo_service import safe\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class ClockService(BaseEffectService):\n"
        "    def loop(self, *, values):\n"
        "        fn = safe.time\n"
        "        for value in values:\n"
        "            fn = time.time\n"
        "            break\n"
        "        return fn()\n"
        "    def caught(self):\n"
        "        fn = safe.time\n"
        "        try:\n"
        "            fn = time.time\n"
        "            raise ValueError\n"
        "        except ValueError:\n"
        "            pass\n"
        "        return fn()\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS)

    assert {item.line for item in report.violations} == {11, 19}


def test_datetime_local_timezone_reads_are_ambient_but_explicit_timezone_is_not(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/clock.py"),
        "from datetime import UTC, datetime\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class ClockService(BaseEffectService):\n"
        "    def localize(self, *, value: datetime, timestamp: float):\n"
        "        value.astimezone()\n"
        "        datetime.fromtimestamp(timestamp)\n"
        "        return datetime.fromtimestamp(timestamp, UTC)\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS)

    assert {item.line for item in report.violations} == {6, 7}


def _check_only(
    project_root: Path,
    rule_id: SpecxRuleId,
) -> SpecxArchitectureReport:
    return check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=project_root,
            package_name="demo_service",
            disabled_rules=frozenset(
                candidate for candidate in SpecxRuleId if candidate != rule_id
            ),
        )
    )


def _source(project_root: Path, relative: str) -> Path:
    return project_root / "src/demo_service" / relative


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
