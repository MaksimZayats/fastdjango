from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)

BEHAVIOR_RULES = {
    SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
}


def test_class_scope_aliases_resolve_exact_builtin_wrappers(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/aliases.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "def read_now(_self: object) -> float: return time.time()\n\n"
        "class ClockService(BaseEffectService):\n"
        "    descriptor = property\n"
        "    now = descriptor(read_now)\n",
    )
    _write(
        _source(tmp_path, "core/orders/use_cases/aliases.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def run_static() -> int: return len(())\n"
        "def run_class(_cls: type[object]) -> int: return sum(())\n\n"
        "class StaticUseCase(BaseUseCase):\n"
        "    wrapper = staticmethod\n"
        "    execute = wrapper(run_static)\n\n"
        "class ClassUseCase(BaseUseCase):\n"
        "    wrapper = classmethod\n"
        "    execute = wrapper(run_class)\n",
    )

    report = _check_selected(tmp_path, BEHAVIOR_RULES)

    assert {item.symbol for item in report.violations} == {
        "ClassUseCase",
        "ClockService",
        "StaticUseCase",
    }
    messages = "\n".join(item.message for item in report.violations)
    assert "time.time" in messages
    assert "builtins.len" in messages
    assert "builtins.sum" in messages


def test_class_scope_shadows_reject_custom_wrappers(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/shadows.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "def custom(function: object) -> object: return object()\n"
        "def read_now(_self: object) -> float: return time.time()\n\n"
        "class ClockService(BaseEffectService):\n"
        "    property = custom\n"
        "    descriptor = property\n"
        "    now = descriptor(read_now)\n",
    )
    _write(
        _source(tmp_path, "core/orders/use_cases/shadows.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def custom(function: object) -> object: return object()\n"
        "def run_static() -> int: return len(())\n"
        "def run_class(_cls: type[object]) -> int: return sum(())\n\n"
        "class StaticUseCase(BaseUseCase):\n"
        "    staticmethod = custom\n"
        "    wrapper = staticmethod\n"
        "    execute = wrapper(run_static)\n\n"
        "class ClassUseCase(BaseUseCase):\n"
        "    classmethod = custom\n"
        "    wrapper = classmethod\n"
        "    execute = wrapper(run_class)\n",
    )

    report = _check_selected(tmp_path, BEHAVIOR_RULES)

    assert report.violations == ()


def test_class_scope_conditional_wrapper_bindings_are_conservative(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/conditional.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "USE_BUILTIN = True\n"
        "def custom(function: object) -> object: return object()\n"
        "def read_now(_self: object) -> float: return time.time()\n\n"
        "class ClockService(BaseEffectService):\n"
        "    if USE_BUILTIN:\n"
        "        wrapper = property\n"
        "    else:\n"
        "        wrapper = custom\n"
        "    now = wrapper(read_now)\n",
    )
    _write(
        _source(tmp_path, "core/orders/use_cases/conditional.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "USE_BUILTIN = True\n"
        "def custom(function: object) -> object: return object()\n"
        "def run_static() -> int: return len(())\n"
        "def run_class(_cls: type[object]) -> int: return sum(())\n\n"
        "class StaticUseCase(BaseUseCase):\n"
        "    if USE_BUILTIN:\n"
        "        wrapper = staticmethod\n"
        "    else:\n"
        "        wrapper = custom\n"
        "    execute = wrapper(run_static)\n\n"
        "class ClassUseCase(BaseUseCase):\n"
        "    if USE_BUILTIN:\n"
        "        wrapper = classmethod\n"
        "    else:\n"
        "        wrapper = custom\n"
        "    execute = wrapper(run_class)\n",
    )

    report = _check_selected(tmp_path, BEHAVIOR_RULES)

    assert report.violations == ()


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
