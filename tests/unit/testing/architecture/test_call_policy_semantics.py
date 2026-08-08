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


def test_function_di_rejects_quoted_injected_annotations(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests/unit/test_handler.py",
        "from diwire import Injected\n\n"
        "class Worker: pass\n\n"
        "def bad(worker: 'Injected[Worker]'): pass\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.DIWIRE_NO_FUNCTION_INJECTION)

    assert [item.symbol for item in report.violations] == ["bad"]


def test_legacy_injected_aliases_work_for_fields_and_fail_for_parameters(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "dependencies.py"),
        "from typing import TypeAlias\n"
        "from diwire import Injected\n\n"
        "class Worker:\n"
        "    def run(self): pass\n\n"
        "WorkerDependency: TypeAlias = Injected[Worker]\n",
    )
    _write(
        _source(tmp_path, "core/orders/use_cases/place.py"),
        "from demo_service.dependencies import WorkerDependency\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class PlaceUseCase(BaseUseCase):\n"
        "    worker: WorkerDependency\n"
        "    def execute(self, *, command): return self.worker.run()\n",
    )
    _write(
        tmp_path / "tests/unit/test_handler.py",
        "from demo_service.dependencies import WorkerDependency\n\n"
        "def handler(worker: WorkerDependency): pass\n",
    )

    orchestration = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )
    injection = _check_only(tmp_path, SpecxRuleId.DIWIRE_NO_FUNCTION_INJECTION)

    assert orchestration.violations == ()
    assert [item.symbol for item in injection.violations] == ["handler"]


def test_function_level_resolver_context_service_location_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests/unit/test_handler.py",
        "from diwire import resolver_context\n\n"
        "class Service: pass\n\n"
        "def sync_handler(): return resolver_context.resolve(Service)\n"
        "async def async_handler(): return await resolver_context.aresolve(Service)\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.DIWIRE_NO_FUNCTION_INJECTION)

    assert len(report.violations) == 2


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


def test_project_constructor_reexports_resolve_to_the_defining_class(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/dtos/order.py"),
        "class OrderDTO: pass\n",
    )
    _write(
        _source(tmp_path, "core/orders/dtos/__init__.py"),
        "from .order import OrderDTO\n",
    )
    _write(
        _source(tmp_path, "core/orders/use_cases/get.py"),
        "from demo_service.core.orders.dtos import OrderDTO\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class GetUseCase(BaseUseCase):\n"
        "    def execute(self, *, query): return OrderDTO()\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert report.violations == ()


def test_injected_fields_lose_trust_after_override_or_reassignment(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/place.py"),
        "from diwire import Injected\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class Worker:\n"
        "    def run(self): pass\n\n"
        "class BasePlaceUseCase(BaseUseCase):\n"
        "    worker: Injected[Worker]\n\n"
        "class OverriddenUseCase(BasePlaceUseCase):\n"
        "    worker: Worker\n"
        "    def execute(self, *, command): return self.worker.run()\n\n"
        "class ReassignedUseCase(BaseUseCase):\n"
        "    worker: Injected[Worker]\n"
        "    def execute(self, *, command):\n"
        "        self.worker = command.worker\n"
        "        return self.worker.run()\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert {item.symbol for item in report.violations} == {
        "OverriddenUseCase",
        "ReassignedUseCase",
    }


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


def test_ambient_alias_flow_merges_try_prefixes_inside_handler(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/token.py"),
        "import os\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class TokenService(BaseEffectService):\n"
        "    def issue(self, *, size: int) -> bytes:\n"
        "        factory = bytes\n"
        "        try:\n"
        "            factory = os.urandom\n"
        "            raise RuntimeError\n"
        "        except RuntimeError:\n"
        "            return factory(size)\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS)

    assert [item.line for item in report.violations] == [11]


def test_ambient_alias_flow_resolves_destructuring(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/clock.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class ClockService(BaseEffectService):\n"
        "    def now(self):\n"
        "        fn, unused = time.time, None\n"
        "        return fn()\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS)

    assert [item.line for item in report.violations] == [7]


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


def test_common_filesystem_and_process_apis_are_ambient(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/runtime.py"),
        "import asyncio\nimport glob\nimport os\n"
        "from pathlib import Path\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class RuntimeService(BaseEffectService):\n"
        "    async def inspect(self, *, root: Path):\n"
        "        os.access(root, os.R_OK)\n"
        "        os.walk(root)\n"
        "        os.cpu_count()\n"
        "        os.kill(1, 0)\n"
        "        glob.glob('*')\n"
        "        root.absolute()\n"
        "        return await asyncio.create_subprocess_exec('true')\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS)

    assert len(report.violations) == 7


def test_typed_ambient_objects_remain_ambient_through_local_aliases(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/runtime.py"),
        "from datetime import datetime\n"
        "from pathlib import Path\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class RuntimeService(BaseEffectService):\n"
        "    def inspect(self, *, path: Path, instant: datetime):\n"
        "        alias = path\n"
        "        other = instant\n"
        "        alias.read_text()\n"
        "        return other.astimezone()\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS)

    assert len(report.violations) == 2


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
