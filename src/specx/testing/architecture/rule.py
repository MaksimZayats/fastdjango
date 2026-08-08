from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from inspect import getdoc
from typing import Generic, TypeVar

from specx.testing.architecture.guidance import BUILTIN_RULE_GUIDANCE

ContextT = TypeVar("ContextT")
ViolationT = TypeVar("ViolationT")
RuleIdT = TypeVar("RuleIdT", bound=StrEnum | str, covariant=True)


@dataclass(frozen=True, kw_only=True, slots=True)
class SpecxRuleMetadata:
    """Metadata used to select and explain one architecture rule."""

    rule_id: StrEnum | str
    family: str
    summary: str
    default_enabled: bool
    required_project_surface: str | None
    remediation: str | None = None
    documentation_url: str | None = None
    detection_boundary: str = "Static source and project-layout analysis."


class BaseRule(ABC, Generic[RuleIdT, ContextT, ViolationT]):
    """Base for one architecture rule with a stable identifier and typed result."""

    id: RuleIdT
    family = "neutral"
    default_enabled = True
    required_project_surface: str | None = None
    remediation: str | None = None
    detection_boundary = (
        "Static source and project-layout analysis only; see the rule documentation "
        "for precise detection limits."
    )

    @classmethod
    def metadata(cls) -> SpecxRuleMetadata:
        """Return stable selection and explanation metadata for this rule."""

        docstring = getdoc(cls) or cls.__name__
        is_builtin = cls.__module__.startswith("specx.testing.architecture.rules.")
        documentation_url = None
        remediation = cls.remediation
        detection_boundary = cls.detection_boundary
        if is_builtin:
            guidance = BUILTIN_RULE_GUIDANCE[str(cls.id)]
            documentation_anchor = cls.__module__.rsplit(".", maxsplit=1)[-1]
            documentation_url = (
                f"https://specx.dev/docs/reference/architecture-rules/#{documentation_anchor}"
            )
            if remediation is None:
                remediation = guidance.remediation
            if "detection_boundary" not in cls.__dict__:
                detection_boundary = guidance.detection_boundary
        return SpecxRuleMetadata(
            rule_id=cls.id,
            family=cls.family,
            summary=docstring.splitlines()[0],
            default_enabled=cls.default_enabled,
            required_project_surface=cls.required_project_surface,
            remediation=remediation,
            documentation_url=documentation_url,
            detection_boundary=detection_boundary,
        )

    @abstractmethod
    def check(self, context: ContextT) -> tuple[ViolationT, ...]:
        """Return every violation found by this rule for the supplied context."""
