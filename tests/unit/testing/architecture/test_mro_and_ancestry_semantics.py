from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_foundation_ancestry_resolves_exact_module_level_aliases(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/place.py"),
        "from typing import TypeAlias\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "AssignedUseCaseBase = BaseUseCase\n"
        "AnnotatedUseCaseBase: TypeAlias = BaseUseCase\n\n"
        "def forbidden(): return 1\n\n"
        "class AssignedUseCase(AssignedUseCaseBase):\n"
        "    def execute(self): return forbidden()\n\n"
        "class AnnotatedUseCase(AnnotatedUseCaseBase):\n"
        "    def execute(self): return forbidden()\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert [item.symbol for item in report.violations] == [
        "AssignedUseCase",
        "AnnotatedUseCase",
    ]


def test_abstract_markers_require_exact_standard_library_identities(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/place.py"),
        "from abc import abstractmethod as real_abstractmethod\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def abstractmethod(function): return function\n"
        "def forbidden(): return 1\n"
        "class Protocol: pass\n\n"
        "class DecoratedUseCase(BaseUseCase):\n"
        "    @abstractmethod\n"
        "    def execute(self): return forbidden()\n\n"
        "class ProtocolUseCase(Protocol, BaseUseCase):\n"
        "    def execute(self): return forbidden()\n\n"
        "class RealAbstractUseCase(BaseUseCase):\n"
        "    @real_abstractmethod\n"
        "    def execute(self): ...\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert [item.symbol for item in report.violations] == [
        "DecoratedUseCase",
        "ProtocolUseCase",
    ]


def test_concrete_mixin_satisfies_inherited_abstract_method(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/place.py"),
        "from abc import abstractmethod\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def forbidden(): return 1\n\n"
        "class AbstractPlaceUseCase(BaseUseCase):\n"
        "    @abstractmethod\n"
        "    def execute(self): ...\n\n"
        "class ExecuteMixin:\n"
        "    def execute(self): return forbidden()\n\n"
        "class PlaceUseCase(ExecuteMixin, AbstractPlaceUseCase):\n"
        "    pass\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert [item.symbol for item in report.violations] == ["PlaceUseCase"]


def test_behavior_methods_follow_python_c3_mro(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/clock.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class AmbientRoot:\n"
        "    def read(self): return time.time()\n\n"
        "class SafeLeft(AmbientRoot): pass\n"
        "class SafeRight(AmbientRoot):\n"
        "    def read(self): return 1.0\n\n"
        "class SafeClockService(SafeLeft, SafeRight, BaseEffectService): pass\n\n"
        "class SafeRoot:\n"
        "    def read(self): return 1.0\n\n"
        "class AmbientLeft(SafeRoot): pass\n"
        "class AmbientRight(SafeRoot):\n"
        "    def read(self): return time.time()\n\n"
        "class AmbientClockService(AmbientLeft, AmbientRight, BaseEffectService): pass\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    )

    assert [item.symbol for item in report.violations] == ["AmbientClockService"]


def test_inherited_sqlalchemy_mapping_is_concrete_in_foundation(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "foundation/models.py"),
        "from sqlalchemy.orm import mapped_column\n"
        "from specx.infrastructure.foundation.sqlalchemy.model import BaseSQLAlchemyModel\n\n"
        "class BaseOrderModel(BaseSQLAlchemyModel):\n"
        "    __tablename__ = 'orders'\n\n"
        "class BaseSpecialOrderModel(BaseOrderModel):\n"
        "    special = mapped_column(default=False)\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.SQLALCHEMY_MODELS_LIVE_UNDER_SCOPE_INFRASTRUCTURE,
    )

    assert {item.symbol for item in report.violations} == {
        "BaseOrderModel",
        "BaseSpecialOrderModel",
    }


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
