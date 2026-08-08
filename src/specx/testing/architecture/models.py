from __future__ import annotations

import keyword
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias

from specx._internal.exceptions import BaseSpecxError
from specx.testing.architecture.rule import BaseRule
from specx.testing.architecture.rule_id import SpecxRuleId

if TYPE_CHECKING:
    from specx.testing.architecture.context import ArchitectureContext


RuleIdentifier: TypeAlias = SpecxRuleId | StrEnum | str


class SpecxConfigurationError(BaseSpecxError):
    """Raised when a specx architecture configuration cannot be evaluated."""


def empty_disabled_rules() -> frozenset[RuleIdentifier]:
    return frozenset()


def empty_rule_selectors() -> frozenset[str]:
    return frozenset()


def empty_allowed_functions() -> frozenset[str]:
    return frozenset()


@dataclass(frozen=True, kw_only=True, slots=True)
class SpecxArchitectureViolation:
    """One architecture rule violation found in a project."""

    rule_id: RuleIdentifier
    message: str
    path: Path | None = None
    symbol: str | None = None
    line: int | None = None
    column: int | None = None
    hint: str | None = None
    documentation_url: str | None = None

    def format(self, *, project_root: Path) -> str:
        location = ""
        if self.path is not None:
            location = str(self.path.relative_to(project_root))
        if self.line is not None:
            location = f"{location}:{self.line}" if location else str(self.line)
        if self.column is not None:
            location = f"{location}:{self.column}" if location else str(self.column)
        if self.symbol is not None:
            location = f"{location}:{self.symbol}" if location else self.symbol
        return f"{location}: {self.message}" if location else self.message


@dataclass(frozen=True, kw_only=True, slots=True)
class SpecxArchitectureWarning:
    """One non-failing warning produced while evaluating architecture rules."""

    rule_id: RuleIdentifier
    message: str
    path: Path | None = None
    line: int | None = None
    column: int | None = None
    hint: str | None = None
    documentation_url: str | None = None


@dataclass(frozen=True, kw_only=True, slots=True)
class SpecxArchitectureReport:
    """Grouped architecture rule results for one checked project."""

    project_root: Path
    violations: tuple[SpecxArchitectureViolation, ...]
    warnings: tuple[SpecxArchitectureWarning, ...] = ()

    @property
    def has_violations(self) -> bool:
        return bool(self.violations)

    def format(self) -> str:
        if not self.violations and not self.warnings:
            return "specx architecture checks passed."

        lines: list[str] = []
        if self.warnings:
            lines.append("specx architecture warnings:")
            for warning in self.warnings:
                lines.append(f"- {warning.rule_id}: {warning.message}")
                if warning.hint is not None:
                    lines.append(f"  help: {warning.hint}")
                if warning.documentation_url is not None:
                    lines.append(f"  docs: {warning.documentation_url}")

        if not self.violations:
            lines.append("specx architecture checks passed.")
            return "\n".join(lines)

        grouped: dict[str, list[SpecxArchitectureViolation]] = defaultdict(list)
        for violation in self.violations:
            grouped[str(violation.rule_id)].append(violation)

        lines.append("specx architecture violations:")
        for rule_id in sorted(grouped):
            lines.append(f"- {rule_id}")
            for violation in grouped[rule_id]:
                lines.append(f"  - {violation.format(project_root=self.project_root)}")
                if violation.hint is not None:
                    lines.append(f"    help: {violation.hint}")
                if violation.documentation_url is not None:
                    lines.append(f"    docs: {violation.documentation_url}")
        return "\n".join(lines)


ArchitectureRule: TypeAlias = BaseRule[
    RuleIdentifier,
    "ArchitectureContext",
    SpecxArchitectureViolation,
]
ArchitectureRuleType: TypeAlias = type[ArchitectureRule]


@dataclass(frozen=True, kw_only=True, slots=True)
class SpecxArchitectureConfig:
    """Configuration for checking one Python service against specx rules."""

    project_root: Path
    package_name: str
    select: frozenset[str] | None = None
    extend_select: frozenset[str] = field(default_factory=empty_rule_selectors)
    disabled_rules: frozenset[RuleIdentifier] = field(default_factory=empty_disabled_rules)
    extra_rules: tuple[ArchitectureRuleType, ...] = ()
    path_exclusions: tuple[str, ...] = ()
    allowed_use_case_functions: frozenset[str] = field(default_factory=empty_allowed_functions)

    def __post_init__(self) -> None:
        if not self.package_name.isidentifier() or keyword.iskeyword(self.package_name):
            raise SpecxConfigurationError(
                f"package_name must be one non-keyword Python identifier, "
                f"got {self.package_name!r}",
            )

        normalized_root = self.project_root.expanduser()
        object.__setattr__(self, "project_root", normalized_root)
        malformed = sorted(
            name for name in self.allowed_use_case_functions if not _is_qualified_name(name)
        )
        if malformed:
            raise SpecxConfigurationError(
                "allowed_use_case_functions must contain exact dotted Python names; "
                f"invalid values: {malformed}"
            )


def _is_qualified_name(value: str) -> bool:
    parts = value.split(".")
    return (
        len(parts) >= 2
        and all(part.isidentifier() and not keyword.iskeyword(part) for part in parts)
        and "*" not in value
    )
