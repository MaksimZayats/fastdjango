from __future__ import annotations

import keyword
import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from specx._internal.cli_config import load_specx_config
from specx._internal.project_management.discovery import normalize_use_case_id
from specx._internal.project_management.exceptions import SpecxProjectError
from specx._internal.project_management.models import ScaffoldFile, UseCaseKind

_FIELD_PATTERN = re.compile(r"(?P<name>[a-z_][a-z0-9_]*):(?P<type>.+)")
_PRIMITIVE_TYPES = frozenset({"bool", "float", "int", "str"})


@dataclass(frozen=True, kw_only=True, slots=True)
class ScaffoldField:
    """Validated field requested for a generated contract."""

    name: str
    annotation: str
    optional: bool
    sample: str


def scaffold_use_case(
    project_root: Path,
    *,
    resource_id: str,
    kind: UseCaseKind,
    input_field_values: tuple[str, ...],
    result_field_values: tuple[str, ...],
    synchronous: bool,
    dry_run: bool,
) -> tuple[ScaffoldFile, ...]:
    """Render and optionally write one deterministic use-case scaffold."""

    normalized_id = normalize_use_case_id(resource_id)
    component, name = normalized_id.split("/", maxsplit=1)
    loaded = load_specx_config(project_root)
    root = loaded.architecture.project_root
    package_name = loaded.architecture.package_name
    input_fields = _parse_fields(input_field_values, label="input")
    result_fields = _parse_fields(result_field_values, label="result")
    files = _render_files(
        root=root,
        package_name=package_name,
        component=component,
        name=name,
        kind=kind,
        input_fields=input_fields,
        result_fields=result_fields,
        synchronous=synchronous,
    )
    conflicts = tuple(file.path for file in files if file.path.exists())
    if conflicts:
        relative = ", ".join(str(path.relative_to(root)) for path in conflicts)
        raise SpecxProjectError(
            f"refusing to overwrite existing scaffold files: {relative}",
            code="scaffold.conflict",
            hint="Choose a different use-case ID; specx intentionally has no force option.",
        )
    if not dry_run:
        written: list[Path] = []
        created_directories: set[Path] = set()
        try:
            for file in files:
                missing_parents = _missing_parents(file.path.parent, stop=root)
                file.path.parent.mkdir(parents=True, exist_ok=True)
                created_directories.update(missing_parents)
                file.path.write_text(file.content, encoding="utf-8")
                written.append(file.path)
        except OSError as error:
            for path in reversed(written):
                path.unlink(missing_ok=True)
            for directory in sorted(
                created_directories,
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                with suppress(OSError):
                    directory.rmdir()
            raise SpecxProjectError(
                f"could not write scaffold atomically: {error}",
                code="scaffold.write-failed",
                hint="No completed scaffold files were kept; fix the filesystem error and retry.",
            ) from error
    return files


def _parse_fields(values: tuple[str, ...], *, label: str) -> tuple[ScaffoldField, ...]:
    fields: list[ScaffoldField] = []
    names: set[str] = set()
    for value in values:
        match = _FIELD_PATTERN.fullmatch(value)
        if match is None:
            raise SpecxProjectError(f"invalid {label} field {value!r}; expected NAME:TYPE")
        name = match.group("name")
        if name.startswith("_"):
            raise SpecxProjectError(
                f"invalid {label} field name {name!r}: private names are not supported",
                code="scaffold.invalid-field-name",
                hint="Use a public lowercase snake_case name, for example `track_id:str`.",
            )
        if keyword.iskeyword(name):
            raise SpecxProjectError(
                f"invalid {label} field name {name!r}: Python keyword",
                code="scaffold.invalid-field-name",
                hint="Use a public lowercase snake_case field name.",
            )
        if name in names:
            raise SpecxProjectError(f"duplicate {label} field name {name!r}")
        names.add(name)
        annotation, optional, sample = _parse_type(match.group("type"), field=value)
        fields.append(
            ScaffoldField(name=name, annotation=annotation, optional=optional, sample=sample)
        )
    return tuple(fields)


def _parse_type(value: str, *, field: str) -> tuple[str, bool, str]:
    optional = value.endswith("?")
    base = value[:-1] if optional else value
    if base in _PRIMITIVE_TYPES:
        annotation = base
        sample = {"bool": "True", "float": "1.0", "int": "1", "str": '"example"'}[base]
    elif base.startswith("list[") and base.endswith("]"):
        item_type = base[5:-1]
        if item_type not in _PRIMITIVE_TYPES:
            raise SpecxProjectError(
                f"invalid field type in {field!r}; list items must be bool, float, int, or str"
            )
        annotation = f"list[{item_type}]"
        item_sample = {
            "bool": "True",
            "float": "1.0",
            "int": "1",
            "str": '"example"',
        }[item_type]
        sample = f"[{item_sample}]"
    else:
        raise SpecxProjectError(
            f"invalid field type in {field!r}; expected a primitive, TYPE?, or list[TYPE]"
        )
    if optional:
        return f"{annotation} | None", True, "None"
    return annotation, False, sample


def _render_files(
    *,
    root: Path,
    package_name: str,
    component: str,
    name: str,
    kind: UseCaseKind,
    input_fields: tuple[ScaffoldField, ...],
    result_fields: tuple[ScaffoldField, ...],
    synchronous: bool,
) -> tuple[ScaffoldFile, ...]:
    component_module = component.replace("-", "_")
    action_module = name.replace("-", "_")
    action_class = _pascal_case(name)
    input_suffix = "Command" if kind == "command" else "Query"
    input_class = f"{action_class}{input_suffix}"
    use_case_class = f"{action_class}UseCase"
    result_class = f"{action_class}ResultDTO"
    result_module = f"{action_module}_result_dto"
    source_component = root / "src" / package_name / "core" / component_module
    test_component = root / "tests" / "unit" / "core" / component_module
    primary_files = (
        ScaffoldFile(
            path=source_component / "dtos" / f"{result_module}.py",
            content=_render_result_dto(result_class=result_class, fields=result_fields),
        ),
        ScaffoldFile(
            path=source_component / "use_cases" / f"{action_module}.py",
            content=_render_use_case(
                package_name=package_name,
                component_module=component_module,
                result_module=result_module,
                action_class=action_class,
                input_class=input_class,
                use_case_class=use_case_class,
                result_class=result_class,
                kind=kind,
                fields=input_fields,
                synchronous=synchronous,
            ),
        ),
        ScaffoldFile(
            path=test_component / "use_cases" / f"test_{action_module}.py",
            content=_render_test(
                package_name=package_name,
                component_module=component_module,
                action_module=action_module,
                input_class=input_class,
                use_case_class=use_case_class,
                kind=kind,
                fields=input_fields,
                synchronous=synchronous,
            ),
        ),
    )
    initializer_directories = (
        root / "src" / package_name,
        root / "src" / package_name / "core",
        source_component,
        source_component / "dtos",
        source_component / "use_cases",
        root / "tests",
        root / "tests" / "unit",
        root / "tests" / "unit" / "core",
        test_component,
        test_component / "use_cases",
    )
    initializers = tuple(
        ScaffoldFile(path=directory / "__init__.py", content="")
        for directory in initializer_directories
        if not (directory / "__init__.py").exists()
    )
    return (*initializers, *primary_files)


def _render_result_dto(*, result_class: str, fields: tuple[ScaffoldField, ...]) -> str:
    field_lines = _render_field_lines(fields)
    example_arguments = _render_arguments(fields)
    return f'''from dataclasses import dataclass

from specx.core.foundation.dto import BaseDTO


@dataclass(frozen=True, kw_only=True, slots=True)
class {result_class}(BaseDTO):
    """Result returned by the generated application action.

    Example:
        {result_class}({example_arguments})

    """

{field_lines}
'''


def _render_use_case(
    *,
    package_name: str,
    component_module: str,
    result_module: str,
    action_class: str,
    input_class: str,
    use_case_class: str,
    result_class: str,
    kind: UseCaseKind,
    fields: tuple[ScaffoldField, ...],
    synchronous: bool,
) -> str:
    base_module = "command" if kind == "command" else "query"
    base_class = "BaseCommand" if kind == "command" else "BaseQuery"
    field_lines = _render_field_lines(fields)
    example_arguments = _render_arguments(fields)
    example_call = f"use_case.execute({kind}={input_class}({example_arguments}))"
    if not synchronous:
        example_call = f"await {example_call}"
    async_prefix = "" if synchronous else "async "
    return f'''from dataclasses import dataclass

from specx.core.foundation.{base_module} import {base_class}
from specx.core.foundation.use_case import BaseUseCase

from {package_name}.core.{component_module}.dtos.{result_module} import {result_class}


@dataclass(frozen=True, kw_only=True, slots=True)
class {input_class}({base_class}):
    """Input for the generated {action_class} action.

    Example:
        {input_class}({example_arguments})

    """

{field_lines}


@dataclass(kw_only=True, slots=True)
class {use_case_class}(BaseUseCase):
    """Generated application action awaiting domain behavior.

    Example:
        result = {example_call}

    """

    {async_prefix}def execute(self, *, {kind}: {input_class}) -> {result_class}:
        """Run the generated application action."""
        del {kind}
        message = "Implement {use_case_class}.execute"
        raise NotImplementedError(message)
'''


def _render_test(
    *,
    package_name: str,
    component_module: str,
    action_module: str,
    input_class: str,
    use_case_class: str,
    kind: UseCaseKind,
    fields: tuple[ScaffoldField, ...],
    synchronous: bool,
) -> str:
    asyncio_import = "import asyncio\n" if not synchronous else ""
    invocation = f"use_case.execute({kind}=input_value)"
    if not synchronous:
        invocation = f"asyncio.run({invocation})"
    return rf"""from __future__ import annotations

{asyncio_import}from typing import TYPE_CHECKING

import pytest

from {package_name}.core.{component_module}.use_cases.{action_module} import (
    {input_class},
    {use_case_class},
)

if TYPE_CHECKING:
    from diwire import Container


def test_execute_is_explicitly_unimplemented(container: Container) -> None:
    use_case = container.resolve({use_case_class})
    input_value = {input_class}({_render_arguments(fields)})

    with pytest.raises(NotImplementedError, match=r"Implement {use_case_class}\.execute"):
        {invocation}
"""


def _render_field_lines(fields: tuple[ScaffoldField, ...]) -> str:
    if not fields:
        return ""
    return "\n".join(
        f"    {field.name}: {field.annotation}{' = None' if field.optional else ''}"
        for field in fields
    )


def _render_arguments(fields: tuple[ScaffoldField, ...]) -> str:
    return ", ".join(f"{field.name}={field.sample}" for field in fields)


def _pascal_case(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("-"))


def _missing_parents(path: Path, *, stop: Path) -> tuple[Path, ...]:
    missing: list[Path] = []
    candidate = path
    while candidate != stop and not candidate.exists():
        missing.append(candidate)
        candidate = candidate.parent
    return tuple(missing)
