from __future__ import annotations

import ast
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from specx._internal.project_management.models import (
    ComponentDescriptor,
    FieldDescriptor,
    ProjectDescriptor,
    UseCaseDescriptor,
)


def components_payload(project: ProjectDescriptor) -> dict[str, Any]:
    """Return the versioned component-list JSON payload."""

    return {
        "version": 1,
        "root": str(project.root),
        "components": [
            {"name": component.name, "use_case_count": len(component.use_case_ids)}
            for component in project.components
        ],
    }


def component_payload(
    project: ProjectDescriptor,
    component: ComponentDescriptor,
) -> dict[str, Any]:
    """Return the versioned component-detail JSON payload."""

    return {
        "version": 1,
        "root": str(project.root),
        "component": {
            "name": component.name,
            "path": _relative(component.path, project.root),
            "use_cases": list(component.use_case_ids),
        },
    }


def use_cases_payload(
    project: ProjectDescriptor,
    use_cases: tuple[UseCaseDescriptor, ...],
) -> dict[str, Any]:
    """Return the versioned use-case-list JSON payload."""

    return {
        "version": 1,
        "root": str(project.root),
        "use_cases": [_use_case_summary(candidate, root=project.root) for candidate in use_cases],
    }


def use_case_payload(project: ProjectDescriptor, use_case: UseCaseDescriptor) -> dict[str, Any]:
    """Return the versioned use-case-detail JSON payload."""

    return {
        "version": 1,
        "root": str(project.root),
        "use_case": {
            **_use_case_summary(use_case, root=project.root),
            "module": use_case.module_name,
            "input": {
                "class": use_case.input_class_name,
                "parameter": use_case.input_parameter_name,
                "fields": [asdict(field) for field in use_case.input_fields],
                "example": _contract_example(use_case.input_fields),
            },
            "result": {
                "class": use_case.result_class_name,
                "fields": [asdict(field) for field in use_case.result_fields],
            },
            "dependencies": [asdict(field) for field in use_case.dependencies],
            "summary": use_case.summary,
        },
    }


def print_components(console: Console, project: ProjectDescriptor) -> None:
    """Render a component table for a terminal."""

    table = Table(title="Core components")
    table.add_column("Component", style="cyan")
    table.add_column("Use cases", justify="right")
    for component in project.components:
        table.add_row(component.name, str(len(component.use_case_ids)))
    console.print(Text(f"Root: {project.root}"), soft_wrap=True)
    if project.components:
        console.print(table)
    else:
        console.print(Text("No core components found."))
        console.print(
            Text(
                "Create the first one with `specx project use-case create "
                "<component>/<name> --kind query --dry-run`."
            )
        )


def print_component(
    console: Console,
    project: ProjectDescriptor,
    component: ComponentDescriptor,
) -> None:
    """Render one component and its use cases."""

    table = Table(title=f"Component: {component.name}")
    table.add_column("Use case", style="cyan")
    for resource_id in component.use_case_ids:
        table.add_row(resource_id)
    console.print(Text(f"Root: {project.root}"), soft_wrap=True)
    console.print(Text(f"Path: {_relative(component.path, project.root)}"))
    if component.use_case_ids:
        console.print(table)
    else:
        console.print(Text(f"No use cases found in component {component.name!r}."))
        console.print(
            Text(
                "Preview one with `specx project use-case create "
                f"{component.name}/<name> --kind query --dry-run`."
            )
        )


def print_use_cases(
    console: Console,
    project: ProjectDescriptor,
    use_cases: tuple[UseCaseDescriptor, ...],
) -> None:
    """Render a use-case summary table for a terminal."""

    table = Table(title="Use cases")
    table.add_column("ID", style="cyan")
    table.add_column("Kind")
    table.add_column("Execute")
    table.add_column("Class")
    for use_case in use_cases:
        table.add_row(
            use_case.resource_id,
            use_case.kind,
            "async" if use_case.is_async else "sync",
            use_case.class_name,
        )
    console.print(Text(f"Root: {project.root}"), soft_wrap=True)
    if use_cases:
        console.print(table)
    else:
        console.print(Text("No use cases found."))
        console.print(
            Text(
                "Preview one with `specx project use-case create "
                "<component>/<name> --kind query --dry-run`."
            )
        )


def print_use_case(
    console: Console,
    project: ProjectDescriptor,
    use_case: UseCaseDescriptor,
) -> None:
    """Render detailed static metadata for one use case."""

    details = Table.grid(padding=(0, 2))
    details.add_column(style="bold")
    details.add_column()
    rows = (
        ("ID", use_case.resource_id),
        ("Kind", use_case.kind),
        ("Execute", "async" if use_case.is_async else "sync"),
        ("Class", use_case.class_name),
        ("Input", _contract_text(use_case.input_class_name, use_case.input_fields)),
        ("Input JSON", json.dumps(_contract_example(use_case.input_fields), sort_keys=True)),
        ("Result", _contract_text(use_case.result_class_name, use_case.result_fields)),
        ("Dependencies", _dependency_text(use_case.dependencies)),
        ("Source", f"{_relative(use_case.path, project.root)}:{use_case.line}"),
        ("Summary", use_case.summary or "none"),
    )
    for label, value in rows:
        details.add_row(label, Text(value, overflow="fold"))
    console.print(Text(f"Root: {project.root}"), soft_wrap=True)
    console.print(Panel(details, title="Use case"))


def _use_case_summary(use_case: UseCaseDescriptor, *, root: Path) -> dict[str, Any]:
    return {
        "id": use_case.resource_id,
        "component": use_case.component,
        "name": use_case.name,
        "kind": use_case.kind,
        "execution": "async" if use_case.is_async else "sync",
        "class": use_case.class_name,
        "source": {"path": _relative(use_case.path, root), "line": use_case.line},
    }


def _contract_text(class_name: str, fields: tuple[FieldDescriptor, ...]) -> str:
    return f"{class_name}({_field_text(fields)})"


def _field_text(fields: tuple[FieldDescriptor, ...]) -> str:
    return (
        ", ".join(
            f"{field.name}: {field.annotation}"
            + (" (required)" if field.required else f" = {field.default}")
            for field in fields
        )
        or "none"
    )


def _dependency_text(fields: tuple[FieldDescriptor, ...]) -> str:
    return ", ".join(f"{field.name}: {field.annotation}" for field in fields) or "none"


def _contract_example(fields: tuple[FieldDescriptor, ...]) -> dict[str, Any]:
    return {field.name: _example_value(field) for field in fields}


def _example_value(field: FieldDescriptor) -> Any:
    if field.default is not None:
        try:
            return ast.literal_eval(field.default)
        except (SyntaxError, ValueError):
            pass
    annotation = field.annotation.replace(" ", "")
    if annotation.startswith("list["):
        return []
    if annotation == "bool":
        return False
    if annotation == "int":
        return 0
    if annotation == "float":
        return 0.0
    if annotation == "str":
        return ""
    if "None" in annotation:
        return None
    return f"<{field.annotation}>"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)
