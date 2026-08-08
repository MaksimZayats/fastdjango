from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from specx._internal.python_ast.scanner import PythonAstProject
from specx.testing.architecture.models import SpecxArchitectureConfig

INNER_PACKAGE_NAMES = {
    "capabilities",
    "dtos",
    "entities",
    "exceptions",
    "gateways",
    "repositories",
    "services",
    "use_cases",
}
BASE_SUFFIXES = (
    "ApplicationValueError",
    "ApplicationError",
    "DeliveryService",
    "FastAPISchema",
    "RuntimeSettings",
    "SQLAlchemyModel",
    "Lifecycle",
    "Configurator",
    "UnitOfWorkManager",
    "Capability",
    "Command",
    "Controller",
    "Gateway",
    "Repository",
    "UnitOfWork",
    "UseCase",
    "Entity",
    "Factory",
    "Model",
    "Schema",
    "Service",
    "Settings",
    "ValueError",
    "Enum",
    "Error",
    "DTO",
    "Query",
)
BASE_SUFFIX_OVERRIDES = {
    "ApplicationError": "Error",
    "ApplicationValueError": "ValueError",
    "DeliveryService": "Service",
    "FastAPISchema": "Schema",
    "PureService": "Service",
    "ReadService": "Service",
    "EffectService": "Service",
    "RuntimeSettings": "Settings",
    "SQLAlchemyModel": "Model",
    "StrEnum": "Enum",
}
USE_CASE_INPUT_BASE_NAMES = {"BaseCommand", "BaseQuery"}
USE_CASE_INPUT_ARGUMENTS = {"command", "query"}
CORE_SERVICE_BASE_NAMES = {"BasePureService", "BaseReadService", "BaseEffectService"}
CAPABILITY_FORBIDDEN_NAME_SUFFIXES = (
    "Dependency",
    "Gateway",
    "Helper",
    "Manager",
    "Repository",
    "Service",
    "Util",
    "Utils",
    "UseCase",
)
GATEWAY_EFFECT_DECLARATION_MARKERS = ("External effect:", "External effects:")
PURE_SERVICE_FORBIDDEN_DEPENDENCY_FRAGMENTS = (
    "UnitOfWorkManager",
    "UnitOfWork",
    "Repository",
    "Gateway",
    "Client",
    "Settings",
    "Clock",
    "UUID",
    "Random",
)
PURE_SERVICE_FORBIDDEN_IMPORT_ROOTS = {
    "fastapi",
    "httpx",
    "httpx2",
    "openai",
    "random",
    "redis",
    "requests",
    "sqlalchemy",
    "time",
    "uuid",
}
PURE_SERVICE_FORBIDDEN_IMPORT_PARTS = {
    "delivery",
    "infrastructure",
    "ioc",
    "repositories",
    "settings",
}
READ_SERVICE_FORBIDDEN_CALL_NAMES = {
    "charge",
    "charge_money",
    "commit",
    "publish",
    "publish_event",
    "rollback",
    "send_email",
    "send_message",
}
READ_SERVICE_FORBIDDEN_CALL_PREFIXES = ("charge_", "publish_", "send_")
EFFECT_SERVICE_FORBIDDEN_IMPORT_ROOTS = {"fastapi", "starlette"}
EFFECT_SERVICE_FORBIDDEN_IMPORT_PARTS = {"delivery"}
READ_REPOSITORY_METHOD_NAMES = {"count", "exists", "find", "get", "list", "search"}
READ_REPOSITORY_METHOD_PREFIXES = (
    "count_by_",
    "exists_by_",
    "find_by_",
    "find_for_",
    "get_by_",
    "get_for_",
    "list_by_",
    "list_for_",
    "search_by_",
)
SCHEMA_BOOTSTRAP_METHOD_NAMES = {"create_all", "drop_all"}
MAKE_COMMAND_PATTERN = re.compile(r"(?<![a-zA-Z0-9_-])make\s+([a-zA-Z0-9_.-]+)\b")
MAKE_TARGET_PATTERN = re.compile(
    r"^([a-zA-Z0-9_.-]+(?:[ \t]+[a-zA-Z0-9_.-]+)*):(?:\s|$)",
    re.MULTILINE,
)


@dataclass(frozen=True, kw_only=True, slots=True)
class ArchitectureContext:
    """Shared static project model used by all specx architecture rules."""

    config: SpecxArchitectureConfig
    ast_project: PythonAstProject

    @property
    def project_root(self) -> Path:
        return self.config.project_root

    @property
    def src_root(self) -> Path:
        return self.project_root / "src" / self.config.package_name

    def source_paths(self) -> tuple[Path, ...]:
        return tuple(
            path
            for path in sorted(self.ast_project.files)
            if path.is_relative_to(self.src_root) and path.name != "__init__.py"
        )

    def core_paths(self) -> tuple[Path, ...]:
        core_root = self.src_root / "core"
        return tuple(
            path
            for path in sorted(self.ast_project.files)
            if path.is_relative_to(core_root)
            and path.name != "__init__.py"
            and len(path.relative_to(core_root).parts) >= 3
        )

    def core_service_paths(self) -> tuple[Path, ...]:
        return tuple(
            path
            for path in self.source_paths()
            if _path_has_parts(path.relative_to(self.src_root), ("core", "*", "services"))
        )

    def tree(self, path: Path) -> ast.Module:
        return self.ast_project.source_file(path).tree

    def imports(self, path: Path) -> frozenset[str]:
        return self.ast_project.source_file(path).imports

    def aliases(self, path: Path) -> dict[str, str]:
        return self.ast_project.source_file(path).aliases

    def makefile_targets(self) -> set[str]:
        path = self.project_root / "Makefile"
        if not path.exists():
            return set()
        text = path.read_text(encoding="utf-8")
        return {
            target
            for match in MAKE_TARGET_PATTERN.finditer(text)
            for target in match.group(1).split()
            if not target.startswith(".")
        }

    def makefile_target_recipes(self) -> dict[str, str]:
        """Return each public Make target and its recipe/body text."""

        path = self.project_root / "Makefile"
        if not path.exists():
            return {}
        recipes: dict[str, list[str]] = {}
        current_targets: tuple[str, ...] = ()
        for line in path.read_text(encoding="utf-8").splitlines():
            match = MAKE_TARGET_PATTERN.match(line)
            if match is not None:
                current_targets = tuple(
                    target
                    for target in line.split(":", maxsplit=1)[0].split()
                    if not target.startswith(".")
                )
                for target in current_targets:
                    recipes.setdefault(target, [])
                continue
            for target in current_targets:
                recipes[target].append(line)
        return {target: "\n".join(lines).rstrip() for target, lines in recipes.items()}

    def qualified_name(self, path: Path, expression: ast.expr | None) -> str:
        """Resolve an imported alias or lexically local symbol to a qualified name."""

        chain = attribute_chain(expression)
        if not chain:
            return ast.unparse(expression) if expression is not None else ""
        bindings = qualified_symbol_bindings(self, path, at_node=expression)
        raw = ".".join((bindings.get(chain[0], chain[0]), *chain[1:]))
        canonical = self._canonical_reexport_names(frozenset({raw}))
        return next(iter(canonical)) if len(canonical) == 1 else raw

    def qualified_names(self, path: Path, expression: ast.expr | None) -> frozenset[str]:
        """Resolve every conservatively reachable qualified name for an expression."""

        chain = attribute_chain(expression)
        if not chain:
            return frozenset({ast.unparse(expression) if expression is not None else ""})
        bindings = qualified_symbol_binding_choices(self, path, at_node=expression)
        roots = bindings.get(chain[0], frozenset({chain[0]}))
        return self._canonical_reexport_names(
            frozenset(".".join((root, *chain[1:])) for root in roots)
        )

    def _canonical_reexport_names(self, names: frozenset[str]) -> frozenset[str]:
        current = names
        for _iteration in range(10):
            replacements: dict[str, str] = {}
            for init_path in (
                path
                for path in self.ast_project.files
                if path.name == "__init__.py" and path.is_relative_to(self.src_root)
            ):
                relative_parent = init_path.relative_to(self.src_root).parent
                package_module = ".".join(
                    (self.config.package_name, *relative_parent.parts)
                ).rstrip(".")
                module_name = f"{package_module}.__init__"
                for statement in self.tree(init_path).body:
                    if not isinstance(statement, ast.ImportFrom):
                        continue
                    imported_module = _imported_module_name(
                        statement,
                        module_name=module_name,
                    )
                    for alias in statement.names:
                        if alias.name == "*":
                            continue
                        exported = f"{package_module}.{alias.asname or alias.name}"
                        replacements[exported] = f"{imported_module}.{alias.name}"
            updated = frozenset(
                next(
                    (
                        f"{target}{name.removeprefix(exported)}"
                        for exported, target in replacements.items()
                        if name == exported or name.startswith(f"{exported}.")
                    ),
                    name,
                )
                for name in current
            )
            if updated == current:
                return current
            current = updated
        return current


def documented_make_targets(text: str) -> set[str]:
    return set(MAKE_COMMAND_PATTERN.findall(text))


def module_parts(module: str) -> tuple[str, ...]:
    return tuple(part for part in module.split(".") if part)


def base_name(base: ast.expr, aliases: dict[str, str] | None = None) -> str:
    aliases = aliases or {}
    if isinstance(base, ast.Name):
        return aliases.get(base.id, base.id)
    if isinstance(base, ast.Attribute):
        return base.attr
    if isinstance(base, ast.Subscript):
        return base_name(base.value, aliases)
    return ast.unparse(base)


def annotation_name(annotation: ast.expr | None, aliases: dict[str, str] | None = None) -> str:
    aliases = aliases or {}
    if annotation is None:
        return ""
    if isinstance(annotation, ast.Name):
        return aliases.get(annotation.id, annotation.id)
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    if isinstance(annotation, ast.Subscript):
        value_name = annotation_name(annotation.value, aliases)
        slice_name = annotation_name(annotation.slice, aliases)
        return f"{value_name}[{slice_name}]"
    if isinstance(annotation, ast.Tuple):
        return ", ".join(annotation_name(element, aliases) for element in annotation.elts)
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return (
            f"{annotation_name(annotation.left, aliases)} | "
            f"{annotation_name(annotation.right, aliases)}"
        )
    return ast.unparse(annotation)


def class_suffix_from_base(base: str) -> str | None:
    normalized_base_name = base.removeprefix("Base")
    if normalized_base_name in BASE_SUFFIX_OVERRIDES:
        return BASE_SUFFIX_OVERRIDES[normalized_base_name]
    return next(
        (suffix for suffix in BASE_SUFFIXES if normalized_base_name.endswith(suffix)),
        None,
    )


def capability_family_suffix_from_base(
    base: str,
    class_base_name_index: dict[str, set[str]],
) -> str | None:
    if base == "BaseCapability":
        return "Capability"
    if "BaseCapability" in foundation_base_names_for_class(base, class_base_name_index):
        return base.removeprefix("Base")
    return None


def category_suffix_from_base(
    base: str,
    class_base_name_index: dict[str, set[str]],
) -> str | None:
    capability_suffix = capability_family_suffix_from_base(base, class_base_name_index)
    if capability_suffix is not None:
        return capability_suffix
    return class_suffix_from_base(base)


def has_scoped_example_docstring(node: ast.ClassDef) -> bool:
    docstring = ast.get_docstring(node)
    if docstring is None or "Example:" not in docstring:
        return False
    scope, _separator, example = docstring.partition("Example:")
    if any(line.strip() in {"...", "pass"} for line in example.splitlines()):
        return False
    example_lines = [line.strip() for line in example.splitlines() if line.strip()]
    return scope.strip() != "" and example_lines != []


def declares_external_effect(node: ast.ClassDef) -> bool:
    docstring = ast.get_docstring(node)
    return docstring is not None and any(
        marker in docstring for marker in GATEWAY_EFFECT_DECLARATION_MARKERS
    )


def uses_diwire_container(tree: ast.Module) -> bool:
    diwire_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "diwire":
                    diwire_aliases.add(alias.asname or alias.name)
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module == "diwire"
            and any(alias.name == "Container" for alias in node.names)
        ):
            return True
    return any(
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in diwire_aliases
        and node.attr == "Container"
        for node in ast.walk(tree)
    )


def field_aliases_for_self_fields(
    class_node: ast.ClassDef,
    aliases: dict[str, str],
) -> dict[str, str]:
    fields: dict[str, str] = {}
    for child in class_node.body:
        if not isinstance(child, ast.AnnAssign) or not isinstance(child.target, ast.Name):
            continue
        fields[child.target.id] = annotation_name(child.annotation, aliases)
    return fields


def context_self_fields(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    field_names: set[str],
) -> set[str]:
    opened_fields: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, (ast.AsyncWith, ast.With)):
            continue
        for item in node.items:
            root_name = self_attribute_root_name(item.context_expr)
            if root_name in field_names:
                opened_fields.add(root_name)
    return opened_fields


def context_self_field_count(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    field_names: set[str],
) -> int:
    count = 0
    for node in ast.walk(function):
        if not isinstance(node, (ast.AsyncWith, ast.With)):
            continue
        for item in node.items:
            if self_attribute_root_name(item.context_expr) in field_names:
                count += 1
    return count


def uow_manager_context_fields(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    manager_fields: set[str],
) -> set[str]:
    return context_self_fields(function, manager_fields)


def uow_manager_context_count(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    manager_fields: set[str],
) -> int:
    return context_self_field_count(function, manager_fields)


def injected_type_name(annotation: ast.expr | None, aliases: dict[str, str]) -> str:
    if annotation is None:
        return ""
    if (
        isinstance(annotation, ast.Subscript)
        and annotation_name(annotation.value, aliases) == "Injected"
    ):
        return annotation_name(annotation.slice, aliases)
    return ""


def root_name(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        return root_name(expression.value)
    if isinstance(expression, ast.Call):
        return root_name(expression.func)
    if isinstance(expression, ast.Subscript):
        return root_name(expression.value)
    return None


def call_is_rooted_in_names(call: ast.Call, names: set[str]) -> bool:
    return root_name(call.func) in names


def expression_is_rooted_in_names(expression: ast.expr | None, names: set[str]) -> bool:
    return expression is not None and root_name(expression) in names


def self_attribute_root_name(expression: ast.expr | None) -> str | None:
    if isinstance(expression, ast.Call):
        return self_attribute_root_name(expression.func)
    if isinstance(expression, ast.Attribute):
        parent = expression.value
        if isinstance(parent, ast.Name) and parent.id == "self":
            return expression.attr
        return self_attribute_root_name(parent)
    return None


def expression_is_rooted_in_self_attributes(
    expression: ast.expr | None,
    attribute_names: set[str],
) -> bool:
    return self_attribute_root_name(expression) in attribute_names


def call_is_rooted_in_self_attributes(call: ast.Call, attribute_names: set[str]) -> bool:
    return expression_is_rooted_in_self_attributes(call.func, attribute_names)


def call_from_expression(expression: ast.expr | None) -> ast.Call | None:
    if isinstance(expression, ast.Call):
        return expression
    if isinstance(expression, ast.Await) and isinstance(expression.value, ast.Call):
        return expression.value
    return None


def active_uow_names(function: ast.AsyncFunctionDef | ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, (ast.AsyncWith, ast.With)):
            continue
        for item in node.items:
            if item.optional_vars is None:
                continue
            if isinstance(item.optional_vars, ast.Name):
                names.add(item.optional_vars.id)
    return names


def active_uow_names_from_manager_fields(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    manager_fields: set[str],
) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, (ast.AsyncWith, ast.With)):
            continue
        for item in node.items:
            if self_attribute_root_name(item.context_expr) not in manager_fields:
                continue
            if isinstance(item.optional_vars, ast.Name):
                names.add(item.optional_vars.id)
    return names


def unit_of_work_argument_names(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    aliases: dict[str, str],
) -> set[str]:
    names: set[str] = set()
    for argument in [*function.args.args, *function.args.kwonlyargs]:
        if "UnitOfWork" in annotation_name(argument.annotation, aliases):
            names.add(argument.arg)
    return names


def active_repository_names(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    *,
    root_names: set[str] | None = None,
    self_attribute_names: set[str] | None = None,
) -> set[str]:
    roots = root_names or active_uow_names(function)
    self_attributes = self_attribute_names or set()
    names: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign):
            continue
        value_root = root_name(node.value)
        value_self_root = self_attribute_root_name(node.value)
        if value_root not in roots and value_self_root not in self_attributes:
            continue
        if isinstance(node.value, ast.Attribute) and not node.value.attr.endswith("repository"):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def attribute_chain(expression: ast.expr | None) -> tuple[str, ...]:
    if isinstance(expression, ast.Name):
        return (expression.id,)
    if isinstance(expression, ast.Attribute):
        parent_chain = attribute_chain(expression.value)
        if not parent_chain:
            return ()
        return (*parent_chain, expression.attr)
    if isinstance(expression, ast.Call):
        return attribute_chain(expression.func)
    if isinstance(expression, ast.Subscript):
        return attribute_chain(expression.value)
    return ()


def repository_result_variable_names(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    *,
    self_attribute_names: set[str],
) -> set[str]:
    names: set[str] = set()
    repository_roots = active_uow_names(function) | active_repository_names(
        function,
        self_attribute_names=self_attribute_names,
    )
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign):
            continue
        call = call_from_expression(node.value)
        if call is None:
            continue
        if call_is_rooted_in_names(call, repository_roots) or call_is_rooted_in_self_attributes(
            call, self_attribute_names
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def repository_mutator_method_names(context: ArchitectureContext) -> set[str]:
    names: set[str] = set()
    for path in (context.src_root / "core").glob("*/repositories/**/*.py"):
        if path.name == "__init__.py" or path not in context.ast_project.files:
            continue
        tree = context.tree(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                method_name = node.name
                if not is_read_repository_method_name(method_name):
                    names.add(method_name)
    return names


def is_read_repository_method_name(method_name: str) -> bool:
    return method_name in READ_REPOSITORY_METHOD_NAMES or method_name.startswith(
        READ_REPOSITORY_METHOD_PREFIXES
    )


def is_schema_bootstrap_call(call: ast.Call) -> bool:
    return isinstance(call.func, ast.Attribute) and call.func.attr in SCHEMA_BOOTSTRAP_METHOD_NAMES


def class_direct_base_names(node: ast.ClassDef, aliases: dict[str, str]) -> set[str]:
    return {base_name(base, aliases) for base in node.bases}


def class_base_name_index(context: ArchitectureContext) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for path in context.source_paths():
        tree = context.tree(path)
        aliases = context.aliases(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                index[node.name] = class_direct_base_names(node, aliases)
    return index


def class_definition_base_index(
    context: ArchitectureContext,
) -> dict[str, tuple[tuple[Path, set[str]], ...]]:
    mutable_index: dict[str, list[tuple[Path, set[str]]]] = {}
    for path in context.source_paths():
        tree = context.tree(path)
        module_name = _source_module_name(path, context)
        _index_class_definitions(
            tree.body,
            bindings={},
            path=path,
            module_name=module_name,
            mutable_index=mutable_index,
        )
    return {name: tuple(definitions) for name, definitions in mutable_index.items()}


def class_has_foundation_base_at(
    node: ast.ClassDef,
    base: str,
    *,
    source_path: Path,
    context: ArchitectureContext,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
) -> bool:
    """Return whether one path-qualified class inherits a foundation base."""

    return class_has_foundation_base_from_path(
        node.name,
        base,
        source_path=source_path,
        context=context,
        definition_index=definition_index,
    )


def nearest_foundation_base_names_for_class_at(
    node: ast.ClassDef,
    *,
    source_path: Path,
    context: ArchitectureContext,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
) -> set[str]:
    """Return the nearest recognized foundation bases for one exact class."""

    return _nearest_foundation_base_names_from_path(
        node.name,
        source_path=source_path,
        context=context,
        definition_index=definition_index,
        visited=set(),
    )


def category_suffix_from_base_at(
    base: str,
    *,
    source_path: Path,
    context: ArchitectureContext,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
) -> str | None:
    """Return a category suffix using path-qualified capability ancestry."""

    leaf = base.rsplit(".", maxsplit=1)[-1]
    if leaf == "BaseCapability":
        return "Capability"
    if leaf.startswith("Base") and class_has_foundation_base_from_path(
        base,
        "BaseCapability",
        source_path=source_path,
        context=context,
        definition_index=definition_index,
    ):
        return leaf.removeprefix("Base")
    return class_suffix_from_base(leaf)


def _nearest_foundation_base_names_from_path(
    class_name: str,
    *,
    source_path: Path,
    context: ArchitectureContext,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
    visited: set[tuple[Path, str]],
) -> set[str]:
    nearest: set[str] = set()
    for candidate_path, base_names in _class_definition_candidates(
        class_name,
        source_path=source_path,
        context=context,
        definition_index=definition_index,
    ):
        visit_key = (candidate_path, class_name)
        if visit_key in visited:
            continue
        direct = {
            found_base
            for found_base in base_names
            if class_suffix_from_base(found_base.rsplit(".", maxsplit=1)[-1]) is not None
        }
        if direct:
            nearest.update(direct)
            continue
        for found_base in base_names:
            nearest.update(
                _nearest_foundation_base_names_from_path(
                    found_base,
                    source_path=candidate_path,
                    context=context,
                    definition_index=definition_index,
                    visited={*visited, visit_key},
                )
            )
    return nearest


def qualified_class_name(
    node: ast.ClassDef,
    *,
    source_path: Path,
    context: ArchitectureContext,
) -> str:
    """Return the importable qualified name of a project class."""

    return f"{_source_module_name(source_path, context)}.{node.name}"


def project_class_qualified_names(context: ArchitectureContext) -> frozenset[str]:
    """Return every statically declared project class by qualified name."""

    return frozenset(
        qualified_class_name(node, source_path=path, context=context)
        for path in context.source_paths()
        for node in module_scope_class_nodes(context.tree(path))
    )


def module_scope_class_nodes(tree: ast.Module) -> tuple[ast.ClassDef, ...]:
    """Return classes bound in module scope, including control-flow declarations."""

    classes: list[ast.ClassDef] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.ClassDef):
            classes.append(node)
            return
        if node is not tree and isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        ):
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return tuple(classes)


def class_is_statically_abstract_at(
    node: ast.ClassDef,
    *,
    source_path: Path,
    context: ArchitectureContext,
) -> bool:
    """Recognize abstract project classes using path-qualified ancestry."""

    relative_parts = source_path.relative_to(context.src_root).parts
    if (
        "foundation" in relative_parts
        and len(node.name) > 4
        and node.name.startswith("Base")
        and node.name[4].isupper()
    ):
        return True
    if _declares_explicit_abstract_class(
        node,
        source_path=source_path,
        context=context,
    ):
        return True
    return bool(
        _unimplemented_abstract_methods(
            node,
            source_path=source_path,
            context=context,
        )
    )


def class_declares_sqlalchemy_mapping(node: ast.ClassDef) -> bool:
    """Return whether a class declares a concrete SQLAlchemy table mapping."""

    explicitly_abstract = any(
        isinstance(child, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "__abstract__"
            for target in (child.targets if isinstance(child, ast.Assign) else [child.target])
        )
        and isinstance(child.value, ast.Constant)
        and child.value.value is True
        for child in node.body
    )
    if explicitly_abstract:
        return False
    declares_table = any(
        isinstance(child, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id in {"__table__", "__tablename__"}
            for target in (child.targets if isinstance(child, ast.Assign) else [child.target])
        )
        for child in node.body
    )
    declares_mapped_attribute = any(
        isinstance(descendant, ast.Call)
        and attribute_chain(descendant.func)[-1:] in {("mapped_column",), ("Column",)}
        for child in node.body
        if isinstance(child, (ast.Assign, ast.AnnAssign))
        for descendant in ast.walk(child)
    )
    return declares_table or declares_mapped_attribute


def class_has_sqlalchemy_mapping_at(
    node: ast.ClassDef,
    *,
    source_path: Path,
    context: ArchitectureContext,
) -> bool:
    """Return whether a project class or an effective ancestor declares a mapping."""

    return any(
        class_declares_sqlalchemy_mapping(candidate)
        for _candidate_path, candidate in project_class_hierarchy(
            node,
            path=source_path,
            context=context,
        )
    )


def _declares_explicit_abstract_class(
    node: ast.ClassDef,
    *,
    source_path: Path,
    context: ArchitectureContext,
) -> bool:
    protocol_names = {"typing.Protocol", "typing_extensions.Protocol"}
    if any(
        (resolved := context.qualified_names(source_path, base)) and resolved <= protocol_names
        for base in node.bases
    ):
        return True
    return any(
        isinstance(child, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "__abstract__"
            for target in (child.targets if isinstance(child, ast.Assign) else [child.target])
        )
        and isinstance(child.value, ast.Constant)
        and child.value.value is True
        for child in node.body
    )


def _unimplemented_abstract_methods(
    node: ast.ClassDef,
    *,
    source_path: Path,
    context: ArchitectureContext,
) -> set[str]:
    from specx.testing.architecture.rules._call_analysis import (
        effective_class_method_declarations,
    )

    declarations: dict[
        str,
        list[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef, str | None]],
    ] = {}
    for method_name, declaration in effective_class_method_declarations(
        node,
        path=source_path,
        context=context,
    ):
        declarations.setdefault(method_name, []).append(
            (
                declaration.path,
                declaration.function,
                declaration.descriptor_component,
            )
        )
    required: set[str] = set()
    for method_name, candidates in declarations.items():
        ordinary = [candidate for candidate in candidates if candidate[2] is None]
        if ordinary:
            if all(
                _method_is_statically_abstract(function, path=path, context=context)
                for path, function, _component in ordinary
            ):
                required.add(method_name)
            continue
        components = {component for _path, _function, component in candidates}
        if any(
            all(
                _method_is_statically_abstract(function, path=path, context=context)
                for path, function, candidate_component in candidates
                if candidate_component == component
            )
            for component in components
        ):
            required.add(method_name)
    return required


def _method_is_statically_abstract(
    method: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> bool:
    abstract_decorators = {
        "abc.abstractclassmethod",
        "abc.abstractmethod",
        "abc.abstractproperty",
        "abc.abstractstaticmethod",
    }
    return any(
        (resolved := context.qualified_names(path, decorator)) and resolved <= abstract_decorators
        for decorator in method.decorator_list
    )


def project_class_hierarchy(
    class_node: ast.ClassDef,
    *,
    path: Path,
    context: ArchitectureContext,
) -> tuple[tuple[Path, ast.ClassDef], ...]:
    """Return project classes in Python C3 method-resolution order."""

    definitions = {
        qualified_class_name(node, source_path=candidate_path, context=context): (
            candidate_path,
            node,
        )
        for candidate_path in context.source_paths()
        for node in module_scope_class_nodes(context.tree(candidate_path))
    }
    root = qualified_class_name(class_node, source_path=path, context=context)
    # Rules also discover lexically nested classes. They are not importable under this
    # simple name, but their own methods and project ancestors still need enforcement.
    definitions[root] = (path, class_node)
    cache: dict[str, tuple[str, ...]] = {}

    def linearize(qualified: str, visiting: frozenset[str]) -> tuple[str, ...]:
        if qualified in cache:
            return cache[qualified]
        if qualified in visiting or qualified not in definitions:
            return (qualified,)
        node_path, node = definitions[qualified]
        bases = tuple(context.qualified_name(node_path, base) for base in node.bases)
        result = (
            qualified,
            *_merge_c3(
                [list(linearize(base, visiting | {qualified})) for base in bases] + [list(bases)]
            ),
        )
        cache[qualified] = result
        return result

    return tuple(
        definitions[qualified]
        for qualified in linearize(root, frozenset())
        if qualified in definitions
    )


def _merge_c3(sequences: list[list[str]]) -> tuple[str, ...]:
    merged: list[str] = []
    remaining = [sequence for sequence in sequences if sequence]
    while remaining:
        candidate: str | None = None
        for sequence in remaining:
            head = sequence[0]
            if all(head not in other[1:] for other in remaining):
                candidate = head
                break
        if candidate is None:
            # Invalid Python hierarchies fail at runtime. Preserve deterministic analysis
            # instead of making architecture checking itself fail.
            candidate = remaining[0][0]
        merged.append(candidate)
        for sequence in remaining:
            if sequence and sequence[0] == candidate:
                sequence.pop(0)
        remaining = [sequence for sequence in remaining if sequence]
    return tuple(merged)


def class_has_foundation_base_from_path(
    class_name: str,
    base: str,
    *,
    source_path: Path,
    context: ArchitectureContext,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
    visited: set[tuple[Path, str]] | None = None,
) -> bool:
    visited = visited or set()
    candidates = _class_definition_candidates(
        class_name,
        source_path=source_path,
        context=context,
        definition_index=definition_index,
    )
    for candidate_path, base_names in candidates:
        visit_key = (candidate_path, class_name)
        if visit_key in visited:
            continue
        candidate_visited = {*visited, visit_key}
        if any(
            found_base == base or found_base in _FOUNDATION_BASE_QUALIFIED_NAMES.get(base, set())
            for found_base in base_names
        ):
            return True
        if any(
            class_has_foundation_base_from_path(
                found_base,
                base,
                source_path=candidate_path,
                context=context,
                definition_index=definition_index,
                visited=candidate_visited,
            )
            for found_base in base_names
        ):
            return True
    return False


_FOUNDATION_BASE_QUALIFIED_NAMES: dict[str, set[str]] = {
    "BaseCapability": {"specx.core.foundation.capability.BaseCapability"},
    "BaseCommand": {"specx.core.foundation.command.BaseCommand"},
    "BaseController": {"specx.delivery.foundation.controller.BaseController"},
    "BaseDTO": {"specx.core.foundation.dto.BaseDTO"},
    "BaseDeliveryService": {"specx.delivery.foundation.service.BaseDeliveryService"},
    "BaseEffectService": {"specx.core.foundation.effect_service.BaseEffectService"},
    "BaseEntity": {"specx.core.foundation.entity.BaseEntity"},
    "BaseFastAPISchema": {"specx.delivery.foundation.fastapi.schema.BaseFastAPISchema"},
    "BaseGateway": {"specx.core.foundation.gateway.BaseGateway"},
    "BaseLifecycle": {"specx.delivery.foundation.lifecycle.BaseLifecycle"},
    "BasePureService": {"specx.core.foundation.pure_service.BasePureService"},
    "BaseQuery": {"specx.core.foundation.query.BaseQuery"},
    "BaseReadService": {"specx.core.foundation.read_service.BaseReadService"},
    "BaseRepository": {"specx.core.foundation.repository.BaseRepository"},
    "BaseRuntimeSettings": {
        "specx.infrastructure.foundation.settings.BaseRuntimeSettings",
    },
    "BaseSQLAlchemyModel": {
        "specx.infrastructure.foundation.sqlalchemy.model.BaseSQLAlchemyModel",
        "specx.infrastructure.foundation.sqlalchemy_model.BaseSQLAlchemyModel",
    },
    "BaseUnitOfWork": {"specx.core.foundation.unit_of_work.BaseUnitOfWork"},
    "BaseUnitOfWorkManager": {
        "specx.core.foundation.unit_of_work_manager.BaseUnitOfWorkManager",
    },
    "BaseUseCase": {"specx.core.foundation.use_case.BaseUseCase"},
}


def _class_definition_candidates(
    class_name: str,
    *,
    source_path: Path,
    context: ArchitectureContext,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
) -> tuple[tuple[Path, set[str]], ...]:
    unqualified_class_name = class_name.rsplit(".", maxsplit=1)[-1]
    candidates = definition_index.get(unqualified_class_name, ())
    if "." in class_name:
        return tuple(
            candidate
            for candidate in candidates
            if f"{_source_module_name(candidate[0], context)}.{unqualified_class_name}"
            == class_name
        )
    local_candidates = tuple(candidate for candidate in candidates if candidate[0] == source_path)
    if local_candidates:
        return local_candidates
    return candidates if len(candidates) == 1 else ()


def _source_module_name(path: Path, context: ArchitectureContext) -> str:
    relative_module = path.relative_to(context.src_root).with_suffix("")
    return ".".join((context.config.package_name, *relative_module.parts))


def qualified_symbol_bindings(
    context: ArchitectureContext,
    path: Path,
    *,
    at_node: ast.AST | None = None,
) -> dict[str, str]:
    """Return import and lexically local symbol bindings at one AST node."""

    module_name = (
        _source_module_name(path, context) if path.is_relative_to(context.src_root) else ""
    )
    bindings: dict[str, str] = {}
    definition_time = at_node is not None and _is_definition_time_expression(
        context.tree(path), at_node
    )
    target_position = _node_position(at_node) if definition_time and at_node is not None else None
    for node in _lexical_scope_nodes(context.tree(path)):
        node_position = _node_position(node)
        if (
            target_position is not None
            and node_position is not None
            and node_position >= target_position
        ):
            continue
        _update_lexical_binding(
            node,
            bindings,
            module_name=module_name,
            local_scope=False,
        )
    if at_node is not None and not definition_time:
        for scope in _containing_lexical_scopes(context.tree(path), at_node):
            _update_function_scope_bindings(
                scope,
                bindings,
                module_name=module_name,
                at_node=at_node,
            )
    return bindings


def qualified_symbol_binding_choices(
    context: ArchitectureContext,
    path: Path,
    *,
    at_node: ast.AST | None,
) -> dict[str, frozenset[str]]:
    """Return conservative reaching bindings, merging control-flow branches."""

    deterministic = qualified_symbol_bindings(context, path, at_node=None)
    choices = {name: frozenset({value}) for name, value in deterministic.items()}
    if at_node is None:
        return choices
    tree = context.tree(path)
    definition_time = _is_definition_time_expression(tree, at_node)
    class_scope = _class_body_scope_for_expression(tree, at_node)
    class_body_time = class_scope is not None
    if definition_time or class_body_time:
        module_name = (
            _source_module_name(path, context) if path.is_relative_to(context.src_root) else ""
        )
        choices, _found = _flow_bindings_to_target(
            tree.body,
            {},
            target=at_node,
            module_name=module_name,
        )
        if class_scope is not None:
            choices, _found = _flow_bindings_to_target(
                class_scope.body,
                choices,
                target=at_node,
                module_name=module_name,
            )
        choices = {
            name: frozenset(
                _module_qualified_choice(value, module_name=module_name) for value in values
            )
            for name, values in choices.items()
        }
        exact = qualified_symbol_bindings(context, path, at_node=at_node)
        for name, value in exact.items():
            choices.setdefault(name, frozenset({value}))
        return choices
    module_name = (
        _source_module_name(path, context) if path.is_relative_to(context.src_root) else ""
    )
    for scope in _containing_lexical_scopes(context.tree(path), at_node):
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            arguments = (
                *scope.args.posonlyargs,
                *scope.args.args,
                *scope.args.kwonlyargs,
            )
            for argument in arguments:
                choices[argument.arg] = frozenset(
                    {argument.arg if argument.arg in {"self", "cls"} else f"<local>.{argument.arg}"}
                )
            if scope.args.vararg is not None:
                choices[scope.args.vararg.arg] = frozenset({f"<local>.{scope.args.vararg.arg}"})
            if scope.args.kwarg is not None:
                choices[scope.args.kwarg.arg] = frozenset({f"<local>.{scope.args.kwarg.arg}"})
            if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
                choices, _found = _flow_bindings_to_target(
                    scope.body,
                    choices,
                    target=at_node,
                    module_name=module_name,
                )
        else:
            for generator in scope.generators:
                for name in _stored_names(generator.target):
                    choices[name] = frozenset({f"<local>.{name}"})
    return choices


def _class_body_scope_for_expression(
    tree: ast.Module,
    target: ast.AST,
) -> ast.ClassDef | None:
    containing: list[ast.ClassDef] = []

    def visit(node: ast.AST) -> bool:
        if node is target:
            return True
        for child in ast.iter_child_nodes(node):
            if visit(child):
                if isinstance(node, ast.ClassDef):
                    containing.append(node)
                return True
        return False

    visit(tree)
    return next(
        (
            class_scope
            for class_scope in containing
            if _is_class_body_time_expression(class_scope, target)
        ),
        None,
    )


def _is_class_body_time_expression(
    class_scope: ast.ClassDef,
    target: ast.AST,
) -> bool:
    def evaluated_in_class_body(node: ast.AST) -> bool:
        if node is target:
            return True
        expressions: tuple[ast.AST, ...]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            expressions = (
                *node.decorator_list,
                *node.args.defaults,
                *(default for default in node.args.kw_defaults if default is not None),
                *(argument.annotation for argument in node.args.posonlyargs if argument.annotation),
                *(argument.annotation for argument in node.args.args if argument.annotation),
                *(argument.annotation for argument in node.args.kwonlyargs if argument.annotation),
                *(
                    (node.args.vararg.annotation,)
                    if node.args.vararg and node.args.vararg.annotation
                    else ()
                ),
                *(
                    (node.args.kwarg.annotation,)
                    if node.args.kwarg and node.args.kwarg.annotation
                    else ()
                ),
                *((node.returns,) if node.returns is not None else ()),
            )
        elif isinstance(node, ast.Lambda):
            expressions = (
                *node.args.defaults,
                *(default for default in node.args.kw_defaults if default is not None),
            )
        elif isinstance(node, ast.ClassDef):
            expressions = (
                *node.decorator_list,
                *node.bases,
                *(item.value for item in node.keywords),
            )
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            expressions = (node.generators[0].iter,) if node.generators else ()
        else:
            expressions = tuple(ast.iter_child_nodes(node))
        return any(evaluated_in_class_body(expression) for expression in expressions)

    return any(evaluated_in_class_body(statement) for statement in class_scope.body)


LexicalScope = (
    ast.FunctionDef
    | ast.AsyncFunctionDef
    | ast.Lambda
    | ast.ListComp
    | ast.SetComp
    | ast.DictComp
    | ast.GeneratorExp
)


def _containing_lexical_scopes(
    tree: ast.Module,
    target: ast.AST,
) -> tuple[LexicalScope, ...]:
    scopes: list[LexicalScope] = []

    def visit(node: ast.AST) -> bool:
        if node is target:
            return True
        for child in ast.iter_child_nodes(node):
            if visit(child):
                if isinstance(
                    node,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                        ast.Lambda,
                        ast.ListComp,
                        ast.SetComp,
                        ast.DictComp,
                        ast.GeneratorExp,
                    ),
                ):
                    scopes.append(node)
                return True
        return False

    visit(tree)
    scopes.reverse()
    return tuple(scopes)


def _update_function_scope_bindings(
    function: LexicalScope,
    bindings: dict[str, str],
    *,
    module_name: str,
    at_node: ast.AST,
) -> None:
    if isinstance(function, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        for generator in function.generators:
            for name in _stored_names(generator.target):
                bindings[name] = f"<local>.{name}"
        return
    arguments = (
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    )
    for argument in arguments:
        bindings[argument.arg] = (
            argument.arg if argument.arg in {"self", "cls"} else f"<local>.{argument.arg}"
        )
    if function.args.vararg is not None:
        bindings[function.args.vararg.arg] = f"<local>.{function.args.vararg.arg}"
    if function.args.kwarg is not None:
        bindings[function.args.kwarg.arg] = f"<local>.{function.args.kwarg.arg}"

    target_position = _node_position(at_node)
    if isinstance(function, ast.Lambda):
        return
    for node in _lexical_scope_nodes(function):
        node_position = _node_position(node)
        if (
            target_position is not None
            and node_position is not None
            and node_position >= target_position
        ):
            continue
        _update_lexical_binding(
            node,
            bindings,
            module_name=module_name,
            local_scope=True,
        )


def _is_definition_time_expression(tree: ast.Module, target: ast.AST) -> bool:
    def contains(root: ast.AST | None) -> bool:
        return root is not None and any(node is target for node in ast.walk(root))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if any(contains(expression) for expression in (*node.decorator_list, *node.bases)):
                return True
            if any(contains(keyword.value) for keyword in node.keywords):
                return True
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if not isinstance(node, ast.Lambda) and any(
            contains(expression) for expression in node.decorator_list
        ):
            return True
        if not isinstance(node, ast.Lambda) and contains(node.returns):
            return True
        if any(
            contains(expression)
            for expression in (
                *node.args.defaults,
                *(default for default in node.args.kw_defaults if default is not None),
                *(argument.annotation for argument in node.args.posonlyargs if argument.annotation),
                *(argument.annotation for argument in node.args.args if argument.annotation),
                *(argument.annotation for argument in node.args.kwonlyargs if argument.annotation),
            )
        ):
            return True
    return False


def _flow_bindings_to_target(
    statements: list[ast.stmt],
    state: dict[str, frozenset[str]],
    *,
    target: ast.AST,
    module_name: str,
) -> tuple[dict[str, frozenset[str]], bool]:
    current = dict(state)
    for statement in statements:
        if _contains_node(statement, target):
            branch_entry = _flow_statement_entry_bindings(
                statement,
                current,
                before_target=target,
            )
            if isinstance(statement, ast.Try):
                if any(_contains_node(child, target) for child in statement.finalbody):
                    before_final = _flow_try_before_finally(
                        statement,
                        current,
                        module_name=module_name,
                    )
                    return _flow_bindings_to_target(
                        statement.finalbody,
                        before_final,
                        target=target,
                        module_name=module_name,
                    )
                if any(_contains_node(child, target) for child in statement.orelse):
                    body_state = _flow_complete_block(
                        statement.body,
                        current,
                        module_name=module_name,
                    )
                    return _flow_bindings_to_target(
                        statement.orelse,
                        body_state,
                        target=target,
                        module_name=module_name,
                    )
                for handler in statement.handlers:
                    if any(_contains_node(child, target) for child in handler.body):
                        return _flow_bindings_to_target(
                            handler.body,
                            _flow_try_handler_entry_state(
                                statement,
                                current,
                                module_name=module_name,
                            ),
                            target=target,
                            module_name=module_name,
                        )
            for branch in _statement_branches(statement):
                if any(_contains_node(child, target) for child in branch):
                    return _flow_bindings_to_target(
                        branch,
                        branch_entry,
                        target=target,
                        module_name=module_name,
                    )
            return branch_entry, True
        current = _flow_statement_bindings(statement, current, module_name=module_name)
    return current, False


def _flow_statement_bindings(
    statement: ast.stmt,
    state: dict[str, frozenset[str]],
    *,
    module_name: str,
) -> dict[str, frozenset[str]]:
    current = _flow_statement_entry_bindings(statement, state)
    if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        for target in targets:
            _bind_choice_target(target, statement.value, current)
        return current
    if isinstance(statement, ast.Try):
        before_final = _flow_try_before_finally(
            statement,
            current,
            module_name=module_name,
        )
        return _flow_complete_block(
            statement.finalbody,
            before_final,
            module_name=module_name,
        )
    branches = _statement_branches(statement)
    if branches:
        branch_states = [
            _flow_complete_block(branch, current, module_name=module_name) for branch in branches
        ]
        if isinstance(statement, (ast.For, ast.AsyncFor, ast.While, ast.Match)):
            branch_states.append(current)
        return _merge_binding_states(branch_states)
    _update_choice_binding(statement, current, module_name=module_name)
    return current


def _flow_statement_entry_bindings(
    statement: ast.stmt,
    state: dict[str, frozenset[str]],
    *,
    before_target: ast.AST | None = None,
) -> dict[str, frozenset[str]]:
    current = dict(state)
    expressions: tuple[ast.expr, ...] = ()
    if isinstance(statement, (ast.If, ast.While)):
        expressions = (statement.test,)
    elif isinstance(statement, (ast.For, ast.AsyncFor)):
        expressions = (statement.iter,)
    elif isinstance(statement, (ast.Assign, ast.AnnAssign, ast.Expr, ast.Return)):
        expressions = (statement.value,) if statement.value is not None else ()
    elif isinstance(statement, ast.Raise):
        expressions = tuple(
            expression for expression in (statement.exc, statement.cause) if expression is not None
        )
    elif isinstance(statement, ast.Assert):
        expressions = (statement.test,) + ((statement.msg,) if statement.msg is not None else ())
    elif isinstance(statement, (ast.With, ast.AsyncWith)):
        expressions = tuple(item.context_expr for item in statement.items)
    elif isinstance(statement, ast.Match):
        expressions = (statement.subject,)
    for expression in expressions:
        for node in ast.walk(expression):
            if isinstance(node, ast.NamedExpr) and (
                before_target is None or _node_ends_before(node, before_target)
            ):
                _bind_choice_target(node.target, node.value, current)
    return current


def _node_ends_before(node: ast.AST, target: ast.AST) -> bool:
    end_line = getattr(node, "end_lineno", None)
    end_column = getattr(node, "end_col_offset", None)
    target_line = getattr(target, "lineno", None)
    target_column = getattr(target, "col_offset", None)
    if not all(
        isinstance(value, int) for value in (end_line, end_column, target_line, target_column)
    ):
        return False
    return (end_line, end_column) <= (target_line, target_column)


def _flow_try_before_finally(
    statement: ast.Try,
    state: dict[str, frozenset[str]],
    *,
    module_name: str,
) -> dict[str, frozenset[str]]:
    body_state = _flow_complete_block(statement.body, state, module_name=module_name)
    if body_state:
        body_state = _flow_complete_block(
            statement.orelse,
            body_state,
            module_name=module_name,
        )
    handler_entry = _flow_try_handler_entry_state(
        statement,
        state,
        module_name=module_name,
    )
    handler_states = [
        _flow_complete_block(handler.body, handler_entry, module_name=module_name)
        for handler in statement.handlers
    ]
    return _merge_binding_states([body_state, *handler_states])


def _flow_try_handler_entry_state(
    statement: ast.Try,
    state: dict[str, frozenset[str]],
    *,
    module_name: str,
) -> dict[str, frozenset[str]]:
    prefixes = [dict(state)]
    current = dict(state)
    for body_statement in statement.body:
        current = _flow_statement_bindings(
            body_statement,
            current,
            module_name=module_name,
        )
        prefixes.append(current)
        if isinstance(body_statement, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
            break
    return _merge_binding_states(prefixes)


def _flow_complete_block(
    statements: list[ast.stmt],
    state: dict[str, frozenset[str]],
    *,
    module_name: str,
) -> dict[str, frozenset[str]]:
    current = dict(state)
    for statement in statements:
        if isinstance(statement, ast.Return):
            return {}
        if isinstance(statement, (ast.Raise, ast.Break, ast.Continue)):
            return current
        current = _flow_statement_bindings(statement, current, module_name=module_name)
    return current


def _module_qualified_choice(value: str, *, module_name: str) -> str:
    for prefix in ("<local-class>.", "<local>."):
        if value.startswith(prefix):
            suffix = value.removeprefix(prefix)
            return f"{module_name}.{suffix}" if module_name else suffix
    return value


def _statement_branches(statement: ast.stmt) -> tuple[list[ast.stmt], ...]:
    if isinstance(statement, ast.If):
        return (statement.body, statement.orelse)
    if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
        return (statement.body, statement.orelse)
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return (statement.body,)
    if isinstance(statement, ast.Try):
        return (statement.body, *(handler.body for handler in statement.handlers))
    if isinstance(statement, ast.Match):
        return tuple(case.body for case in statement.cases)
    return ()


def _merge_binding_states(
    states: list[dict[str, frozenset[str]]],
) -> dict[str, frozenset[str]]:
    states = [state for state in states if state]
    if not states:
        return {}
    names: set[str] = set()
    for state in states:
        names.update(state)
    return {
        name: frozenset().union(*(state.get(name, frozenset()) for state in states))
        for name in names
    }


def _resolve_expression_choices(
    expression: ast.expr | None,
    bindings: dict[str, frozenset[str]],
) -> frozenset[str]:
    if isinstance(expression, ast.IfExp):
        return _resolve_expression_choices(expression.body, bindings) | _resolve_expression_choices(
            expression.orelse, bindings
        )
    if isinstance(expression, ast.NamedExpr):
        return _resolve_expression_choices(expression.value, bindings)
    chain = attribute_chain(expression)
    if not chain:
        return frozenset()
    roots = bindings.get(chain[0], frozenset({chain[0]}))
    return frozenset(".".join((root, *chain[1:])) for root in roots)


def _bind_choice_target(
    target: ast.expr,
    value: ast.expr | None,
    bindings: dict[str, frozenset[str]],
) -> None:
    if (
        isinstance(target, (ast.Tuple, ast.List))
        and isinstance(value, (ast.Tuple, ast.List))
        and len(target.elts) == len(value.elts)
    ):
        for child_target, child_value in zip(target.elts, value.elts, strict=True):
            _bind_choice_target(child_target, child_value, bindings)
        return
    if isinstance(target, ast.Starred):
        _bind_choice_target(target.value, value, bindings)
        return
    values = _resolve_expression_choices(value, bindings)
    if not values and isinstance(value, (ast.Tuple, ast.List)):
        values = frozenset(
            resolved
            for element in value.elts
            for resolved in _resolve_expression_choices(element, bindings)
        )
    for name in _stored_names(target):
        bindings[name] = values or frozenset({f"<local>.{name}"})


def _update_choice_binding(
    node: ast.AST,
    bindings: dict[str, frozenset[str]],
    *,
    module_name: str,
) -> None:
    deterministic = {name: next(iter(values)) for name, values in bindings.items() if values}
    before = dict(deterministic)
    _update_lexical_binding(node, deterministic, module_name=module_name, local_scope=True)
    for name, value in deterministic.items():
        if before.get(name) != value:
            bindings[name] = frozenset({value})


def _stored_names(expression: ast.expr) -> set[str]:
    return {
        node.id
        for node in ast.walk(expression)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }


def _contains_node(root: ast.AST, target: ast.AST) -> bool:
    return any(node is target for node in ast.walk(root))


def _lexical_scope_nodes(
    scope: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[ast.AST, ...]:
    nodes: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        if node is not scope and isinstance(
            node,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        ):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                nodes.append(node)
            return
        nodes.append(node)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(scope)
    return tuple(
        sorted(
            nodes,
            key=lambda node: _node_position(node) or (-1, -1),
        )
    )


def _node_position(node: ast.AST) -> tuple[int, int] | None:
    line = getattr(node, "lineno", None)
    column = getattr(node, "col_offset", None)
    return (line, column) if isinstance(line, int) and isinstance(column, int) else None


def _update_lexical_binding(
    node: ast.AST,
    bindings: dict[str, str],
    *,
    module_name: str,
    local_scope: bool,
) -> None:
    type_alias_name = getattr(node, "name", None)
    if type(node).__name__ == "TypeAlias" and isinstance(type_alias_name, ast.Name):
        bindings[type_alias_name.id] = (
            f"<local>.{type_alias_name.id}"
            if local_scope
            else f"{module_name}.{type_alias_name.id}"
            if module_name
            else type_alias_name.id
        )
        return
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        _update_import_bindings(node, bindings, module_name=module_name)
        return
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        bindings[node.name] = (
            f"<local-class>.{node.name}"
            if local_scope and isinstance(node, ast.ClassDef)
            else f"<local>.{node.name}"
            if local_scope
            else f"{module_name}.{node.name}"
            if module_name
            else node.name
        )
        return
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
        targets: tuple[ast.expr, ...]
        value: ast.expr | None
        if isinstance(node, ast.Assign):
            targets = tuple(node.targets)
            value = node.value
        else:
            targets = (node.target,)
            value = node.value
        for target in targets:
            _bind_deterministic_target(target, value, bindings)


def _bind_deterministic_target(
    target: ast.expr,
    value: ast.expr | None,
    bindings: dict[str, str],
) -> None:
    if (
        isinstance(target, (ast.Tuple, ast.List))
        and isinstance(value, (ast.Tuple, ast.List))
        and len(target.elts) == len(value.elts)
    ):
        for child_target, child_value in zip(target.elts, value.elts, strict=True):
            _bind_deterministic_target(child_target, child_value, bindings)
        return
    if isinstance(target, ast.Starred):
        _bind_deterministic_target(target.value, value, bindings)
        return
    resolved_value = _resolve_expression_with_bindings(value, bindings)
    for name in _stored_names(target):
        bindings[name] = resolved_value or f"<local>.{name}"


def _resolve_expression_with_bindings(
    expression: ast.expr | None,
    bindings: dict[str, str],
) -> str | None:
    chain = attribute_chain(expression)
    if not chain:
        return None
    return ".".join((bindings.get(chain[0], chain[0]), *chain[1:]))


def _index_class_definitions(
    statements: list[ast.stmt],
    *,
    bindings: dict[str, str],
    path: Path,
    module_name: str,
    mutable_index: dict[str, list[tuple[Path, set[str]]]],
) -> None:
    for node in statements:
        if isinstance(node, ast.ClassDef):
            mutable_index.setdefault(node.name, []).append(
                (
                    path,
                    {_resolved_class_reference(base, bindings) for base in node.bases},
                )
            )
            _index_class_definitions(
                node.body,
                bindings=bindings.copy(),
                path=path,
                module_name=module_name,
                mutable_index=mutable_index,
            )
            bindings[node.name] = f"{module_name}.{node.name}"
            continue
        _update_lexical_binding(
            node,
            bindings,
            module_name=module_name,
            local_scope=False,
        )
        for _, value in ast.iter_fields(node):
            raw_value = cast(object, value)
            if not isinstance(raw_value, list):
                continue
            items = cast(list[object], raw_value)
            nested_statements = [child for child in items if isinstance(child, ast.stmt)]
            if not nested_statements or len(nested_statements) != len(items):
                continue
            _index_class_definitions(
                nested_statements,
                bindings=bindings.copy(),
                path=path,
                module_name=module_name,
                mutable_index=mutable_index,
            )


def _update_import_bindings(
    node: ast.stmt,
    bindings: dict[str, str],
    *,
    module_name: str,
) -> None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".")[0]
            bindings[local_name] = alias.name if alias.asname else local_name
    elif isinstance(node, ast.ImportFrom):
        imported_module = _imported_module_name(node, module_name=module_name)
        for alias in node.names:
            if alias.name == "*":
                continue
            local_name = alias.asname or alias.name
            bindings[local_name] = f"{imported_module}.{alias.name}"


def _imported_module_name(node: ast.ImportFrom, *, module_name: str) -> str:
    if node.level == 0:
        return node.module or ""
    package_parts = module_name.split(".")[:-1]
    parent_parts = package_parts[: len(package_parts) - (node.level - 1)]
    imported_parts = tuple(part for part in (node.module or "").split(".") if part)
    return ".".join((*parent_parts, *imported_parts))


def _resolved_class_reference(base: ast.expr, bindings: dict[str, str]) -> str:
    expression = base.value if isinstance(base, ast.Subscript) else base
    chain = attribute_chain(expression)
    if not chain:
        return ast.unparse(expression)
    return ".".join((bindings.get(chain[0], chain[0]), *chain[1:]))


def foundation_base_names_for_class(
    class_name: str,
    class_base_name_index: dict[str, set[str]],
    *,
    visited: set[str] | None = None,
) -> set[str]:
    visited = visited or set()
    if class_name in visited:
        return set()
    visited.add(class_name)
    base_names = class_base_name_index.get(class_name, set())
    foundation_base_names = {
        found_base for found_base in base_names if class_suffix_from_base(found_base) is not None
    }
    for found_base in base_names:
        foundation_base_names.update(
            foundation_base_names_for_class(
                found_base,
                class_base_name_index,
                visited=visited,
            ),
        )
    return foundation_base_names


def class_has_foundation_base(
    class_name: str,
    base: str,
    class_base_name_index: dict[str, set[str]],
    *,
    visited: set[str] | None = None,
) -> bool:
    visited = visited or set()
    if class_name in visited:
        return False
    visited.add(class_name)
    base_names = class_base_name_index.get(class_name, set())
    return base in base_names or any(
        class_has_foundation_base(
            found_base,
            base,
            class_base_name_index,
            visited=visited,
        )
        for found_base in base_names
    )


def nearest_foundation_base_names_for_class(
    class_name: str,
    class_base_name_index: dict[str, set[str]],
    *,
    visited: set[str] | None = None,
) -> set[str]:
    visited = visited or set()
    if class_name in visited:
        return set()
    visited.add(class_name)
    base_names = class_base_name_index.get(class_name, set())
    direct_foundation_bases = {
        found_base for found_base in base_names if class_suffix_from_base(found_base) is not None
    }
    if direct_foundation_bases:
        return direct_foundation_bases
    nearest: set[str] = set()
    for found_base in base_names:
        nearest.update(
            nearest_foundation_base_names_for_class(
                found_base,
                class_base_name_index,
                visited=visited,
            ),
        )
    return nearest


def execute_methods_with_classes(
    tree: ast.Module,
) -> list[tuple[ast.ClassDef, ast.AsyncFunctionDef | ast.FunctionDef]]:
    pairs: list[tuple[ast.ClassDef, ast.AsyncFunctionDef | ast.FunctionDef]] = []
    for class_node in [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]:
        for child in class_node.body:
            if (
                isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef))
                and child.name == "execute"
            ):
                pairs.append((class_node, child))
    return pairs


def class_injected_repository_field_names(
    class_node: ast.ClassDef,
    aliases: dict[str, str],
    class_base_name_index: dict[str, set[str]],
) -> set[str]:
    fields: set[str] = set()
    for child in class_node.body:
        if not isinstance(child, ast.AnnAssign) or not isinstance(child.target, ast.Name):
            continue
        injected_name = injected_type_name(child.annotation, aliases)
        if injected_name.endswith("Repository") or class_has_foundation_base(
            injected_name,
            "BaseRepository",
            class_base_name_index,
        ):
            fields.add(child.target.id)
    return fields


def class_injected_repository_field_names_at(
    class_node: ast.ClassDef,
    aliases: dict[str, str],
    *,
    source_path: Path,
    context: ArchitectureContext,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
) -> set[str]:
    """Return repository fields without conflating same-named project classes."""

    fields: set[str] = set()
    for child in class_node.body:
        if not isinstance(child, ast.AnnAssign) or not isinstance(child.target, ast.Name):
            continue
        injected_name = injected_type_name(child.annotation, aliases)
        if injected_name.endswith("Repository") or class_has_foundation_base_from_path(
            injected_name,
            "BaseRepository",
            source_path=source_path,
            context=context,
            definition_index=definition_index,
        ):
            fields.add(child.target.id)
    return fields


def class_injected_unit_of_work_manager_field_names(
    class_node: ast.ClassDef,
    aliases: dict[str, str],
) -> set[str]:
    fields: set[str] = set()
    for child in class_node.body:
        if not isinstance(child, ast.AnnAssign) or not isinstance(child.target, ast.Name):
            continue
        if injected_type_name(child.annotation, aliases).endswith("UnitOfWorkManager"):
            fields.add(child.target.id)
    return fields


def class_unit_of_work_field_names(
    class_node: ast.ClassDef,
    aliases: dict[str, str],
) -> set[str]:
    fields: set[str] = set()
    for child in class_node.body:
        if not isinstance(child, ast.AnnAssign) or not isinstance(child.target, ast.Name):
            continue
        annotation = annotation_name(child.annotation, aliases)
        if "UnitOfWork" in annotation:
            fields.add(child.target.id)
    return fields


def class_dependency_annotations(
    class_node: ast.ClassDef,
    aliases: dict[str, str],
) -> set[str]:
    annotations: set[str] = set()
    for child in class_node.body:
        if isinstance(child, ast.AnnAssign):
            annotations.add(annotation_name(child.annotation, aliases))
    return annotations


def class_has_any_foundation_base(
    class_name: str,
    bases: set[str],
    class_base_name_index: dict[str, set[str]],
) -> bool:
    return any(class_has_foundation_base(class_name, base, class_base_name_index) for base in bases)


def forbidden_dependency_fragments(dependency_name: str, fragments: tuple[str, ...]) -> set[str]:
    return {fragment for fragment in fragments if fragment in dependency_name}


def calls_forbidden_method(
    call: ast.Call,
    method_names: set[str],
    prefixes: tuple[str, ...],
) -> bool:
    return isinstance(call.func, ast.Attribute) and (
        call.func.attr in method_names or call.func.attr.startswith(prefixes)
    )


def module_has_forbidden_parts(
    module: str,
    *,
    roots: set[str],
    parts: set[str],
) -> bool:
    parts_from_module = module_parts(module)
    return bool(parts_from_module) and (
        parts_from_module[0] in roots or any(part in parts for part in parts_from_module)
    )


def _path_has_parts(path: Path, expected: tuple[str, ...]) -> bool:
    parts = path.parts
    if len(parts) < len(expected):
        return False
    return all(
        expected_part == "*" or parts[index] == expected_part
        for index, expected_part in enumerate(expected)
    )
