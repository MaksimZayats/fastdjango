from __future__ import annotations

import ast
import builtins
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
    active_uow_names_from_manager_fields,
    attribute_chain,
    class_injected_unit_of_work_manager_field_names,
    injected_type_name,
    project_class_qualified_names,
    qualified_class_name,
    self_attribute_root_name,
)

AMBIENT_EXACT_CALLS = frozenset(
    {
        "asyncio.sleep",
        "builtins.open",
        "datetime.date.today",
        "datetime.datetime.now",
        "datetime.datetime.today",
        "datetime.datetime.utcnow",
        "os.chdir",
        "os.getcwd",
        "os.getpid",
        "os.getenv",
        "os.listdir",
        "os.lstat",
        "os.mkdir",
        "os.makedirs",
        "os.putenv",
        "os.remove",
        "os.removedirs",
        "os.rename",
        "os.renames",
        "os.replace",
        "os.rmdir",
        "os.scandir",
        "os.stat",
        "os.system",
        "os.unsetenv",
        "time.monotonic",
        "time.monotonic_ns",
        "time.perf_counter",
        "time.perf_counter_ns",
        "time.process_time",
        "time.sleep",
        "time.time",
        "time.time_ns",
        "uuid.uuid1",
        "uuid.uuid4",
        "uuid.uuid6",
        "uuid.uuid7",
        "uuid.uuid8",
    }
)
AMBIENT_PREFIXES = (
    "aiohttp.",
    "httpx.",
    "os.environ.",
    "random.",
    "requests.",
    "secrets.",
    "shutil.",
    "socket.",
    "subprocess.",
    "tempfile.",
    "urllib.request.",
)
FILESYSTEM_METHODS = frozenset(
    {
        "chmod",
        "cwd",
        "exists",
        "glob",
        "home",
        "is_dir",
        "is_file",
        "iterdir",
        "mkdir",
        "open",
        "owner",
        "read_bytes",
        "read_text",
        "readlink",
        "rename",
        "replace",
        "resolve",
        "rglob",
        "rmdir",
        "stat",
        "symlink_to",
        "touch",
        "unlink",
        "write_bytes",
        "write_text",
        "walk",
    }
)


def resolved_call_name(call: ast.Call, *, path: Path, context: ArchitectureContext) -> str:
    name = context.qualified_name(path, call.func)
    if "." not in name and hasattr(builtins, name):
        return f"builtins.{name}"
    return name


def is_ambient_runtime_call(
    call: ast.Call,
    *,
    path: Path,
    context: ArchitectureContext,
    function: ast.AsyncFunctionDef | ast.FunctionDef | None = None,
    class_node: ast.ClassDef | None = None,
) -> bool:
    name = resolved_call_name(call, path=path, context=context)
    if name in AMBIENT_EXACT_CALLS or name.startswith(AMBIENT_PREFIXES):
        return True
    chain = attribute_chain(call.func)
    path_roots: set[tuple[str, ...]] = (
        pathlib_object_chains(
            function,
            class_node=class_node,
            path=path,
            context=context,
        )
        if function is not None
        else set()
    )
    return bool(
        chain
        and chain[-1] in FILESYSTEM_METHODS
        and (
            "pathlib" in name
            or any(part in {"Path", "PurePath"} for part in chain)
            or any(tuple(chain[: len(root)]) == root for root in path_roots)
        )
    )


def pathlib_object_chains(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    *,
    class_node: ast.ClassDef | None,
    path: Path,
    context: ArchitectureContext,
) -> set[tuple[str, ...]]:
    names: set[tuple[str, ...]] = {
        (argument.arg,)
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        )
        if context.qualified_name(path, argument.annotation).endswith("pathlib.Path")
    }
    if class_node is not None:
        names.update(
            ("self", child.target.id)
            for child in class_node.body
            if isinstance(child, ast.AnnAssign)
            and isinstance(child.target, ast.Name)
            and context.qualified_name(path, child.annotation).endswith("pathlib.Path")
        )
    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if not context.qualified_name(path, node.value.func).endswith("pathlib.Path"):
                continue
            names.update((target.id,) for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if context.qualified_name(path, node.annotation).endswith("pathlib.Path"):
                names.add((node.target.id,))
    changed = True
    while changed:
        changed = False
        for node in ast.walk(function):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if not isinstance(value, ast.BinOp) or not isinstance(value.op, ast.Div):
                continue
            source = attribute_chain(value.left)
            if not source or not any(tuple(source[: len(root)]) == root for root in names):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                chain = attribute_chain(target)
                if chain and tuple(chain) not in names:
                    names.add(tuple(chain))
                    changed = True
    return names


def class_injected_field_names(class_node: ast.ClassDef, aliases: dict[str, str]) -> set[str]:
    return {
        child.target.id
        for child in class_node.body
        if isinstance(child, ast.AnnAssign)
        and isinstance(child.target, ast.Name)
        and injected_type_name(child.annotation, aliases)
    }


def call_is_injected_collaborator_or_uow(
    call: ast.Call,
    *,
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    class_node: ast.ClassDef,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    hierarchy = class_hierarchy(class_node, path=path, context=context)
    injected_fields = {
        field
        for node_path, node in hierarchy
        for field in class_injected_field_names(node, context.aliases(node_path))
    }
    if self_attribute_root_name(call.func) in injected_fields:
        return True
    manager_fields = {
        field
        for node_path, node in hierarchy
        for field in class_injected_unit_of_work_manager_field_names(
            node, context.aliases(node_path)
        )
    }
    active_uows = active_uow_names_from_manager_fields(function, manager_fields)
    chain = attribute_chain(call.func)
    return bool(chain and chain[0] in active_uows)


def class_hierarchy(
    class_node: ast.ClassDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> tuple[tuple[Path, ast.ClassDef], ...]:
    definitions = {
        qualified_class_name(node, source_path=candidate_path, context=context): (
            candidate_path,
            node,
        )
        for candidate_path in context.source_paths()
        for node in context.tree(candidate_path).body
        if isinstance(node, ast.ClassDef)
    }
    found: list[tuple[Path, ast.ClassDef]] = []
    visited: set[str] = set()

    def collect(node_path: Path, node: ast.ClassDef) -> None:
        key = f"{node_path}:{node.name}"
        if key in visited:
            return
        visited.add(key)
        found.append((node_path, node))
        for base in node.bases:
            resolved = context.qualified_name(node_path, base)
            candidate = definitions.get(resolved)
            if candidate is not None:
                collect(*candidate)

    collect(path, class_node)
    return tuple(found)


def is_statically_recognized_constructor(
    call: ast.Call,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    resolved = resolved_call_name(call, path=path, context=context)
    if resolved in project_class_qualified_names(context):
        return True
    if not resolved.startswith("builtins."):
        return False
    return isinstance(getattr(builtins, resolved.removeprefix("builtins."), None), type)


def ambient_environment_nodes(
    tree: ast.Module,
    *,
    path: Path,
    context: ArchitectureContext,
) -> tuple[ast.AST, ...]:
    nodes: list[ast.AST] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Attribute, ast.Name))
            and isinstance(node.ctx, ast.Load)
            and context.qualified_name(path, node) == "os.environ"
        ):
            nodes.append(node)
    return tuple(nodes)
