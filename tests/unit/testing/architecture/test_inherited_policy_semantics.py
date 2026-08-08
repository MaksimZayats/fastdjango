from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_core_rejects_project_root_models_and_pydantic_dataclasses(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "contracts.py"),
        "from dataclasses import dataclass\n"
        "from pydantic import RootModel\n"
        "from pydantic.dataclasses import dataclass as pydantic_dataclass\n\n"
        "class Tags(RootModel[list[str]]): pass\n\n"
        "@pydantic_dataclass\n"
        "class Request:\n"
        "    value: str\n\n"
        "@dataclass\n"
        "class DomainValue:\n"
        "    value: str\n",
    )
    _write(
        _source(tmp_path, "core/orders/services/parser.py"),
        "import demo_service.contracts as contracts\n\n"
        "def parse() -> object:\n"
        "    contracts.Request(value='order')\n"
        "    contracts.DomainValue(value='domain')\n"
        "    return contracts.Tags(['order'])\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC,
    )

    assert len(report.violations) == 1
    assert "demo_service.contracts.Request" in report.violations[0].message
    assert "demo_service.contracts.Tags" in report.violations[0].message
    assert "DomainValue" not in report.violations[0].message


def test_core_rejects_legacy_aliases_of_pydantic_and_settings_types(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "contracts.py"),
        "from typing import TypeAlias\n"
        "from pydantic import BaseModel\n"
        "from pydantic_settings import BaseSettings\n\n"
        "class RuntimePayload(BaseModel): pass\n"
        "class RuntimeSettings(BaseSettings): pass\n"
        "PayloadAlias: TypeAlias = RuntimePayload\n"
        "SettingsAlias: TypeAlias = RuntimeSettings\n",
    )
    _write(
        _source(tmp_path, "core/orders/services/parser.py"),
        "from demo_service.contracts import PayloadAlias, SettingsAlias\n\n"
        "def parse(payload: PayloadAlias, settings: SettingsAlias):\n"
        "    return payload, settings\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC,
    )

    assert len(report.violations) == 2


def test_core_rejects_package_reexported_pydantic_types(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "delivery/schemas/request.py"),
        "from pydantic import BaseModel\n\nclass Request(BaseModel): pass\n",
    )
    _write(
        _source(tmp_path, "delivery/schemas/__init__.py"),
        "from .request import Request\n",
    )
    _write(
        _source(tmp_path, "core/orders/services/parser.py"),
        "from demo_service.delivery.schemas import Request\n\n"
        "def parse(value): return Request.model_validate(value)\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC,
    )

    assert len(report.violations) == 1
    assert "request.Request" in report.violations[0].message


def test_core_rejects_neutral_reexports_and_quoted_forbidden_types(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "delivery/schemas/request.py"),
        "from pydantic import BaseModel\n\nclass RuntimePayload(BaseModel): pass\n",
    )
    _write(
        _source(tmp_path, "infrastructure/settings.py"),
        "from pydantic_settings import BaseSettings\n\nclass RuntimeSettings(BaseSettings): pass\n",
    )
    _write(
        _source(tmp_path, "contracts.py"),
        "from demo_service.delivery.schemas.request import RuntimePayload\n"
        "from demo_service.infrastructure.settings import RuntimeSettings\n",
    )
    _write(
        _source(tmp_path, "core/orders/services/parser.py"),
        "import demo_service.contracts as contracts\n\n"
        "class Parser:\n"
        "    payload: 'contracts.RuntimePayload'\n"
        "    settings: 'contracts.RuntimeSettings'\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC,
    )

    assert len(report.violations) == 2
    messages = "\n".join(item.message for item in report.violations)
    assert "demo_service.contracts.RuntimePayload" in messages
    assert "demo_service.contracts.RuntimeSettings" in messages


def test_service_signature_reports_each_inherited_declaration_once_and_overrides(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/foundation/price_service.py"),
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class BasePriceService(BasePureService):\n"
        "    def total(self, value: int) -> int: return value\n"
        "    def discount(self, *, value: int) -> int: return value\n",
    )
    _write(
        _source(tmp_path, "core/orders/services/retail.py"),
        "from demo_service.core.orders.foundation.price_service import BasePriceService\n\n"
        "class RetailPriceService(BasePriceService): pass\n",
    )
    _write(
        _source(tmp_path, "core/orders/services/wholesale.py"),
        "from demo_service.core.orders.foundation.price_service import BasePriceService\n\n"
        "class WholesalePriceService(BasePriceService):\n"
        "    def discount(self, value: int) -> int: return value\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS,
    )

    assert [item.symbol for item in report.violations] == [
        "BasePriceService.total",
        "WholesalePriceService.discount",
    ]


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


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
