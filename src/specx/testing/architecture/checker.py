from __future__ import annotations

import ast
from dataclasses import replace

from specx._internal.python_ast.scanner import PythonAstScanner
from specx.testing.architecture.context import ArchitectureContext
from specx.testing.architecture.models import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxArchitectureViolation,
    SpecxArchitectureWarning,
)
from specx.testing.architecture.registry import SpecxRuleRegistry


def check_specx_architecture(config: SpecxArchitectureConfig) -> SpecxArchitectureReport:
    """Run enabled specx architecture rules and return a grouped report."""

    registry = SpecxRuleRegistry.build(extra_rules=config.extra_rules)
    enabled_rules = registry.enabled_rules(
        disabled_rules=config.disabled_rules,
        select=config.select,
        extend_select=config.extend_select,
    )
    scanner = PythonAstScanner(
        project_root=config.project_root,
        excluded_patterns=config.path_exclusions,
    )
    ast_project = scanner.scan(roots=(config.project_root / "src", config.project_root / "tests"))
    context = ArchitectureContext(config=config, ast_project=ast_project)
    violations: list[SpecxArchitectureViolation] = []

    warnings: list[SpecxArchitectureWarning] = []
    warned_families: set[str] = set()
    for rule_type in enabled_rules:
        metadata = rule_type.metadata()
        if metadata.required_project_surface is not None:
            surface = context.src_root / metadata.required_project_surface
            surface_has_python = any(
                path.is_relative_to(surface) for path in context.ast_project.files
            )
            if not surface_has_python:
                selected_explicitly = _is_explicit_surface_selection(
                    rule_id=str(metadata.rule_id),
                    family=metadata.family,
                    config=config,
                )
                if selected_explicitly and metadata.family not in warned_families:
                    warnings.append(
                        SpecxArchitectureWarning(
                            rule_id=metadata.family,
                            message=(
                                f"selected rule family requires Python files under "
                                f"src/{config.package_name}/{metadata.required_project_surface}"
                            ),
                            path=surface,
                            hint=(
                                "Add the selected technology surface or remove the explicit "
                                f"{metadata.family!r} selector."
                            ),
                            documentation_url=metadata.documentation_url,
                        )
                    )
                    warned_families.add(metadata.family)
                continue

        rule = rule_type()
        violations.extend(
            _with_rule_guidance(
                _with_source_location(violation, context=context),
                hint=metadata.remediation,
                documentation_url=metadata.documentation_url,
            )
            for violation in rule.check(context)
        )

    return SpecxArchitectureReport(
        project_root=config.project_root,
        violations=tuple(violations),
        warnings=tuple(warnings),
    )


def _is_explicit_surface_selection(
    *,
    rule_id: str,
    family: str,
    config: SpecxArchitectureConfig,
) -> bool:
    selectors = (config.select or frozenset()) | config.extend_select
    return rule_id in selectors or family in selectors


def assert_specx_architecture(config: SpecxArchitectureConfig) -> None:
    """Assert that a project satisfies every enabled specx architecture rule."""

    report = check_specx_architecture(config)
    if report.has_violations:
        raise AssertionError(report.format())


def _with_source_location(
    violation: SpecxArchitectureViolation,
    *,
    context: ArchitectureContext,
) -> SpecxArchitectureViolation:
    if violation.line is not None or violation.path not in context.ast_project.files:
        return violation
    if violation.symbol is None:
        return violation

    tree = context.tree(violation.path)
    node = next(
        (
            candidate
            for candidate in ast.walk(tree)
            if isinstance(candidate, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and candidate.name == violation.symbol
        ),
        None,
    )
    if node is None:
        return violation

    return replace(
        violation,
        line=node.lineno,
        column=node.col_offset + 1,
    )


def _with_rule_guidance(
    violation: SpecxArchitectureViolation,
    *,
    hint: str | None,
    documentation_url: str | None,
) -> SpecxArchitectureViolation:
    return replace(
        violation,
        hint=violation.hint or hint,
        documentation_url=violation.documentation_url or documentation_url,
    )
