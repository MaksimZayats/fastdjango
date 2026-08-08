from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_class_control_flow_and_descriptor_attached_methods_are_checked(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/clock.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "def static_read(value: int): return time.time() + value\n"
        "def class_read(cls, value: int): return time.time() + value\n\n"
        "class ConditionalService(BaseEffectService):\n"
        "    if True:\n"
        "        def read(self, value: int): return time.time() + value\n\n"
        "class StaticService(BaseEffectService):\n"
        "    read = staticmethod(static_read)\n\n"
        "class ClassService(BaseEffectService):\n"
        "    read = classmethod(class_read)\n",
    )

    report = _check_selected(
        tmp_path,
        {
            SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
            SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS,
        },
    )

    assert len(report.violations) == 6
    assert {item.symbol for item in report.violations} == {
        "ClassService",
        "ClassService.read",
        "ConditionalService",
        "ConditionalService.read",
        "StaticService",
        "StaticService.read",
    }


def test_class_control_flow_and_attached_use_case_functions_are_checked(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/place.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def helper(): return 1\n"
        "def attached_execute(self): return helper()\n\n"
        "def static_execute(): return helper()\n"
        "def class_execute(cls): return helper()\n\n"
        "class ConditionalUseCase(BaseUseCase):\n"
        "    if True:\n"
        "        def execute(self): return helper()\n\n"
        "class AttachedUseCase(BaseUseCase):\n"
        "    execute = attached_execute\n\n"
        "class StaticUseCase(BaseUseCase):\n"
        "    execute = staticmethod(static_execute)\n\n"
        "class ClassUseCase(BaseUseCase):\n"
        "    execute = classmethod(class_execute)\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert {item.symbol for item in report.violations} == {
        "AttachedUseCase",
        "ClassUseCase",
        "ConditionalUseCase",
        "StaticUseCase",
    }


def test_conditional_method_satisfies_project_abstract_declaration_for_analysis(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/clock.py"),
        "import time\n"
        "from abc import abstractmethod\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class AbstractClockService(BaseEffectService):\n"
        "    @abstractmethod\n"
        "    def read(self): ...\n\n"
        "class ClockService(AbstractClockService):\n"
        "    if True:\n"
        "        def read(self): return time.time()\n\n"
        "class DormantClockService(AbstractClockService):\n"
        "    if False:\n"
        "        def read(self): return time.monotonic()\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    )

    assert [item.symbol for item in report.violations] == ["ClockService"]


def test_plain_subclass_assignment_invalidates_inherited_injected_field(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/run.py"),
        "from diwire import Injected\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class Worker:\n"
        "    def run(self): return 1\n\n"
        "class BaseRunUseCase(BaseUseCase):\n"
        "    worker: Injected[Worker]\n\n"
        "class RunUseCase(BaseRunUseCase):\n"
        "    worker = Worker()\n"
        "    def execute(self): return self.worker.run()\n\n"
        "class DefaultedUseCase(BaseRunUseCase):\n"
        "    worker: Injected[Worker] = Worker()\n"
        "    def execute(self): return self.worker.run()\n\n"
        "class AssignedThenAnnotatedUseCase(BaseRunUseCase):\n"
        "    worker = Worker()\n"
        "    worker: Injected[Worker]\n"
        "    def execute(self): return self.worker.run()\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert {item.symbol for item in report.violations} == {
        "AssignedThenAnnotatedUseCase",
        "DefaultedUseCase",
        "RunUseCase",
    }
    assert all("self.worker.run" in item.message for item in report.violations)


def test_path_provenance_is_exact_and_tracks_inline_derived_paths(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "helpers/pathlib_math.py"),
        "def stat(): return 42\n",
    )
    _write(
        _source(tmp_path, "core/orders/services/files.py"),
        "from pathlib import Path\n"
        "from demo_service.helpers import pathlib_math\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class FileService(BaseEffectService):\n"
        "    def inspect(self, *, root: Path):\n"
        "        deterministic = pathlib_math.stat()\n"
        "        return deterministic, (root / 'config.json').read_text()\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    )

    assert len(report.violations) == 1
    assert report.violations[0].line == 8
    assert "read_text" in report.violations[0].message


def test_ambient_callable_parameter_defaults_are_tracked(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/clock.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class ClockService(BaseEffectService):\n"
        "    def read(self, *, clock=time.time): return clock()\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    )

    assert len(report.violations) == 1
    assert "time.time" in report.violations[0].message


def test_only_statically_called_local_helper_bodies_are_followed(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/clock.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "def module_clock(): return time.time()\n"
        "def dormant_module_clock(): return time.monotonic()\n\n"
        "class ClockService(BaseEffectService):\n"
        "    def read(self):\n"
        "        def nested_clock(): return time.perf_counter()\n"
        "        def dormant_nested_clock(): return time.process_time()\n"
        "        return nested_clock(), dormant_nested_clock\n"
        "    def read_default(self, *, clock=module_clock): return clock()\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    )

    messages = "\n".join(item.message for item in report.violations)
    assert len(report.violations) == 2
    assert "time.time" in messages
    assert "time.perf_counter" in messages
    assert "time.monotonic" not in messages
    assert "time.process_time" not in messages


def test_pure_settings_module_name_is_allowed_but_exact_settings_types_are_not(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "settings.py"),
        "DEFAULT_PAGE_SIZE = 20\n",
    )
    _write(
        _source(tmp_path, "configuration.py"),
        "from pydantic_settings import BaseSettings\n\nclass RuntimeConfig(BaseSettings): pass\n",
    )
    _write(
        _source(tmp_path, "core/orders/entities/order.py"),
        "from demo_service.settings import DEFAULT_PAGE_SIZE\n"
        "from demo_service.configuration import RuntimeConfig\n\n"
        "page_size = DEFAULT_PAGE_SIZE\n"
        "runtime: RuntimeConfig\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC,
    )

    assert len(report.violations) == 1
    assert "RuntimeConfig" in report.violations[0].message
    assert "DEFAULT_PAGE_SIZE" not in report.violations[0].message


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
