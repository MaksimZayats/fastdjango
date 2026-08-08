from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from specx.testing.architecture.context import (
    ArchitectureContext,
    active_uow_names_from_manager_fields,
    attribute_chain,
    module_scope_class_nodes,
    project_class_hierarchy,
    project_class_qualified_names,
    qualified_class_name,
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


def resolved_ambient_call_name(
    call: ast.Call,
    *,
    path: Path,
    context: ArchitectureContext,
    function: ast.AsyncFunctionDef | ast.FunctionDef,
) -> str:
    names = resolved_call_names(call, path=path, context=context) | _parameter_default_call_names(
        call,
        function=function,
        path=path,
        context=context,
    )
    ambient = frozenset(
        name for name in names if name in AMBIENT_EXACT_CALLS or name.startswith(AMBIENT_PREFIXES)
    )
    selected = ambient or names
    return (
        next(iter(selected)) if len(selected) == 1 else f"<ambiguous:{','.join(sorted(selected))}>"
    )


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
    if function is not None:
        names |= _parameter_default_call_names(
            call,
            function=function,
            path=path,
            context=context,
        )
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
        isinstance(call.func, ast.Attribute)
        and call.func.attr in FILESYSTEM_METHODS
        and (
            any(candidate.startswith("pathlib.") for candidate in names)
            or _path_expression_matches_roots(call.func.value, path_roots)
        )
    )


def _parameter_default_call_names(
    call: ast.Call,
    *,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    path: Path,
    context: ArchitectureContext,
) -> frozenset[str]:
    chain = attribute_chain(call.func)
    if not chain:
        return frozenset()
    reaching_names = context.qualified_names(path, call.func)
    local_parameter_name = ".".join(("<local>", *chain))
    if local_parameter_name not in reaching_names:
        return frozenset()
    positional = (*function.args.posonlyargs, *function.args.args)
    defaulted_positionals = (
        positional[-len(function.args.defaults) :] if function.args.defaults else ()
    )
    defaults: dict[str, ast.expr] = {
        argument.arg: default
        for argument, default in zip(
            defaulted_positionals,
            function.args.defaults,
            strict=True,
        )
    }
    defaults.update(
        {
            argument.arg: default
            for argument, default in zip(
                function.args.kwonlyargs,
                function.args.kw_defaults,
                strict=True,
            )
            if default is not None
        }
    )
    default = defaults.get(chain[0])
    if default is None:
        return frozenset()
    return frozenset(
        ".".join((qualified, *chain[1:])) for qualified in context.qualified_names(path, default)
    )


def _path_expression_matches_roots(
    expression: ast.expr,
    roots: set[tuple[str, ...]],
) -> bool:
    chain = attribute_chain(expression)
    if chain and any(_path_receiver_matches_root(chain, root) for root in roots):
        return True
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Div):
        return _path_expression_matches_roots(expression.left, roots)
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Attribute)
        and expression.func.attr in PATH_PRESERVING_MEMBERS
    ):
        return _path_expression_matches_roots(expression.func.value, roots)
    return False


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


def reachable_behavior_functions(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> tuple[tuple[Path, ast.AsyncFunctionDef | ast.FunctionDef], ...]:
    """Return the root behavior and statically called project-local helpers."""

    project_functions = _project_function_definitions(context)
    queued: list[tuple[Path, ast.AsyncFunctionDef | ast.FunctionDef]] = [(path, function)]
    reachable: list[tuple[Path, ast.AsyncFunctionDef | ast.FunctionDef]] = []
    seen: set[tuple[Path, int]] = set()
    while queued:
        function_path, candidate = queued.pop(0)
        key = (function_path, id(candidate))
        if key in seen:
            continue
        seen.add(key)
        reachable.append((function_path, candidate))
        nested = {
            nested_function.name: nested_function
            for nested_function in _direct_nested_functions(candidate)
        }
        for call in (
            node for node in function_behavior_nodes(candidate) if isinstance(node, ast.Call)
        ):
            resolved = context.qualified_names(
                function_path,
                call.func,
            ) | _parameter_default_call_names(
                call,
                function=candidate,
                path=function_path,
                context=context,
            )
            for qualified in resolved:
                for helper_path, helper in project_functions.get(qualified, ()):
                    queued.append((helper_path, helper))
                if qualified.startswith("<local>."):
                    nested_helper = nested.get(qualified.removeprefix("<local>."))
                    if nested_helper is not None:
                        queued.append((function_path, nested_helper))
            if (
                isinstance(call.func, ast.Name)
                and (named_helper := nested.get(call.func.id)) is not None
            ):
                queued.append((function_path, named_helper))
    return tuple(reachable)


def _direct_nested_functions(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
) -> tuple[ast.AsyncFunctionDef | ast.FunctionDef, ...]:
    nested: list[ast.AsyncFunctionDef | ast.FunctionDef] = []

    def visit(node: ast.AST) -> None:
        if node is not function and isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            nested.append(node)
            return
        if node is not function and isinstance(node, (ast.ClassDef, ast.Lambda)):
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(function)
    return tuple(nested)


MethodBinding = Literal["instance", "class", "static"]
DescriptorComponent = Literal["getter", "setter", "deleter"]
DescriptorBinding = Literal["fresh", "local", "inherited"]
DESCRIPTOR_COMPONENTS: frozenset[DescriptorComponent] = frozenset({"getter", "setter", "deleter"})


@dataclass(frozen=True, slots=True)
class ClassMethodDeclaration:
    path: Path
    function: ast.FunctionDef | ast.AsyncFunctionDef
    binding: MethodBinding
    descriptor_component: DescriptorComponent | None = None


@dataclass(frozen=True, slots=True)
class ClassMethodGroup:
    declarations: tuple[ClassMethodDeclaration, ...]
    always_bound: bool
    shadows_inherited_name: bool
    overridden_descriptor_components: frozenset[DescriptorComponent]


def class_method_declarations(
    class_node: ast.ClassDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> dict[str, ClassMethodGroup]:
    """Return runtime-effective method groups, including exact function assignments."""

    project_functions = _project_function_definitions(context)
    return _class_block_method_groups(
        class_node.body,
        {},
        path=path,
        context=context,
        project_functions=project_functions,
    )


def effective_class_method_declarations(
    class_node: ast.ClassDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> tuple[tuple[str, ClassMethodDeclaration], ...]:
    """Return C3-effective method and property-accessor declaration candidates."""

    effective: list[tuple[str, ClassMethodDeclaration]] = []
    shadowed_names: set[str] = set()
    shadowed_components: dict[str, set[DescriptorComponent]] = {}
    for owner_path, owner in class_hierarchy(class_node, path=path, context=context):
        for method_name, group in class_method_declarations(
            owner,
            path=owner_path,
            context=context,
        ).items():
            if method_name in shadowed_names:
                continue
            components = shadowed_components.setdefault(method_name, set())
            effective.extend(
                (method_name, declaration)
                for declaration in group.declarations
                if declaration.descriptor_component is None
                or declaration.descriptor_component not in components
            )
            if group.shadows_inherited_name:
                shadowed_names.add(method_name)
                continue
            components.update(group.overridden_descriptor_components)
    return tuple(effective)


def _class_block_method_groups(
    statements: list[ast.stmt],
    state: dict[str, ClassMethodGroup],
    *,
    path: Path,
    context: ArchitectureContext,
    project_functions: dict[
        str,
        tuple[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef], ...],
    ],
) -> dict[str, ClassMethodGroup]:
    current = dict(state)
    for statement in statements:
        current = _class_statement_method_groups(
            statement,
            current,
            path=path,
            context=context,
            project_functions=project_functions,
        )
    return current


def _class_statement_method_groups(
    statement: ast.stmt,
    state: dict[str, ClassMethodGroup],
    *,
    path: Path,
    context: ArchitectureContext,
    project_functions: dict[
        str,
        tuple[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef], ...],
    ],
) -> dict[str, ClassMethodGroup]:
    current = dict(state)
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
        descriptor_component, descriptor_binding, descriptor_owners = (
            _function_descriptor_component(
                statement,
                path=path,
                context=context,
            )
        )
        declaration = ClassMethodDeclaration(
            path=path,
            function=statement,
            binding=_function_binding(statement, path=path, context=context),
            descriptor_component=descriptor_component,
        )
        existing = current.get(statement.name)
        existing_declarations = existing.declarations if existing is not None else ()
        if descriptor_component is not None:
            selected_descriptor_found, selected_declarations = (
                _selected_descriptor_declarations(
                    descriptor_owners,
                    method_name=statement.name,
                    replaced_component=descriptor_component,
                    current_class=None,
                    context=context,
                )
                if descriptor_binding == "inherited"
                else (False, ())
            )
            descriptor_declarations = (
                tuple(
                    candidate
                    for candidate in (*existing_declarations, *selected_declarations)
                    if candidate.descriptor_component is not None
                    and candidate.descriptor_component != descriptor_component
                )
                if descriptor_binding != "fresh"
                else ()
            )
            declarations = (*descriptor_declarations, declaration)
            shadows_inherited_name = bool(
                descriptor_binding == "fresh"
                or selected_descriptor_found
                or (existing is not None and existing.shadows_inherited_name)
            )
            overridden_components: set[DescriptorComponent] = set(
                existing.overridden_descriptor_components if existing else ()
            )
            overridden_components.add(descriptor_component)
            overridden_descriptor_components = (
                DESCRIPTOR_COMPONENTS
                if shadows_inherited_name
                else frozenset(overridden_components)
            )
        elif _function_is_overload(statement, path=path, context=context) or (
            existing_declarations
            and all(
                _function_is_overload(
                    candidate.function,
                    path=candidate.path,
                    context=context,
                )
                for candidate in existing_declarations
            )
        ):
            declarations = (*existing_declarations, declaration)
            shadows_inherited_name = True
            overridden_descriptor_components = frozenset(DESCRIPTOR_COMPONENTS)
        else:
            declarations = (declaration,)
            shadows_inherited_name = True
            overridden_descriptor_components = frozenset(DESCRIPTOR_COMPONENTS)
        current[statement.name] = ClassMethodGroup(
            declarations=declarations,
            always_bound=True,
            shadows_inherited_name=shadows_inherited_name,
            overridden_descriptor_components=overridden_descriptor_components,
        )
        return current
    targets: tuple[ast.expr, ...] = ()
    value: ast.expr | None = None
    if isinstance(statement, ast.Assign):
        targets, value = tuple(statement.targets), statement.value
    elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
        targets, value = (statement.target,), statement.value
    if targets:
        property_declarations = _property_constructor_declarations(
            value,
            path=path,
            context=context,
            project_functions=project_functions,
        )
        binding, attached_expression = _attached_method_expression(
            value,
            path=path,
            context=context,
        )
        attached_declarations: tuple[ClassMethodDeclaration, ...]
        if isinstance(value, ast.Call) and isinstance(attached_expression, ast.Lambda):
            attached_declarations = (
                ClassMethodDeclaration(
                    path=path,
                    function=_lambda_as_function(
                        attached_expression,
                        name="<attached-lambda>",
                    ),
                    binding=binding,
                ),
            )
        else:
            qualified = context.qualified_name(path, attached_expression)
            attached_declarations = tuple(
                ClassMethodDeclaration(
                    path=function_path,
                    function=function,
                    binding=binding,
                )
                for function_path, function in project_functions.get(qualified, ())
            )
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            target_declarations = property_declarations
            if target_declarations is None:
                target_declarations = attached_declarations
            current[target.id] = ClassMethodGroup(
                declarations=target_declarations,
                always_bound=True,
                shadows_inherited_name=True,
                overridden_descriptor_components=frozenset(DESCRIPTOR_COMPONENTS),
            )
        return current
    if isinstance(statement, ast.If):
        truth = _class_condition_truth(statement.test, path=path, context=context)
        if truth is not None:
            branch = statement.body if truth else statement.orelse
            return _class_block_method_groups(
                branch,
                current,
                path=path,
                context=context,
                project_functions=project_functions,
            )
        return _merge_class_method_states(
            (
                _class_block_method_groups(
                    statement.body,
                    current,
                    path=path,
                    context=context,
                    project_functions=project_functions,
                ),
                _class_block_method_groups(
                    statement.orelse,
                    current,
                    path=path,
                    context=context,
                    project_functions=project_functions,
                ),
            )
        )
    if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
        if (
            isinstance(statement, ast.While)
            and _class_condition_truth(
                statement.test,
                path=path,
                context=context,
            )
            is False
        ):
            return _class_block_method_groups(
                statement.orelse,
                current,
                path=path,
                context=context,
                project_functions=project_functions,
            )
        return _merge_class_method_states(
            (
                current,
                _class_block_method_groups(
                    statement.body,
                    current,
                    path=path,
                    context=context,
                    project_functions=project_functions,
                ),
                _class_block_method_groups(
                    statement.orelse,
                    current,
                    path=path,
                    context=context,
                    project_functions=project_functions,
                ),
            )
        )
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return _class_block_method_groups(
            statement.body,
            current,
            path=path,
            context=context,
            project_functions=project_functions,
        )
    if isinstance(statement, ast.Try):
        body = _class_block_method_groups(
            statement.body,
            current,
            path=path,
            context=context,
            project_functions=project_functions,
        )
        body = _class_block_method_groups(
            statement.orelse,
            body,
            path=path,
            context=context,
            project_functions=project_functions,
        )
        merged = _merge_class_method_states(
            (
                body,
                *(
                    _class_block_method_groups(
                        handler.body,
                        current,
                        path=path,
                        context=context,
                        project_functions=project_functions,
                    )
                    for handler in statement.handlers
                ),
            )
        )
        return _class_block_method_groups(
            statement.finalbody,
            merged,
            path=path,
            context=context,
            project_functions=project_functions,
        )
    if isinstance(statement, ast.Match):
        has_catch_all = any(
            case.guard is None
            and isinstance(case.pattern, ast.MatchAs)
            and case.pattern.pattern is None
            and case.pattern.name is None
            for case in statement.cases
        )
        fallback = () if has_catch_all else (current,)
        return _merge_class_method_states(
            tuple(
                _class_block_method_groups(
                    case.body,
                    current,
                    path=path,
                    context=context,
                    project_functions=project_functions,
                )
                for case in statement.cases
            )
            + fallback
            or (current,)
        )
    return current


def _merge_class_method_states(
    states: tuple[dict[str, ClassMethodGroup], ...],
) -> dict[str, ClassMethodGroup]:
    names: set[str] = set()
    for state in states:
        names.update(state)
    merged: dict[str, ClassMethodGroup] = {}
    for name in names:
        declarations: list[ClassMethodDeclaration] = []
        seen: set[tuple[Path, int, MethodBinding]] = set()
        overridden_components = set(DESCRIPTOR_COMPONENTS)
        for state in states:
            group = state.get(name)
            if group is None or not group.always_bound:
                overridden_components.clear()
            else:
                overridden_components.intersection_update(group.overridden_descriptor_components)
            if group is None:
                continue
            for declaration in group.declarations:
                key = (declaration.path, id(declaration.function), declaration.binding)
                if key not in seen:
                    seen.add(key)
                    declarations.append(declaration)
        merged[name] = ClassMethodGroup(
            declarations=tuple(declarations),
            always_bound=all(
                (group := state.get(name)) is not None and group.always_bound for state in states
            ),
            shadows_inherited_name=all(
                (group := state.get(name)) is not None
                and group.always_bound
                and group.shadows_inherited_name
                for state in states
            ),
            overridden_descriptor_components=frozenset(overridden_components),
        )
    return merged


def _class_condition_truth(
    expression: ast.expr,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool | None:
    if isinstance(expression, ast.Constant):
        return bool(expression.value)
    if context.qualified_names(path, expression) == frozenset({"typing.TYPE_CHECKING"}):
        return False
    return None


def _attached_method_expression(
    value: ast.expr | None,
    *,
    path: Path,
    context: ArchitectureContext,
) -> tuple[MethodBinding, ast.expr | None]:
    if isinstance(value, ast.Call) and len(value.args) == 1 and not value.keywords:
        wrappers = context.qualified_names(path, value.func)
        if wrappers in {
            frozenset({"builtins.staticmethod"}),
            frozenset({"staticmethod"}),
        }:
            return "static", value.args[0]
        if wrappers in {
            frozenset({"builtins.classmethod"}),
            frozenset({"classmethod"}),
        }:
            return "class", value.args[0]
    return "instance", value


def _property_constructor_declarations(
    value: ast.expr | None,
    *,
    path: Path,
    context: ArchitectureContext,
    project_functions: dict[
        str,
        tuple[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef], ...],
    ],
) -> tuple[ClassMethodDeclaration, ...] | None:
    if not isinstance(value, ast.Call) or context.qualified_names(path, value.func) not in {
        frozenset({"builtins.property"}),
        frozenset({"property"}),
    }:
        return None
    accessors: dict[DescriptorComponent, ast.expr] = {}
    positional_components: tuple[DescriptorComponent, ...] = (
        "getter",
        "setter",
        "deleter",
    )
    for component, expression in zip(
        positional_components,
        value.args[:3],
        strict=False,
    ):
        accessors[component] = expression
    keyword_components: dict[str, DescriptorComponent] = {
        "fget": "getter",
        "fset": "setter",
        "fdel": "deleter",
    }
    for keyword in value.keywords:
        if keyword.arg in keyword_components:
            accessors[keyword_components[keyword.arg]] = keyword.value
    declarations: list[ClassMethodDeclaration] = []
    for component, expression in accessors.items():
        if isinstance(expression, ast.Lambda):
            declarations.append(
                ClassMethodDeclaration(
                    path=path,
                    function=_lambda_as_function(
                        expression,
                        name=f"<property-{component}>",
                    ),
                    binding="instance",
                    descriptor_component=component,
                )
            )
            continue
        qualified = context.qualified_name(path, expression)
        declarations.extend(
            ClassMethodDeclaration(
                path=function_path,
                function=function,
                binding="instance",
                descriptor_component=component,
            )
            for function_path, function in project_functions.get(qualified, ())
        )
    return tuple(declarations)


def _lambda_as_function(
    expression: ast.Lambda,
    *,
    name: str,
) -> ast.FunctionDef:
    returned = ast.copy_location(ast.Return(value=expression.body), expression.body)
    function = ast.FunctionDef(
        name=name,
        args=expression.args,
        body=[returned],
        decorator_list=[],
    )
    return ast.fix_missing_locations(ast.copy_location(function, expression))


def _function_binding(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> MethodBinding:
    decorators = {
        qualified
        for decorator in function.decorator_list
        for qualified in context.qualified_names(
            path,
            decorator.func if isinstance(decorator, ast.Call) else decorator,
        )
    }
    if decorators & {"builtins.staticmethod", "staticmethod"}:
        return "static"
    if decorators & {"builtins.classmethod", "classmethod"}:
        return "class"
    return "instance"


def _function_descriptor_component(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> tuple[
    DescriptorComponent | None,
    DescriptorBinding | None,
    frozenset[str],
]:
    for decorator in function.decorator_list:
        expression = decorator.func if isinstance(decorator, ast.Call) else decorator
        if context.qualified_names(path, expression) & {
            "abc.abstractproperty",
            "builtins.property",
            "property",
        }:
            return "getter", "fresh", frozenset()
        chain = attribute_chain(expression)
        if len(chain) >= 2 and chain[-2] == function.name and chain[-1] in DESCRIPTOR_COMPONENTS:
            descriptor_owners: frozenset[str] = (
                context.qualified_names(path, expression.value.value)
                if len(chain) >= 3
                and isinstance(expression, ast.Attribute)
                and isinstance(expression.value, ast.Attribute)
                else frozenset()
            )
            return (
                chain[-1],
                "local" if len(chain) == 2 else "inherited",
                descriptor_owners,
            )
    return None, None, frozenset()


def _selected_descriptor_declarations(
    qualified_owners: frozenset[str],
    *,
    method_name: str,
    replaced_component: DescriptorComponent,
    current_class: ast.ClassDef | None,
    context: ArchitectureContext,
) -> tuple[bool, tuple[ClassMethodDeclaration, ...]]:
    selected: list[ClassMethodDeclaration] = []
    selected_descriptor_found = False
    seen: set[tuple[Path, int, MethodBinding, DescriptorComponent | None]] = set()
    for owner_path in context.source_paths():
        for owner in module_scope_class_nodes(context.tree(owner_path)):
            if (
                owner is current_class
                or qualified_class_name(
                    owner,
                    source_path=owner_path,
                    context=context,
                )
                not in qualified_owners
            ):
                continue
            for candidate_name, declaration in effective_class_method_declarations(
                owner,
                path=owner_path,
                context=context,
            ):
                if candidate_name == method_name and declaration.descriptor_component is not None:
                    selected_descriptor_found = True
                if (
                    candidate_name != method_name
                    or declaration.descriptor_component is None
                    or declaration.descriptor_component == replaced_component
                ):
                    continue
                key = (
                    declaration.path,
                    id(declaration.function),
                    declaration.binding,
                    declaration.descriptor_component,
                )
                if key not in seen:
                    seen.add(key)
                    selected.append(declaration)
    return selected_descriptor_found, tuple(selected)


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
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:
            parsed = ast.parse(annotation.value, mode="eval").body
        except SyntaxError:
            return False
        return _annotation_is_callable(
            parsed,
            path=path,
            context=context,
            visited=visited,
        )
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return any(
            _annotation_is_callable(
                member,
                path=path,
                context=context,
                visited=visited,
            )
            for member in (annotation.left, annotation.right)
        )
    root = annotation.value if isinstance(annotation, ast.Subscript) else annotation
    qualified = context.qualified_name(path, root)
    if qualified in {"collections.abc.Callable", "typing.Callable"}:
        return True
    if isinstance(annotation, ast.Subscript) and qualified in {
        "typing.Annotated",
        "typing_extensions.Annotated",
    }:
        annotated_type = (
            annotation.slice.elts[0]
            if isinstance(annotation.slice, ast.Tuple) and annotation.slice.elts
            else annotation.slice
        )
        return _annotation_is_callable(
            annotated_type,
            path=path,
            context=context,
            visited=visited,
        )
    if isinstance(annotation, ast.Subscript) and qualified in {
        "typing.Optional",
        "typing.Union",
    }:
        members = (
            annotation.slice.elts
            if isinstance(annotation.slice, ast.Tuple)
            else (annotation.slice,)
        )
        return any(
            _annotation_is_callable(
                member,
                path=path,
                context=context,
                visited=visited,
            )
            for member in members
        )
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
    effective_bindings: dict[str, tuple[Path, ast.expr | None]] = {}
    for node_path, node in hierarchy:
        for field, annotation in _class_direct_field_bindings(node).items():
            effective_bindings.setdefault(field, (node_path, annotation))
    injected_payloads = {
        field: payload
        for field, (node_path, annotation) in effective_bindings.items()
        if annotation is not None
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


def _class_direct_field_bindings(class_node: ast.ClassDef) -> dict[str, ast.expr | None]:
    annotations: dict[str, ast.expr] = {}
    runtime_bound: set[str] = set()
    for statement in reversed(class_node.body):
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            runtime_bound.add(statement.name)
            continue
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    runtime_bound.add(target.id)
            continue
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            annotations.setdefault(statement.target.id, statement.annotation)
            if statement.value is not None:
                runtime_bound.add(statement.target.id)
    return {
        field: None if field in runtime_bound else annotations.get(field)
        for field in runtime_bound | annotations.keys()
    }


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
