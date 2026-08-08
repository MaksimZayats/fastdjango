from __future__ import annotations

import ast
import difflib
import keyword
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from specx._internal.cli_config import LoadedSpecxConfig, load_specx_config
from specx._internal.project_management.exceptions import SpecxProjectError
from specx._internal.project_management.models import (
    ComponentDescriptor,
    FieldDescriptor,
    ProjectDescriptor,
    UseCaseDescriptor,
    UseCaseKind,
)
from specx._internal.python_ast.scanner import PythonAstProject, PythonAstScanner, PythonSourceFile


def discover_project(project_root: Path) -> tuple[LoadedSpecxConfig, ProjectDescriptor]:
    """Discover structural components and managed use cases without importing project code."""

    loaded = load_specx_config(project_root)
    root = loaded.architecture.project_root
    package_name = loaded.architecture.package_name
    package_root = root / "src" / package_name
    core_root = package_root / "core"
    ast_project = PythonAstScanner(
        project_root=root,
        excluded_patterns=loaded.architecture.path_exclusions,
    ).scan((package_root,))
    class_index = _class_index(ast_project)
    base_index = _base_index(ast_project)

    component_paths = tuple(
        path
        for path in sorted(core_root.iterdir() if core_root.is_dir() else ())
        if path.is_dir() and path.name.isidentifier() and not path.name.startswith("_")
    )
    use_cases: list[UseCaseDescriptor] = []
    by_component: dict[str, list[str]] = defaultdict(list)
    seen_component_names: dict[str, Path] = {}
    for component_path in component_paths:
        component_name = _python_name_to_resource(component_path.name)
        previous = seen_component_names.get(component_name)
        if previous is not None:
            raise SpecxProjectError(
                f"component ID {component_name!r} is ambiguous between "
                f"{previous} and {component_path}"
            )
        seen_component_names[component_name] = component_path
        use_case_root = component_path / "use_cases"
        for path in sorted(use_case_root.glob("*.py")) if use_case_root.is_dir() else ():
            if path.name == "__init__.py" or path not in ast_project.files:
                continue
            descriptor = _discover_use_case(
                root=root,
                package_name=package_name,
                component_name=component_name,
                source=ast_project.source_file(path),
                class_index=class_index,
                base_index=base_index,
            )
            use_cases.append(descriptor)
            by_component[component_name].append(descriptor.resource_id)

    duplicates = _duplicates(candidate.resource_id for candidate in use_cases)
    if duplicates:
        raise SpecxProjectError(f"duplicate use-case IDs: {sorted(duplicates)}")

    components = tuple(
        ComponentDescriptor(
            name=_python_name_to_resource(path.name),
            path=path,
            use_case_ids=tuple(sorted(by_component[_python_name_to_resource(path.name)])),
        )
        for path in component_paths
    )
    return loaded, ProjectDescriptor(
        root=root,
        package_name=package_name,
        components=components,
        use_cases=tuple(sorted(use_cases, key=lambda candidate: candidate.resource_id)),
    )


def require_component(project: ProjectDescriptor, component_name: str) -> ComponentDescriptor:
    """Return a component or raise a user-facing project error."""

    available = tuple(candidate.name for candidate in project.components)
    try:
        normalized = _normalize_resource_segment(component_name, label="component")
    except SpecxProjectError as error:
        canonical = component_name.lower().replace("_", "-")
        raise SpecxProjectError(
            str(error),
            code="component.invalid-id",
            hint="Component IDs use lowercase kebab-case; list them with "
            "`specx project component list`.",
            available=available,
            suggestion=_closest_match(canonical, available),
        ) from error
    component = next(
        (candidate for candidate in project.components if candidate.name == normalized),
        None,
    )
    if component is None:
        suggestion = _closest_match(normalized, available)
        raise SpecxProjectError(
            f"unknown component {component_name!r}",
            code="component.not-found",
            hint="List components with `specx project component list`.",
            available=available,
            suggestion=suggestion,
        )
    return component


def require_use_case(project: ProjectDescriptor, resource_id: str) -> UseCaseDescriptor:
    """Return a use case or raise a user-facing project error."""

    available = tuple(candidate.resource_id for candidate in project.use_cases)
    try:
        normalized = normalize_use_case_id(resource_id)
    except SpecxProjectError as error:
        canonical = resource_id.lower().replace("_", "-")
        scoped = tuple(
            candidate
            for candidate in available
            if candidate.startswith(f"{canonical}/")
            or candidate.rsplit("/", maxsplit=1)[-1] == canonical
        )
        choices = scoped or available
        suggestion = choices[0] if len(scoped) == 1 else _closest_match(canonical, choices)
        raise SpecxProjectError(
            str(error),
            code="use-case.invalid-id",
            hint="Use `COMPONENT/NAME`; list IDs with `specx project use-case list`.",
            available=choices,
            suggestion=suggestion,
        ) from error
    use_case = next(
        (candidate for candidate in project.use_cases if candidate.resource_id == normalized),
        None,
    )
    if use_case is None:
        suggestion = _closest_match(normalized, available)
        raise SpecxProjectError(
            f"unknown use case {resource_id!r}",
            code="use-case.not-found",
            hint="List use cases with `specx project use-case list`.",
            available=available,
            suggestion=suggestion,
        )
    return use_case


def normalize_use_case_id(resource_id: str) -> str:
    """Validate and normalize a component/name resource ID."""

    parts = resource_id.split("/")
    if len(parts) != 2:
        raise SpecxProjectError(
            "use-case ID must have the form component/name",
            code="use-case.invalid-id",
            hint="Example: `playback/get-playback-status`.",
        )
    component = _normalize_resource_segment(parts[0], label="component")
    name = _normalize_resource_segment(parts[1], label="use-case name")
    return f"{component}/{name}"


def _discover_use_case(
    *,
    root: Path,
    package_name: str,
    component_name: str,
    source: PythonSourceFile,
    class_index: dict[str, list[tuple[Path, ast.ClassDef]]],
    base_index: dict[str, set[str]],
) -> UseCaseDescriptor:
    aliases = source.aliases
    classes = [node for node in source.tree.body if isinstance(node, ast.ClassDef)]
    use_case_classes = [
        node for node in classes if _inherits(node.name, node, "BaseUseCase", aliases, base_index)
    ]
    if len(use_case_classes) != 1:
        relative = source.path.relative_to(root)
        raise SpecxProjectError(
            f"{relative} must define exactly one BaseUseCase subclass; "
            f"found {len(use_case_classes)}"
        )
    use_case = use_case_classes[0]
    execute_methods = [
        node
        for node in use_case.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "execute"
    ]
    if len(execute_methods) != 1:
        raise SpecxProjectError(f"{use_case.name} must define exactly one execute method")
    execute = execute_methods[0]
    if len(execute.args.kwonlyargs) != 1:
        raise SpecxProjectError(
            f"{use_case.name}.execute must accept exactly one keyword-only input"
        )
    input_argument = execute.args.kwonlyargs[0]
    input_class_name = _annotation_leaf(input_argument.annotation, aliases)
    input_class = next((node for node in classes if node.name == input_class_name), None)
    if input_class is None:
        raise SpecxProjectError(
            f"{use_case.name}.execute input {input_class_name!r} "
            "must be declared in the same module"
        )
    if _inherits(input_class.name, input_class, "BaseCommand", aliases, base_index):
        kind: UseCaseKind = "command"
    elif _inherits(input_class.name, input_class, "BaseQuery", aliases, base_index):
        kind = "query"
    else:
        raise SpecxProjectError(f"{input_class.name} must inherit BaseCommand or BaseQuery")
    if input_argument.arg != kind:
        raise SpecxProjectError(
            f"{use_case.name}.execute input must be named {kind!r}, not {input_argument.arg!r}"
        )

    result_class_name = _annotation_leaf(execute.returns, aliases)
    result_candidates = [
        candidate
        for candidate in class_index.get(result_class_name, [])
        if candidate[0] == source.path
        or _class_symbol(
            root=root,
            package_name=package_name,
            path=candidate[0],
            class_name=result_class_name,
        )
        in source.imports
    ]
    if len(result_candidates) != 1:
        raise SpecxProjectError(
            f"cannot uniquely locate result class {result_class_name!r} for {use_case.name}"
        )
    _, result_class = result_candidates[0]
    module_name = ".".join(
        (package_name, *source.path.relative_to(root / "src" / package_name).with_suffix("").parts)
    )
    name = _python_name_to_resource(source.path.stem)
    summary = (ast.get_docstring(use_case) or "").strip().splitlines()[0]
    return UseCaseDescriptor(
        resource_id=f"{component_name}/{name}",
        component=component_name,
        name=name,
        module_name=module_name,
        class_name=use_case.name,
        input_class_name=input_class.name,
        input_parameter_name=input_argument.arg,
        kind=kind,
        input_fields=_fields(input_class),
        result_class_name=result_class.name,
        result_fields=_fields(result_class),
        dependencies=_fields(use_case),
        is_async=isinstance(execute, ast.AsyncFunctionDef),
        summary=summary,
        path=source.path,
        line=use_case.lineno,
    )


def _fields(class_node: ast.ClassDef) -> tuple[FieldDescriptor, ...]:
    fields: list[FieldDescriptor] = []
    for node in class_node.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        fields.append(
            FieldDescriptor(
                name=node.target.id,
                annotation=ast.unparse(node.annotation),
                required=node.value is None,
                default=ast.unparse(node.value) if node.value is not None else None,
            )
        )
    return tuple(fields)


def _class_index(project: PythonAstProject) -> dict[str, list[tuple[Path, ast.ClassDef]]]:
    index: dict[str, list[tuple[Path, ast.ClassDef]]] = defaultdict(list)
    for path, source in project.files.items():
        for node in source.tree.body:
            if isinstance(node, ast.ClassDef):
                index[node.name].append((path, node))
    return dict(index)


def _base_index(project: PythonAstProject) -> dict[str, set[str]]:
    index: dict[str, set[str]] = defaultdict(set)
    for source in project.files.values():
        for node in source.tree.body:
            if isinstance(node, ast.ClassDef):
                index[node.name].update(_base_names(node, source.aliases))
    return dict(index)


def _inherits(
    class_name: str,
    class_node: ast.ClassDef,
    target: str,
    aliases: dict[str, str],
    base_index: dict[str, set[str]],
) -> bool:
    direct = _base_names(class_node, aliases)
    if target in direct:
        return True
    pending = list(base_index.get(class_name, ()))
    visited: set[str] = set()
    while pending:
        candidate = pending.pop()
        if candidate == target:
            return True
        if candidate in visited:
            continue
        visited.add(candidate)
        pending.extend(base_index.get(candidate, ()))
    return False


def _base_names(class_node: ast.ClassDef, aliases: dict[str, str]) -> set[str]:
    return {_annotation_leaf(base, aliases) for base in class_node.bases}


def _annotation_leaf(annotation: ast.expr | None, aliases: dict[str, str]) -> str:
    if annotation is None:
        return ""
    if isinstance(annotation, ast.Name):
        return aliases.get(annotation.id, annotation.id).split(".")[-1]
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    if isinstance(annotation, ast.Subscript):
        return _annotation_leaf(annotation.value, aliases)
    return ast.unparse(annotation).split(".")[-1]


def _python_name_to_resource(value: str) -> str:
    return value.replace("_", "-")


def _class_symbol(*, root: Path, package_name: str, path: Path, class_name: str) -> str:
    relative_module = path.relative_to(root / "src" / package_name).with_suffix("")
    return ".".join((package_name, *relative_module.parts, class_name))


def _normalize_resource_segment(value: str, *, label: str) -> str:
    if not value or value.startswith("-") or value.endswith("-"):
        raise SpecxProjectError(f"{label} must be lowercase kebab-case")
    if any(
        not ("a" <= character <= "z" or "0" <= character <= "9" or character == "-")
        for character in value
    ):
        raise SpecxProjectError(f"{label} must be lowercase kebab-case")
    if "--" in value or not "a" <= value[0] <= "z":
        raise SpecxProjectError(f"{label} must be lowercase kebab-case and start with a letter")
    if keyword.iskeyword(value.replace("-", "_")):
        raise SpecxProjectError(f"{label} must not normalize to a Python keyword")
    return value


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _closest_match(value: str, available: tuple[str, ...]) -> str | None:
    matches = difflib.get_close_matches(value, available, n=1, cutoff=0.45)
    return matches[0] if matches else None
