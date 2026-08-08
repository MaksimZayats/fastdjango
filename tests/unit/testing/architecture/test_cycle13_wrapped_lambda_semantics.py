from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_direct_and_aliased_wrapped_lambdas_are_ambient_behavior(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/ambient_lambdas.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class StaticClockService(BaseEffectService):\n"
        "    now = staticmethod(lambda: time.time())\n\n"
        "class ClassClockService(BaseEffectService):\n"
        "    wrapper = classmethod\n"
        "    now = wrapper(lambda cls: time.monotonic())\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    )

    assert {item.symbol for item in report.violations} == {
        "ClassClockService",
        "StaticClockService",
    }
    messages = "\n".join(item.message for item in report.violations)
    assert "time.monotonic" in messages
    assert "time.time" in messages


def test_direct_and_aliased_wrapped_lambdas_are_use_case_behavior(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/wrapped_lambdas.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class ClassUseCase(BaseUseCase):\n"
        "    execute = classmethod(lambda cls: len(()))\n\n"
        "class StaticUseCase(BaseUseCase):\n"
        "    wrapper = staticmethod\n"
        "    execute = wrapper(lambda: sum(()))\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert {item.symbol for item in report.violations} == {
        "ClassUseCase",
        "StaticUseCase",
    }
    messages = "\n".join(item.message for item in report.violations)
    assert "builtins.len" in messages
    assert "builtins.sum" in messages


def test_direct_and_aliased_wrapped_lambdas_preserve_receiver_binding(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/signature_lambdas.py"),
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class StaticService(BasePureService):\n"
        "    run = staticmethod(lambda value: value)\n\n"
        "class ClassService(BasePureService):\n"
        "    wrapper = classmethod\n"
        "    run = wrapper(lambda cls, value: value)\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS,
    )

    assert {item.symbol for item in report.violations} == {
        "ClassService.run",
        "StaticService.run",
    }
    assert all("['value']" in item.message for item in report.violations)


def test_custom_and_ambiguous_lambda_wrappers_remain_unclassified(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/custom_lambda_wrappers.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n"
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "USE_BUILTIN = True\n"
        "def custom(function: object) -> object: return object()\n\n"
        "class CustomClockService(BaseEffectService):\n"
        "    staticmethod = custom\n"
        "    now = staticmethod(lambda: time.time())\n\n"
        "class AmbiguousService(BasePureService):\n"
        "    if USE_BUILTIN:\n"
        "        wrapper = classmethod\n"
        "    else:\n"
        "        wrapper = custom\n"
        "    run = wrapper(lambda cls, value: value)\n",
    )
    _write(
        _source(tmp_path, "core/orders/use_cases/custom_lambda_wrappers.py"),
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def custom(function: object) -> object: return object()\n\n"
        "class CustomUseCase(BaseUseCase):\n"
        "    classmethod = custom\n"
        "    execute = classmethod(lambda cls: len(()))\n",
    )

    report = _check_selected(
        tmp_path,
        {
            SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
            SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS,
            SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
        },
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
