from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxRuleId,
    check_specx_architecture,
)


def test_agents_md_rule_accepts_project_shape_and_commands(
    tmp_path: Path,
) -> None:
    _write_minimal_project_guidance(tmp_path)

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(
                SpecxRuleId.ROOT_AGENTS_MD_DOCUMENTS_PROJECT_COMMANDS
            ),
        )
    )

    assert report.violations == ()


def test_agents_md_rule_rejects_documented_missing_make_target(
    tmp_path: Path,
) -> None:
    _write_minimal_project_guidance(tmp_path)
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text(
        agents_path.read_text(encoding="utf-8") + "\n- `make deploy`\n",
        encoding="utf-8",
    )

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(
                SpecxRuleId.ROOT_AGENTS_MD_DOCUMENTS_PROJECT_COMMANDS
            ),
        )
    )

    assert len(report.violations) == 1
    assert "deploy" in report.violations[0].message


def test_agents_md_rule_requires_real_required_make_targets(tmp_path: Path) -> None:
    _write_minimal_project_guidance(tmp_path)
    (tmp_path / "Makefile").unlink()

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(
                SpecxRuleId.ROOT_AGENTS_MD_DOCUMENTS_PROJECT_COMMANDS
            ),
        )
    )

    assert any("missing required Make targets" in item.message for item in report.violations)


def test_agents_md_rule_allows_markdown_line_wrapping(tmp_path: Path) -> None:
    _write_minimal_project_guidance(tmp_path)
    agents_path = tmp_path / "AGENTS.md"
    text = agents_path.read_text(encoding="utf-8").replace(
        "Use cases return DTOs, not entities",
        "Use cases return DTOs,\n  not entities",
    )
    agents_path.write_text(text, encoding="utf-8")

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(
                SpecxRuleId.ROOT_AGENTS_MD_DOCUMENTS_PROJECT_COMMANDS
            ),
        )
    )

    assert report.violations == ()


def test_agents_md_rule_requires_only_class_categories_used_by_project(tmp_path: Path) -> None:
    _write_minimal_project_guidance(tmp_path)
    agents_path = tmp_path / "AGENTS.md"
    text = agents_path.read_text(encoding="utf-8")
    for optional_fragment in (
        "- BaseCapability\n",
        "- BaseGateway\n",
        "- BasePureService\n",
        "- BaseReadService\n",
        "- BaseEffectService\n",
        "- Use cases return DTOs, not entities\n",
        "- Query use cases must not call repository mutators\n",
        "- Use cases that touch persistence inject `UnitOfWorkManager`, open at most one\n"
        "  UoW scope, and must not inject repositories, active UoWs, providers,\n"
        "  SQLAlchemy sessions/engines/session factories, or concrete infrastructure\n"
        "  adapters directly.\n",
    ):
        text = text.replace(optional_fragment, "")
    agents_path.write_text(text, encoding="utf-8")

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(
                SpecxRuleId.ROOT_AGENTS_MD_DOCUMENTS_PROJECT_COMMANDS
            ),
        )
    )

    assert report.violations == ()


def test_agents_md_rule_does_not_require_repeated_architecture_policy(tmp_path: Path) -> None:
    _write_minimal_project_guidance(tmp_path)
    agents_path = tmp_path / "AGENTS.md"
    text = agents_path.read_text(encoding="utf-8").replace("- BaseCapability\n", "")
    agents_path.write_text(text, encoding="utf-8")
    _write(
        tmp_path / "src/demo_service/core/orders/capabilities/slug_capability.py",
        "from specx.core.foundation.capability import BaseCapability\n\n"
        "class SlugCapability(BaseCapability):\n"
        "    pass\n",
    )

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(
                SpecxRuleId.ROOT_AGENTS_MD_DOCUMENTS_PROJECT_COMMANDS
            ),
        )
    )

    assert report.violations == ()


def test_fastapi_agents_rule_is_opt_in(tmp_path: Path) -> None:
    _write_minimal_project_guidance(tmp_path)
    agents_path = tmp_path / "AGENTS.md"
    text = agents_path.read_text(encoding="utf-8").replace(
        "- FastAPI entrypoint: `demo_service.delivery.fastapi.__main__:app`\n",
        "",
    )
    agents_path.write_text(text, encoding="utf-8")
    _write(
        tmp_path / "src" / "demo_service" / "delivery" / "fastapi" / "__main__.py",
        "app = object()\n",
    )

    default_report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(
                SpecxRuleId.FASTAPI_ROOT_AGENTS_MD_DOCUMENTS_ENTRYPOINT
            ),
        )
    )
    selected_report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            extend_select=frozenset({"fastapi"}),
            disabled_rules=_disable_all_except(
                SpecxRuleId.FASTAPI_ROOT_AGENTS_MD_DOCUMENTS_ENTRYPOINT
            ),
        )
    )

    assert default_report.violations == ()
    assert len(selected_report.violations) == 1
    assert "FastAPI entrypoint" in selected_report.violations[0].message


def test_agents_rule_accepts_shared_multi_target_make_rules(tmp_path: Path) -> None:
    _write_minimal_project_guidance(tmp_path)
    _write(tmp_path / "Makefile", "check lint test:\n\t@true\n")

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(
                SpecxRuleId.ROOT_AGENTS_MD_DOCUMENTS_PROJECT_COMMANDS
            ),
        )
    )

    assert report.violations == ()


def _write_minimal_project_guidance(project_root: Path) -> None:
    _write(project_root / "src" / "demo_service" / "__init__.py", "")
    _write(
        project_root / "AGENTS.md",
        "# Agent Instructions\n\n"
        "- Package lives under `src/demo_service`\n"
        "- FastAPI entrypoint: `demo_service.delivery.fastapi.__main__:app`\n"
        "- make check\n"
        "- make lint\n"
        "- make test\n"
        "- uv run --locked specx check --output-format json\n"
        "- BaseCapability\n"
        "- BaseGateway\n"
        "- BasePureService\n"
        "- BaseReadService\n"
        "- BaseEffectService\n"
        "- Use cases return DTOs, not entities\n"
        "- Query use cases must not call repository mutators\n"
        "- Runtime logging is configured by `LoggingConfigurator`.\n"
        "- FastAPI lifespan uses `FastAPILifecycle` and calls `container.aclose()`.\n"
        "- Do not inject loggers; classes that log create local stdlib loggers.\n"
        "- Use cases that touch persistence inject `UnitOfWorkManager`, open at most one\n"
        "  UoW scope, and must not inject repositories, active UoWs, providers,\n"
        "  SQLAlchemy sessions/engines/session factories, or concrete infrastructure\n"
        "  adapters directly.\n",
    )
    _write(project_root / "Makefile", "check:\n\nlint:\n\ntest:\n")


def _disable_all_except(rule_id: SpecxRuleId) -> frozenset[SpecxRuleId]:
    return frozenset(candidate for candidate in SpecxRuleId if candidate != rule_id)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
