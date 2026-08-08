from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_service_signatures_exclude_only_the_actual_receiver(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/receiver.py"),
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class ReceiverService(BasePureService):\n"
        "    def instance(receiver, value: int) -> int: return value\n"
        "    @classmethod\n"
        "    def class_level(owner, value: int) -> int: return value\n"
        "    @staticmethod\n"
        "    def static(self: int) -> int: return self\n"
        "    def unusual(receiver, self: int) -> int: return self\n"
        "    def no_arguments(receiver) -> None: pass\n",
    )

    report = _check(tmp_path)

    assert [(item.symbol, item.message) for item in report.violations] == [
        (
            "ReceiverService.instance",
            "public parameters must be keyword-only: ['value']",
        ),
        (
            "ReceiverService.class_level",
            "public parameters must be keyword-only: ['value']",
        ),
        (
            "ReceiverService.static",
            "public parameters must be keyword-only: ['self']",
        ),
        (
            "ReceiverService.unusual",
            "public parameters must be keyword-only: ['self']",
        ),
    ]


def test_service_signatures_check_every_overload_once_across_descendants(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/foundation/formatter.py"),
        "from typing import overload\n"
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class BaseFormatterService(BasePureService):\n"
        "    @overload\n"
        "    def render(receiver, value: str) -> str: ...\n"
        "    @overload\n"
        "    def render(receiver, *, value: int) -> int: ...\n"
        "    def render(receiver, value: object) -> object: return value\n",
    )
    for module, class_name in (
        ("json_formatter", "JsonFormatterService"),
        ("text_formatter", "TextFormatterService"),
    ):
        _write(
            _source(tmp_path, f"core/orders/services/{module}.py"),
            "from demo_service.core.orders.foundation.formatter import "
            "BaseFormatterService\n\n"
            f"class {class_name}(BaseFormatterService): pass\n",
        )

    report = _check(tmp_path)

    assert [item.symbol for item in report.violations] == [
        "BaseFormatterService.render",
        "BaseFormatterService.render",
    ]
    assert [item.line for item in report.violations] == [6, 9]


def test_service_signature_effective_override_hides_all_base_overloads(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "foundation/legacy_formatter.py"),
        "from typing import overload\n\n"
        "class LegacyFormatterMixin:\n"
        "    @overload\n"
        "    def render(receiver, value: str) -> str: ...\n"
        "    @overload\n"
        "    def render(receiver, value: bytes) -> bytes: ...\n"
        "    def render(receiver, value: object) -> object: return value\n",
    )
    _write(
        _source(tmp_path, "core/orders/services/formatter.py"),
        "from demo_service.foundation.legacy_formatter import LegacyFormatterMixin\n"
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class FormatterService(LegacyFormatterMixin, BasePureService):\n"
        "    def render(receiver, *, value: object) -> object: return value\n",
    )

    report = _check(tmp_path)

    assert report.violations == ()


def _check(project_root: Path) -> SpecxArchitectureReport:
    return check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=project_root,
            package_name="demo_service",
            disabled_rules=frozenset(
                rule
                for rule in SpecxRuleId
                if rule != SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS
            ),
        )
    )


def _source(project_root: Path, relative: str) -> Path:
    return project_root / "src/demo_service" / relative


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
