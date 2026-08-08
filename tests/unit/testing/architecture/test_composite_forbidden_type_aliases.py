from __future__ import annotations

from pathlib import Path

import pytest

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


@pytest.mark.parametrize(
    ("imports", "alias"),
    [
        ("", "RuntimeConfig | None"),
        ("", "list[RuntimeConfig]"),
        ("from typing import Annotated\n", "Annotated[RuntimeConfig, 'runtime']"),
    ],
)
def test_core_rejects_imported_composite_runtime_settings_aliases(
    tmp_path: Path,
    imports: str,
    alias: str,
) -> None:
    _write(
        _source(tmp_path, "configuration.py"),
        f"{imports}from pydantic_settings import BaseSettings\n\n"
        "class RuntimeConfig(BaseSettings): pass\n\n"
        f"RuntimeConfigAlias = {alias}\n",
    )
    _write(
        _source(tmp_path, "core/orders/service.py"),
        "from demo_service.configuration import RuntimeConfigAlias\n\n"
        "def configure(*, settings: RuntimeConfigAlias) -> None: pass\n",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "RuntimeConfigAlias" in report.violations[0].message


def test_core_rejects_quoted_runtime_settings_type_alias(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "configuration.py"),
        "from typing import TypeAlias\n"
        "from pydantic_settings import BaseSettings\n\n"
        "class RuntimeConfig(BaseSettings): pass\n\n"
        "RuntimeConfigAlias: TypeAlias = 'RuntimeConfig | None'\n",
    )
    _write(
        _source(tmp_path, "core/orders/service.py"),
        "from demo_service.configuration import RuntimeConfigAlias\n\n"
        "settings: RuntimeConfigAlias\n",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "RuntimeConfigAlias" in report.violations[0].message


def test_core_rejects_forbidden_alias_reached_through_a_quoted_cycle(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "configuration.py"),
        "from typing import TypeAlias\n"
        "from pydantic_settings import BaseSettings\n\n"
        "class RuntimeConfig(BaseSettings): pass\n\n"
        "FirstAlias: TypeAlias = 'SecondAlias'\n"
        "SecondAlias: TypeAlias = 'FirstAlias | RuntimeConfig'\n",
    )
    _write(
        _source(tmp_path, "core/orders/service.py"),
        "from demo_service.configuration import FirstAlias\n\nsettings: FirstAlias\n",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "FirstAlias" in report.violations[0].message


def test_core_rejects_recursively_imported_pydantic_alias_chain(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "delivery/schema.py"),
        "from pydantic import BaseModel\n\nclass OrderSchema(BaseModel): pass\n",
    )
    _write(
        _source(tmp_path, "contracts.py"),
        "from demo_service.delivery.schema import OrderSchema\n\n"
        "OrderSchemas = list[OrderSchema]\n",
    )
    _write(
        _source(tmp_path, "public_types.py"),
        "from demo_service.contracts import OrderSchemas\n\n"
        "MaybeOrderSchemas = OrderSchemas | None\n",
    )
    _write(
        _source(tmp_path, "core/orders/service.py"),
        "from demo_service.public_types import MaybeOrderSchemas\n\n"
        "def consume(*, orders: MaybeOrderSchemas) -> None: pass\n",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "MaybeOrderSchemas" in report.violations[0].message


def test_core_allows_pure_composite_and_string_value_aliases(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "domain_types.py"),
        "from dataclasses import dataclass\n"
        "from typing import Annotated, Literal, TypeAlias\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class DomainOptions:\n"
        "    retries: int\n\n"
        "MaybeOptions = DomainOptions | None\n"
        "OptionList = list[DomainOptions]\n"
        "TaggedOption = Annotated[DomainOptions, 'domain']\n"
        "TaggedLabel = Annotated[str, 'RuntimeConfig']\n"
        "LiteralLabel = Literal['RuntimeConfig']\n"
        "ForwardOption: TypeAlias = 'DomainOptions | None'\n"
        "RUNTIME_LABEL = 'RuntimeConfig'\n",
    )
    _write(
        _source(tmp_path, "core/orders/service.py"),
        "from demo_service.domain_types import (\n"
        "    ForwardOption, LiteralLabel, MaybeOptions, OptionList, RUNTIME_LABEL,\n"
        "    TaggedLabel, TaggedOption,\n"
        ")\n\n"
        "def consume(\n"
        "    *, first: MaybeOptions, second: OptionList, third: TaggedOption,\n"
        "    fourth: ForwardOption, label: LiteralLabel, tagged: TaggedLabel,\n"
        ") -> str:\n"
        "    return RUNTIME_LABEL\n",
    )

    assert _check(tmp_path).violations == ()


def _check(project_root: Path) -> SpecxArchitectureReport:
    rule_id = SpecxRuleId.CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC
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
