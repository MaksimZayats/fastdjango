from __future__ import annotations

import ast
import builtins
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
    active_uow_names_from_manager_fields,
    attribute_chain,
    project_class_hierarchy,
    project_class_qualified_names,
)

AMBIENT_EXACT_CALLS = frozenset(
    {
        "asyncio.current_task",
        "asyncio.get_event_loop",
        "asyncio.get_running_loop",
        "asyncio.open_connection",
        "asyncio.open_unix_connection",
        "asyncio.sleep",
        "asyncio.create_subprocess_exec",
        "asyncio.create_subprocess_shell",
        "asyncio.start_server",
        "asyncio.start_unix_server",
        "builtins.input",
        "builtins.open",
        "datetime.date.today",
        "datetime.datetime.now",
        "datetime.datetime.today",
        "datetime.datetime.utcnow",
        "io.open",
        "os.access",
        "os.chdir",
        "os.device_encoding",
        "os.dup",
        "os.dup2",
        "os.cpu_count",
        "os.fdatasync",
        "os.fdopen",
        "os.fstat",
        "os.fsync",
        "os.ftruncate",
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
        "os.close",
        "os.kill",
        "os.killpg",
        "os.mkdir",
        "os.makedirs",
        "os.open",
        "os.pipe",
        "os.pipe2",
        "os.posix_fadvise",
        "os.posix_fallocate",
        "os.pread",
        "os.preadv",
        "os.putenv",
        "os.pwrite",
        "os.pwritev",
        "os.read",
        "os.readv",
        "os.urandom",
        "os.remove",
        "os.removedirs",
        "os.rename",
        "os.renames",
        "os.replace",
        "os.rmdir",
        "os.scandir",
        "os.stat",
        "os.sendfile",
        "os.splice",
        "os.system",
        "os.truncate",
        "os.ttyname",
        "os.unsetenv",
        "os.walk",
        "os.write",
        "os.writev",
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
        "time.clock_gettime",
        "time.clock_gettime_ns",
        "time.clock_settime",
        "time.clock_settime_ns",
        "time.get_clock_info",
        "time.perf_counter",
        "time.perf_counter_ns",
        "time.process_time",
        "time.process_time_ns",
        "time.sleep",
        "time.time",
        "time.time_ns",
        "time.thread_time",
        "time.thread_time_ns",
        "uuid.getnode",
        "uuid.uuid1",
        "uuid.uuid4",
        "uuid.uuid6",
        "uuid.uuid7",
        "uuid.uuid8",
    }
)
AMBIENT_PREFIXES = (
    "aiohttp.",
    "asyncio.get_event_loop.",
    "asyncio.get_running_loop.",
    "glob.",
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
        "absolute",
        "cwd",
        "exists",
        "expanduser",
        "glob",
        "group",
        "home",
        "is_block_device",
        "is_char_device",
        "is_dir",
        "is_fifo",
        "is_file",
        "is_junction",
        "is_mount",
        "is_socket",
        "is_symlink",
        "iterdir",
        "lchmod",
        "lstat",
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
        "samefile",
        "stat",
        "symlink_to",
        "touch",
        "unlink",
        "write_bytes",
        "write_text",
        "walk",
    }
)
PATHLIB_CONSTRUCTORS = frozenset(
    {
        "pathlib.Path",
        "pathlib.PosixPath",
        "pathlib.PurePath",
        "pathlib.PurePosixPath",
        "pathlib.PureWindowsPath",
        "pathlib.WindowsPath",
    }
)
PATH_PRESERVING_MEMBERS = frozenset(
    {
        "absolute",
        "expanduser",
        "joinpath",
        "parent",
        "parents",
        "resolve",
        "with_name",
        "with_stem",
        "with_suffix",
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
    receiver = attribute_chain(call.func.value) if isinstance(call.func, ast.Attribute) else ()
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
            or any(_path_receiver_matches_root(receiver, root) for root in path_roots)
        )
    )


def _path_receiver_matches_root(
    receiver: tuple[str, ...],
    root: tuple[str, ...],
) -> bool:
    if receiver == root:
        return True
    return receiver[: len(root)] == root and all(
        member in PATH_PRESERVING_MEMBERS for member in receiver[len(root) :]
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
        for node in _function_scope_nodes(function)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and _annotation_contains_datetime(node.annotation, path=path, context=context)
    )
    _propagate_direct_object_aliases(function, names)
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
    for node in _function_scope_nodes(function):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if context.qualified_name(path, node.value.func) not in PATHLIB_CONSTRUCTORS:
                continue
            names.update((target.id,) for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if _annotation_contains_path(node.annotation, path=path, context=context):
                names.add((node.target.id,))
    changed = True
    while changed:
        changed = False
        for node in _function_scope_nodes(function):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if not isinstance(value, ast.BinOp) or not isinstance(value.op, ast.Div):
                continue
            source = attribute_chain(value.left)
            if not source or not any(
                _path_receiver_matches_root(tuple(source), root) for root in names
            ):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                chain = attribute_chain(target)
                if chain and tuple(chain) not in names:
                    names.add(tuple(chain))
                    changed = True
    _propagate_direct_object_aliases(function, names)
    return names


def _propagate_direct_object_aliases(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    names: set[tuple[str, ...]],
) -> None:
    changed = True
    while changed:
        changed = False
        for node in _function_scope_nodes(function):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            source = attribute_chain(node.value)
            if not source or tuple(source) not in names:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                chain = attribute_chain(target)
                if chain and tuple(chain) not in names:
                    names.add(tuple(chain))
                    changed = True


def _function_scope_nodes(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
) -> tuple[ast.AST, ...]:
    nodes: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        if node is not function and isinstance(
            node,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        ):
            return
        nodes.append(node)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(function)
    return tuple(nodes)


def function_behavior_nodes(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
) -> tuple[ast.AST, ...]:
    """Return executable method nodes without dormant nested-scope bodies."""

    nodes: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        if node is not function and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for expression in (
                *node.decorator_list,
                *node.args.defaults,
                *(default for default in node.args.kw_defaults if default is not None),
            ):
                visit(expression)
            return
        if node is not function and isinstance(node, ast.ClassDef):
            for expression in (*node.decorator_list, *node.bases):
                visit(expression)
            for keyword in node.keywords:
                visit(keyword.value)
            return
        if isinstance(node, ast.Lambda):
            for expression in (
                *node.args.defaults,
                *(default for default in node.args.kw_defaults if default is not None),
            ):
                visit(expression)
            return
        nodes.append(node)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(function)
    return tuple(nodes)


def class_method_declarations(
    class_node: ast.ClassDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> dict[str, tuple[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef], ...]]:
    """Return runtime-effective method groups, including exact function assignments."""

    project_functions = _project_function_definitions(context)
    declarations: dict[
        str,
        list[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef]],
    ] = {}
    for child in class_node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            existing = declarations.get(child.name, [])
            if existing and all(
                _function_is_overload(function, path=function_path, context=context)
                for function_path, function in existing
            ):
                existing.append((path, child))
                declarations[child.name] = existing
            elif _function_is_overload(child, path=path, context=context):
                declarations.setdefault(child.name, []).append((path, child))
            else:
                declarations[child.name] = [(path, child)]
            continue
        targets: tuple[ast.expr, ...] = ()
        value: ast.expr | None = None
        if isinstance(child, ast.Assign):
            targets, value = tuple(child.targets), child.value
        elif isinstance(child, ast.AnnAssign) and child.value is not None:
            targets, value = (child.target,), child.value
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            qualified = context.qualified_name(path, value)
            attached = project_functions.get(qualified)
            if attached is None:
                declarations.pop(target.id, None)
            else:
                declarations[target.id] = list(attached)
    return {name: tuple(group) for name, group in declarations.items()}


def _project_function_definitions(
    context: ArchitectureContext,
) -> dict[str, tuple[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef], ...]]:
    definitions: dict[
        str,
        list[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef]],
    ] = {}
    for path in context.source_paths():
        module = ".".join(
            (
                context.config.package_name,
                *path.relative_to(context.src_root).with_suffix("").parts,
            )
        )
        for function in _module_scope_function_nodes(context.tree(path)):
            definitions.setdefault(f"{module}.{function.name}", []).append((path, function))
    return {name: tuple(group) for name, group in definitions.items()}


def _module_scope_function_nodes(
    tree: ast.Module,
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]:
    functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node)
            return
        if isinstance(node, (ast.ClassDef, ast.Lambda)):
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return tuple(functions)


def _function_is_overload(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    overloads = {"typing.overload", "typing_extensions.overload"}
    return any(
        context.qualified_names(path, decorator) <= overloads
        for decorator in function.decorator_list
    )


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


def _injected_annotation_payload(
    annotation: ast.expr,
    *,
    path: Path,
    context: ArchitectureContext,
    visited: frozenset[str],
) -> tuple[Path, ast.expr] | None:
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:
            parsed = ast.parse(annotation.value, mode="eval").body
        except SyntaxError:
            return None
        return _injected_annotation_payload(
            parsed,
            path=path,
            context=context,
            visited=visited,
        )
    if (
        isinstance(annotation, ast.Subscript)
        and context.qualified_name(path, annotation.value) == "diwire.Injected"
    ):
        return path, annotation.slice
    qualified = context.qualified_name(path, annotation)
    if qualified in visited:
        return None
    alias = _project_alias_expression(qualified, path=path, context=context)
    if alias is None:
        return None
    alias_path, expression = alias
    return _injected_annotation_payload(
        expression,
        path=alias_path,
        context=context,
        visited=visited | {qualified},
    )


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
    alias = _project_alias_expression(qualified, path=path, context=context)
    if alias is not None:
        alias_path, value = alias
        return _annotation_is_callable(
            value,
            path=alias_path,
            context=context,
            visited={*visited, qualified},
        )
    return False


def _project_alias_expression(
    qualified_name: str,
    *,
    path: Path,
    context: ArchitectureContext,
) -> tuple[Path, ast.expr] | None:
    for alias_path in context.source_paths():
        module = ".".join(
            (
                context.config.package_name,
                *alias_path.relative_to(context.src_root).with_suffix("").parts,
            )
        )
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
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.value is not None
            ):
                alias_name, value = node.target.id, node.value
            if alias_name is None or value is None:
                continue
            if qualified_name in {alias_name, f"{module}.{alias_name}"} and (
                alias_path == path or qualified_name == f"{module}.{alias_name}"
            ):
                return alias_path, value
    return None


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
    effective_annotations: dict[str, tuple[Path, ast.expr]] = {}
    for node_path, node in hierarchy:
        for child in node.body:
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                effective_annotations.setdefault(child.target.id, (node_path, child.annotation))
    injected_payloads = {
        field: payload
        for field, (node_path, annotation) in effective_annotations.items()
        if (
            payload := _injected_annotation_payload(
                annotation,
                path=node_path,
                context=context,
                visited=frozenset(),
            )
        )
        is not None
    }
    injected_fields = set(injected_payloads)
    callable_fields = {
        field
        for field, (payload_path, payload) in injected_payloads.items()
        if _annotation_is_callable(
            payload,
            path=payload_path,
            context=context,
            visited=set(),
        )
    }
    resolved_chains = [tuple(name.split(".")) for name in context.qualified_names(path, call.func)]
    allowed_fields = injected_fields - callable_fields
    if (
        resolved_chains
        and not _self_fields_reassigned_before(
            function,
            call,
            fields=allowed_fields,
        )
        and all(
            len(chain) >= 2 and chain[0] == "self" and chain[1] in allowed_fields
            for chain in resolved_chains
        )
    ):
        return True
    manager_fields = {
        field
        for field, (payload_path, payload) in injected_payloads.items()
        if context.qualified_name(payload_path, payload).endswith("UnitOfWorkManager")
    }
    active_uows = active_uow_names_from_manager_fields(function, manager_fields)
    return bool(
        resolved_chains
        and not _self_fields_reassigned_before(function, call, fields=manager_fields)
        and all(resolved_chain[0] in active_uows for resolved_chain in resolved_chains)
    )


def _self_fields_reassigned_before(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    call: ast.Call,
    *,
    fields: set[str],
) -> bool:
    call_position = (call.lineno, call.col_offset)
    for node in _function_scope_nodes(function):
        position = (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))
        if position >= call_position:
            continue
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Store)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and node.attr in fields
        ):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "self"
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in fields
        ):
            return True
    return False


def class_hierarchy(
    class_node: ast.ClassDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> tuple[tuple[Path, ast.ClassDef], ...]:
    return project_class_hierarchy(class_node, path=path, context=context)


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
