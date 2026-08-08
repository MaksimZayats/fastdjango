from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

UseCaseKind = Literal["command", "query"]


@dataclass(frozen=True, kw_only=True, slots=True)
class FieldDescriptor:
    """Static name, annotation, and default for one contract field."""

    name: str
    annotation: str
    required: bool
    default: str | None


@dataclass(frozen=True, kw_only=True, slots=True)
class UseCaseDescriptor:
    """Static management metadata for one project use case."""

    resource_id: str
    component: str
    name: str
    module_name: str
    class_name: str
    input_class_name: str
    input_parameter_name: str
    kind: UseCaseKind
    input_fields: tuple[FieldDescriptor, ...]
    result_class_name: str
    result_fields: tuple[FieldDescriptor, ...]
    dependencies: tuple[FieldDescriptor, ...]
    is_async: bool
    summary: str
    path: Path
    line: int


@dataclass(frozen=True, kw_only=True, slots=True)
class ComponentDescriptor:
    """Static management metadata for one core component."""

    name: str
    path: Path
    use_case_ids: tuple[str, ...]


@dataclass(frozen=True, kw_only=True, slots=True)
class ProjectDescriptor:
    """Discovered project components and use cases."""

    root: Path
    package_name: str
    components: tuple[ComponentDescriptor, ...]
    use_cases: tuple[UseCaseDescriptor, ...]

    def use_case(self, resource_id: str) -> UseCaseDescriptor:
        """Return one use case by canonical ID."""

        return next(
            candidate for candidate in self.use_cases if candidate.resource_id == resource_id
        )


@dataclass(frozen=True, kw_only=True, slots=True)
class ScaffoldFile:
    """One rendered file in an atomic use-case scaffold plan."""

    path: Path
    content: str
