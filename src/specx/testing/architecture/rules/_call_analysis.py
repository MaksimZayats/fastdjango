from __future__ import annotations

import ast
import builtins
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
    active_uow_names_from_manager_fields,
    attribute_chain,
    class_injected_unit_of_work_manager_field_names,
    project_class_qualified_names,
    qualified_class_name,
)

AMBIENT_EXACT_CALLS = frozenset(
    {
        "asyncio.sleep",
        "builtins.open",
        "datetime.date.today",
        "datetime.datetime.now",
        "datetime.datetime.today",
        "datetime.datetime.utcnow",
        "io.open",
        "os.chdir",
        "os.getcwd",
        "os.getegid",
        "os.geteuid",
        "os.getgid",
        "os.getlogin",
        "os.getpid",
        "os.getppid",
        "os.getuid",
        "os.getenv",
        "os.listdir",
        "os.lstat",
        "os.mkdir",
        "os.makedirs",
        "os.putenv",
        "os.urandom",
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
        "os.path.exists",
        "os.path.abspath",
        "os.path.expanduser",
        "os.path.expandvars",
        "os.path.getatime",
        "os.path.getctime",
        "os.path.getmtime",
        "os.path.getsize",
        "os.path.isdir",
        "os.path.isfile",
        "os.path.islink",
        "os.path.ismount",
        "os.path.lexists",
        "os.path.realpath",
        "os.path.samefile",
        "sys.exit",
        "getpass.getuser",
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
    "locale.",
    "platform.",
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
AMBIENT_VALUE_NAMES = frozenset(
    {
        "sys.argv",
        "sys.base_prefix",
        "sys.executable",
        "sys.path",
        "sys.platform",
        "sys.prefix",
        "time.altzone",
        "time.daylight",
        "time.timezone",
        "time.tzname",
    }
)
SAFE_STDLIB_CONSTRUCTORS = frozenset(
    {
        "datetime.date",
        "datetime.datetime",
        "datetime.time",
        "datetime.timedelta",
        "datetime.timezone",
        "decimal.Decimal",
        "fractions.Fraction",
        "pathlib.Path",
        "pathlib.PosixPath",
        "pathlib.PurePath",
        "pathlib.PurePosixPath",
        "pathlib.PureWindowsPath",
        "pathlib.WindowsPath",
        "uuid.UUID",
    }
)


def resolved_call_name(call: ast.Call, *, path: Path, context: ArchitectureContext) -> str:
    names = resolved_call_names(call, path=path, context=context)
    return next(iter(names)) if len(names) == 1 else f"<ambiguous:{','.join(sorted(names))}>"


def resolved_call_names(
    call: ast.Call,
    *,
    path: Path,
    context: ArchitectureContext,
) -> frozenset[str]:
    return frozenset(
        f"builtins.{name}" if "." not in name and hasattr(builtins, name) else name
        for name in context.qualified_names(path, call.func)
    )


def is_ambient_runtime_call(
    call: ast.Call,
    *,
    path: Path,
    context: ArchitectureContext,
    function: ast.AsyncFunctionDef | ast.FunctionDef | None = None,
    class_node: ast.ClassDef | None = None,
    class_path: Path | None = None,
) -> bool:
    names = resolved_call_names(call, path=path, context=context)
    if any(name in AMBIENT_EXACT_CALLS or name.startswith(AMBIENT_PREFIXES) for name in names):
        return True
    if any(
        name.startswith(f"{ambient_value}.")
        for name in names
        for ambient_value in AMBIENT_VALUE_NAMES
    ):
        return True
    if "datetime.date.fromtimestamp" in names:
        return True
    if "datetime.datetime.fromtimestamp" in names and _timezone_argument_is_ambient(call):
        return True
    name = resolved_call_name(call, path=path, context=context)
    if (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "astimezone"
        and not call.args
        and not call.keywords
        and (
            any(name.startswith("datetime.") for name in names)
            or _call_receiver_is_typed_datetime(
                call,
                function=function,
                class_node=class_node,
                path=path,
                class_path=class_path,
                context=context,
            )
        )
    ):
        return True
    chain = attribute_chain(call.func)
    path_roots: set[tuple[str, ...]] = (
        pathlib_object_chains(
            function,
            class_node=class_node,
            path=path,
            class_path=class_path,
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


def _timezone_argument_is_ambient(call: ast.Call) -> bool:
    if len(call.args) >= 2:
        return isinstance(call.args[1], ast.Constant) and call.args[1].value is None
    timezone = next((keyword.value for keyword in call.keywords if keyword.arg == "tz"), None)
    return timezone is None or (isinstance(timezone, ast.Constant) and timezone.value is None)


def _call_receiver_is_typed_datetime(
    call: ast.Call,
    *,
    function: ast.AsyncFunctionDef | ast.FunctionDef | None,
    class_node: ast.ClassDef | None,
    path: Path,
    class_path: Path | None,
    context: ArchitectureContext,
) -> bool:
    if function is None or not isinstance(call.func, ast.Attribute):
        return False
    receiver = attribute_chain(call.func.value)
    if not receiver:
        return False
    roots = _typed_datetime_chains(
        function,
        class_node=class_node,
        path=path,
        class_path=class_path,
        context=context,
    )
    return any(tuple(receiver[: len(root)]) == root for root in roots)


def _typed_datetime_chains(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    *,
    class_node: ast.ClassDef | None,
    path: Path,
    class_path: Path | None,
    context: ArchitectureContext,
) -> set[tuple[str, ...]]:
    names: set[tuple[str, ...]] = {
        (argument.arg,)
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        )
        if _annotation_contains_datetime(argument.annotation, path=path, context=context)
    }
    if class_node is not None:
        for node_path, hierarchy_node in class_hierarchy(
            class_node,
            path=class_path or path,
            context=context,
        ):
            names.update(
                ("self", child.target.id)
                for child in hierarchy_node.body
                if isinstance(child, ast.AnnAssign)
                and isinstance(child.target, ast.Name)
                and _annotation_contains_datetime(
                    child.annotation,
                    path=node_path,
                    context=context,
                )
            )
    names.update(
        (node.target.id,)
        for node in ast.walk(function)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and _annotation_contains_datetime(node.annotation, path=path, context=context)
    )
    return names


def _annotation_contains_datetime(
    annotation: ast.expr | None,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    if annotation is None:
        return False
    if context.qualified_name(path, annotation) == "datetime.datetime":
        return True
    return any(
        _annotation_contains_datetime(child, path=path, context=context)
        for child in ast.iter_child_nodes(annotation)
        if isinstance(child, ast.expr)
    )


def pathlib_object_chains(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    *,
    class_node: ast.ClassDef | None,
    path: Path,
    class_path: Path | None = None,
    context: ArchitectureContext,
) -> set[tuple[str, ...]]:
    names: set[tuple[str, ...]] = {
        (argument.arg,)
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        )
        if _annotation_contains_path(argument.annotation, path=path, context=context)
    }
    if class_node is not None:
        for node_path, hierarchy_node in class_hierarchy(
            class_node,
            path=class_path or path,
            context=context,
        ):
            names.update(
                ("self", child.target.id)
                for child in hierarchy_node.body
                if isinstance(child, ast.AnnAssign)
                and isinstance(child.target, ast.Name)
                and _annotation_contains_path(
                    child.annotation,
                    path=node_path,
                    context=context,
                )
            )
    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if not context.qualified_name(path, node.value.func).endswith("pathlib.Path"):
                continue
            names.update((target.id,) for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if _annotation_contains_path(node.annotation, path=path, context=context):
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


def _annotation_contains_path(
    annotation: ast.expr | None,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    if annotation is None:
        return False
    if context.qualified_name(path, annotation) == "pathlib.Path":
        return True
    return any(
        _annotation_contains_path(child, path=path, context=context)
        for child in ast.iter_child_nodes(annotation)
        if isinstance(child, ast.expr)
    )


def class_injected_field_names(
    class_node: ast.ClassDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> set[str]:
    return {
        child.target.id
        for child in class_node.body
        if isinstance(child, ast.AnnAssign)
        and isinstance(child.target, ast.Name)
        and isinstance(child.annotation, ast.Subscript)
        and context.qualified_name(path, child.annotation.value) == "diwire.Injected"
    }


def class_injected_callable_field_names(
    class_node: ast.ClassDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> set[str]:
    fields: set[str] = set()
    for child in class_node.body:
        if not isinstance(child, ast.AnnAssign) or not isinstance(child.target, ast.Name):
            continue
        annotation = child.annotation
        if (
            not isinstance(annotation, ast.Subscript)
            or context.qualified_name(path, annotation.value) != "diwire.Injected"
        ):
            continue
        if _annotation_is_callable(annotation.slice, path=path, context=context, visited=set()):
            fields.add(child.target.id)
    return fields


def _annotation_is_callable(
    annotation: ast.expr,
    *,
    path: Path,
    context: ArchitectureContext,
    visited: set[str],
) -> bool:
    root = annotation.value if isinstance(annotation, ast.Subscript) else annotation
    qualified = context.qualified_name(path, root)
    if qualified in {"collections.abc.Callable", "typing.Callable"}:
        return True
    if qualified in visited:
        return False
    for alias_path in context.source_paths():
        for node in context.tree(alias_path).body:
            alias_name: str | None = None
            value: ast.expr | None = None
            type_alias_name = getattr(node, "name", None)
            type_alias_value = getattr(node, "value", None)
            if (
                type(node).__name__ == "TypeAlias"
                and isinstance(type_alias_name, ast.Name)
                and isinstance(type_alias_value, ast.expr)
            ):
                alias_name, value = type_alias_name.id, type_alias_value
            elif (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                alias_name, value = node.targets[0].id, node.value
            if alias_name is None or value is None:
                continue
            module = ".".join(
                (
                    context.config.package_name,
                    *alias_path.relative_to(context.src_root).with_suffix("").parts,
                )
            )
            alias_qualified = f"{module}.{alias_name}"
            if alias_qualified == qualified or (alias_path == path and alias_name == qualified):
                return _annotation_is_callable(
                    value,
                    path=alias_path,
                    context=context,
                    visited={*visited, qualified},
                )
    return False


def call_is_injected_collaborator_or_uow(
    call: ast.Call,
    *,
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    class_node: ast.ClassDef,
    path: Path,
    context: ArchitectureContext,
    class_path: Path | None = None,
) -> bool:
    hierarchy = class_hierarchy(class_node, path=class_path or path, context=context)
    injected_fields = {
        field
        for node_path, node in hierarchy
        for field in class_injected_field_names(
            node,
            path=node_path,
            context=context,
        )
    }
    callable_fields = {
        field
        for node_path, node in hierarchy
        for field in class_injected_callable_field_names(
            node,
            path=node_path,
            context=context,
        )
    }
    resolved_chains = [tuple(name.split(".")) for name in context.qualified_names(path, call.func)]
    allowed_fields = injected_fields - callable_fields
    if resolved_chains and all(
        len(chain) >= 2 and chain[0] == "self" and chain[1] in allowed_fields
        for chain in resolved_chains
    ):
        return True
    manager_fields = {
        field
        for node_path, node in hierarchy
        for field in class_injected_unit_of_work_manager_field_names(
            node, context.aliases(node_path)
        )
    }
    active_uows = active_uow_names_from_manager_fields(function, manager_fields)
    return bool(
        resolved_chains
        and all(resolved_chain[0] in active_uows for resolved_chain in resolved_chains)
    )


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
    resolved_names = resolved_call_names(call, path=path, context=context)
    project_classes = project_class_qualified_names(context)
    return bool(resolved_names) and all(
        resolved in project_classes
        or resolved in SAFE_STDLIB_CONSTRUCTORS
        or (
            resolved.startswith("builtins.")
            and isinstance(getattr(builtins, resolved.removeprefix("builtins."), None), type)
        )
        for resolved in resolved_names
    )


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


def ambient_runtime_value_nodes(
    tree: ast.Module,
    *,
    path: Path,
    context: ArchitectureContext,
) -> tuple[ast.expr, ...]:
    """Return direct reads of ambient runtime values that are not calls."""

    return tuple(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute))
        and isinstance(node.ctx, ast.Load)
        and context.qualified_name(path, node) in AMBIENT_VALUE_NAMES
    )
