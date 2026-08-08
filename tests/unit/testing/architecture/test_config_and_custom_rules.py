from __future__ import annotations

from pathlib import Path

import pytest

from specx.testing.architecture import (
    ArchitectureContext,
    BaseRule,
    SpecxArchitectureConfig,
    SpecxArchitectureViolation,
    SpecxConfigurationError,
    SpecxRuleId,
    check_specx_architecture,
)


class AlwaysFailRule(BaseRule[str, ArchitectureContext, SpecxArchitectureViolation]):
    """Project custom rule that always reports one violation for test coverage."""

    id = "custom.always-fails"

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        return (
            SpecxArchitectureViolation(
                rule_id=self.id,
                path=context.src_root,
                message="custom failure",
            ),
        )


@pytest.mark.parametrize("package_name", ["", "3demo", "bad-name", "class"])
def test_config_rejects_invalid_package_names(tmp_path: Path, package_name: str) -> None:
    with pytest.raises(SpecxConfigurationError, match="package_name"):
        SpecxArchitectureConfig(project_root=tmp_path, package_name=package_name)


def test_disabled_rules_suppress_only_selected_rule(tmp_path: Path) -> None:
    _write_minimal_project(tmp_path)
    disabled_rules = frozenset(
        rule_id
        for rule_id in SpecxRuleId
        if rule_id != SpecxRuleId.CLASSES_REQUIRE_EXAMPLE_DOCSTRINGS
    )

    enabled_report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=disabled_rules,
        )
    )
    disabled_report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=disabled_rules
            | frozenset({SpecxRuleId.CLASSES_REQUIRE_EXAMPLE_DOCSTRINGS}),
        )
    )

    assert {violation.rule_id for violation in enabled_report.violations} == {
        SpecxRuleId.CLASSES_REQUIRE_EXAMPLE_DOCSTRINGS,
    }
    assert disabled_report.violations == ()


def test_extra_rules_are_executed_and_can_be_disabled(tmp_path: Path) -> None:
    _write_minimal_project(tmp_path)
    all_builtin_rules = frozenset(SpecxRuleId)

    enabled_report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=all_builtin_rules,
            extra_rules=(AlwaysFailRule,),
        )
    )
    disabled_report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=all_builtin_rules | frozenset({AlwaysFailRule.id}),
            extra_rules=(AlwaysFailRule,),
        )
    )

    assert [violation.message for violation in enabled_report.violations] == ["custom failure"]
    assert disabled_report.violations == ()


def test_fastapi_rules_are_opt_in_and_warn_when_surface_is_missing(tmp_path: Path) -> None:
    _write_minimal_project(tmp_path)
    disabled_rules = frozenset(
        rule_id
        for rule_id in SpecxRuleId
        if rule_id
        not in {
            SpecxRuleId.FASTAPI_ROOT_AGENTS_MD_DOCUMENTS_ENTRYPOINT,
            SpecxRuleId.PUBLIC_ROUTES_USE_FULL_API_V1_PATHS,
        }
    )

    default_report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=disabled_rules,
        )
    )
    selected_report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            extend_select=frozenset({"fastapi"}),
            disabled_rules=disabled_rules,
        )
    )
    all_report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            select=frozenset({"ALL"}),
            disabled_rules=disabled_rules,
        )
    )

    assert default_report.violations == ()
    assert default_report.warnings == ()
    assert selected_report.violations == ()
    assert len(selected_report.warnings) == 1
    assert selected_report.warnings[0].rule_id == "fastapi"
    assert all_report.violations == ()
    assert all_report.warnings == ()


def _write_minimal_project(project_root: Path) -> None:
    _write(
        project_root / "src" / "demo_service" / "core" / "tasks" / "services" / "title_service.py",
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class TitleService(BasePureService):\n"
        "    def normalize(self, *, title: str) -> str:\n"
        "        return title.strip()\n",
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
