from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_conditional_and_nested_use_cases_remain_enforced(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/place.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def forbidden(): return 1\n\n"
        "if True:\n"
        "    class ConditionalUseCase(BaseUseCase):\n"
        "        def execute(self): return forbidden()\n\n"
        "class Namespace:\n"
        "    class NestedUseCase(BaseUseCase):\n"
        "        def execute(self): return forbidden()\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert [item.symbol for item in report.violations] == [
        "ConditionalUseCase",
        "NestedUseCase",
    ]


def test_attached_and_overloaded_behavior_uses_runtime_implementation(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/place.py"),
        "from typing import overload\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def forbidden(): return 1\n"
        "def attached_execute(self): return forbidden()\n\n"
        "class AttachedUseCase(BaseUseCase):\n"
        "    execute = attached_execute\n\n"
        "class OverloadedUseCase(BaseUseCase):\n"
        "    @overload\n"
        "    def execute(self, *, value: int) -> int: ...\n"
        "    def execute(self, *, value: int) -> int: return forbidden()\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert [item.symbol for item in report.violations] == [
        "AttachedUseCase",
        "OverloadedUseCase",
    ]


def test_attached_service_method_preserves_public_signature_policy(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/price.py"),
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "def total_impl(self, value: int) -> int: return value\n\n"
        "class PriceService(BasePureService):\n"
        "    total = total_impl\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS,
    )

    assert [item.symbol for item in report.violations] == ["PriceService.total"]


def test_walrus_alias_preserves_ambient_call_identity(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/clock.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class ClockService(BaseEffectService):\n"
        "    def read(self):\n"
        "        if fn := time.time:\n"
        "            pass\n"
        "        first = fn()\n"
        "        return ((other := time.monotonic), other())[1], first\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    )

    assert len(report.violations) == 2
    messages = "\n".join(item.message for item in report.violations)
    assert "time.monotonic" in messages
    assert "time.time" in messages


def test_dormant_nested_bodies_are_skipped_but_defaults_execute(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/clock.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class ClockService(BaseEffectService):\n"
        "    def safe(self):\n"
        "        def unused(): return time.time()\n"
        "        unused_lambda = lambda: time.time()\n"
        "        class Unused:\n"
        "            def read(self): return time.time()\n"
        "        return unused, unused_lambda, Unused\n\n"
        "    def definition_time(self):\n"
        "        def nested(value=time.time()): return value\n"
        "        return nested\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    )

    assert len(report.violations) == 1
    assert report.violations[0].line == 13


def test_path_policy_uses_exact_receiver_provenance(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/path.py"),
        "from pathlib import Path as FilePath\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class Path:\n"
        "    @staticmethod\n"
        "    def exists(): return True\n\n"
        "class PathService(BaseEffectService):\n"
        "    def inspect(self, *, path: FilePath):\n"
        "        local_exists = Path.exists()\n"
        "        local_path = Path()\n"
        "        def dormant():\n"
        "            local_path = FilePath('.')\n"
        "            return local_path.exists()\n"
        "        clean_name = path.name.replace('a', 'b')\n"
        "        return (\n"
        "            local_exists, local_path.exists(), dormant, clean_name,\n"
        "            path.read_text(), path.parent.stat(),\n"
        "        )\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    )

    assert {item.line for item in report.violations} == {18}
    assert len(report.violations) == 2


def test_ambient_policy_covers_low_level_io_network_and_runtime_clocks(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/runtime.py"),
        "import asyncio\nimport os\nimport time\nimport uuid\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class RuntimeService(BaseEffectService):\n"
        "    async def inspect(self, *, path):\n"
        "        fd = os.open(path, os.O_RDONLY)\n"
        "        data = os.read(fd, 1)\n"
        "        os.write(fd, data)\n"
        "        os.close(fd)\n"
        "        await asyncio.open_connection('localhost', 80)\n"
        "        loop_time = asyncio.get_running_loop().time()\n"
        "        return time.clock_gettime(0), time.thread_time(), uuid.getnode(), loop_time\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    )

    messages = "\n".join(item.message for item in report.violations)
    for expected in (
        "os.open",
        "os.read",
        "os.write",
        "os.close",
        "asyncio.open_connection",
        "asyncio.get_running_loop.time",
        "time.clock_gettime",
        "time.thread_time",
        "uuid.getnode",
    ):
        assert expected in messages


def test_inherited_ambient_behavior_has_one_diagnostic_owner(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/read.py"),
        "import os\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class EnvironmentMixin:\n"
        "    def execute(self): return os.getenv('ORDER_ID')\n\n"
        "class ReadUseCase(EnvironmentMixin, BaseUseCase): pass\n",
    )

    report = _check_selected(
        tmp_path,
        {
            SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
            SpecxRuleId.CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC,
        },
    )

    assert [item.rule_id for item in report.violations] == [
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS
    ]


def test_quoted_injected_fields_preserve_collaborator_and_callable_policy(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/place.py"),
        "from typing import Callable\n"
        "from diwire import Injected\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class Worker:\n"
        "    def run(self): return 1\n\n"
        "class PlaceUseCase(BaseUseCase):\n"
        "    worker: 'Injected[Worker]'\n"
        "    formatter: 'Injected[Callable[[str], str]]'\n"
        "    def execute(self):\n"
        "        self.worker.run()\n"
        "        return self.formatter('order')\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert len(report.violations) == 1
    assert "self.formatter" in report.violations[0].message


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
