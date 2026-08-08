from __future__ import annotations

import ast
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
    active_uow_names,
    active_uow_names_from_manager_fields,
    annotation_name,
    attribute_chain,
    class_definition_base_index,
    class_has_foundation_base_at,
    class_has_foundation_base_from_path,
    class_injected_unit_of_work_manager_field_names,
    injected_type_name,
    module_parts,
)
from specx.testing.architecture.models import RuleIdentifier, SpecxArchitectureViolation
from specx.testing.architecture.rule import BaseRule
from specx.testing.architecture.rule_id import SpecxRuleId

ArchitectureRuleBase = BaseRule[
    SpecxRuleId,
    ArchitectureContext,
    SpecxArchitectureViolation,
]

USE_CASE_FORBIDDEN_INFRASTRUCTURE_DEPENDENCY_NAMES = frozenset(
    {
        "AsyncConnection",
        "AsyncEngine",
        "AsyncSession",
        "Connection",
        "Engine",
        "Session",
        "SQLAlchemySessionFactory",
        "async_sessionmaker",
        "sessionmaker",
    }
)

CORE_BEHAVIOR_TEST_PACKAGE_NAMES = frozenset({"capabilities", "services", "use_cases"})


def violation(
    rule_id: RuleIdentifier,
    *,
    message: str,
    path: Path | None = None,
    symbol: str | None = None,
    node: ast.AST | None = None,
) -> SpecxArchitectureViolation:
    return SpecxArchitectureViolation(
        rule_id=rule_id,
        message=message,
        path=path,
        symbol=symbol,
        line=getattr(node, "lineno", None),
        column=(getattr(node, "col_offset", -1) + 1 if hasattr(node, "col_offset") else None),
    )


ALLOWED_UNVERSIONED_OPERATIONAL_ROUTE_PATHS = frozenset({"/healthz", "/readyz"})


def target_folder_test_exists(
    flat_path: Path,
    *,
    context: ArchitectureContext,
) -> bool:
    target_name = flat_path.stem.removeprefix("test_")
    target_folder_path = flat_path.parent / target_name / flat_path.name

    return target_folder_path in context.ast_project.files


def python_package_directories(
    context: ArchitectureContext,
    *,
    root: Path,
) -> tuple[Path, ...]:
    directories: set[Path] = set()
    for path in context.ast_project.files:
        if not path.is_relative_to(root):
            continue
        parent = path.parent
        while parent.is_relative_to(root):
            directories.add(parent)
            if parent == root:
                break
            parent = parent.parent
    return tuple(sorted(directories))


def is_use_case_class_at(
    class_node: ast.ClassDef,
    *,
    path: Path,
    context: ArchitectureContext,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
) -> bool:
    return class_has_foundation_base_at(
        class_node,
        "BaseUseCase",
        source_path=path,
        context=context,
        definition_index=definition_index,
    )


def use_case_imports_persistence_infrastructure(module: str) -> bool:
    parts = module_parts(module)
    return "infrastructure" in parts or bool(parts and parts[0] == "sqlalchemy")


def is_scope_technical_import(module: str) -> bool:
    parts = module_parts(module)
    if "core" not in parts:
        return False

    core_index = parts.index("core")
    scope_relative_parts = parts[core_index + 2 :]
    return any(
        part in {"alembic", "infrastructure", "migrations", "models", "repositories"}
        for part in scope_relative_parts
    )


def forbidden_use_case_persistence_dependency_fields(
    class_node: ast.ClassDef,
    aliases: dict[str, str],
    *,
    source_path: Path,
    context: ArchitectureContext,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
) -> list[str]:
    fields: list[str] = []
    for child in class_node.body:
        if not isinstance(child, ast.AnnAssign) or not isinstance(child.target, ast.Name):
            continue

        injected_name = injected_type_name(child.annotation, aliases)
        if not injected_name:
            continue

        if _is_forbidden_use_case_persistence_dependency(
            injected_name,
            source_path=source_path,
            context=context,
            definition_index=definition_index,
        ):
            annotation = annotation_name(child.annotation, aliases)
            fields.append(f"{child.target.id}:{annotation}")
    return sorted(fields)


def _is_forbidden_use_case_persistence_dependency(
    dependency_name: str,
    *,
    source_path: Path,
    context: ArchitectureContext,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
) -> bool:
    if dependency_name.endswith("Repository") or class_has_foundation_base_from_path(
        dependency_name,
        "BaseRepository",
        source_path=source_path,
        context=context,
        definition_index=definition_index,
    ):
        return True

    return any(
        forbidden_name in dependency_name
        for forbidden_name in USE_CASE_FORBIDDEN_INFRASTRUCTURE_DEPENDENCY_NAMES
    )


def repository_calls_outside_manager_owned_uow(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    *,
    manager_fields: set[str],
    repository_fields: set[str],
) -> set[str]:
    manager_owned_uow_names = active_uow_names_from_manager_fields(function, manager_fields)
    uow_like_names = {
        name for name in active_uow_names(function) if _name_looks_like_unit_of_work(name)
    }
    repository_alias_names = _repository_alias_names_from_uow_names(
        function,
        manager_owned_uow_names | uow_like_names,
    )
    bad_calls: set[str] = set()
    for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
        chain = attribute_chain(call.func)
        if not chain:
            continue
        if chain[0] in manager_owned_uow_names:
            continue
        if chain[0] in uow_like_names and len(chain) >= 3:
            bad_calls.add(".".join(chain))
            continue
        if _call_chain_uses_direct_repository(
            chain,
            repository_fields=repository_fields,
            repository_alias_names=repository_alias_names,
        ):
            bad_calls.add(".".join(chain))
    return bad_calls


def _repository_alias_names_from_uow_names(
    function: ast.AsyncFunctionDef | ast.FunctionDef,
    uow_names: set[str],
) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign):
            continue
        value_chain = attribute_chain(node.value)
        if len(value_chain) < 2 or value_chain[0] not in uow_names:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                aliases.add(target.id)
    return aliases


def _call_chain_uses_direct_repository(
    chain: tuple[str, ...],
    *,
    repository_fields: set[str],
    repository_alias_names: set[str],
) -> bool:
    if len(chain) < 2:
        return False
    if chain[0] in repository_alias_names:
        return True
    if chain[0] == "self" and len(chain) >= 3 and chain[1] in repository_fields:
        return True
    return any(_name_looks_like_repository(segment) for segment in chain[:-1])


def _name_looks_like_repository(name: str) -> bool:
    normalized = name.strip("_").lower()
    return normalized == "repository" or normalized.endswith("_repository")


def _name_looks_like_unit_of_work(name: str) -> bool:
    normalized = name.strip("_").lower()
    return normalized in {"unit_of_work", "uow"} or normalized.endswith("_unit_of_work")


def is_injected_logger_annotation(
    annotation: ast.expr | None,
    aliases: dict[str, str],
    imports: frozenset[str],
) -> bool:
    if annotation is None:
        return False
    if not isinstance(annotation, ast.Subscript):
        return False
    if annotation_name(annotation.value, aliases) != "Injected":
        return False

    return is_logging_logger_expression(annotation.slice, aliases, imports)


def _is_injected_container_annotation(
    annotation: ast.expr | None,
    aliases: dict[str, str],
) -> bool:
    if annotation is None:
        return False
    if not isinstance(annotation, ast.Subscript):
        return False
    if annotation_name(annotation.value, aliases) != "Injected":
        return False

    return _is_diwire_container_expression(annotation.slice, aliases)


def class_injects_diwire_container(
    class_node: ast.ClassDef,
    aliases: dict[str, str],
) -> bool:
    for child in class_node.body:
        if isinstance(child, ast.AnnAssign) and _is_injected_container_annotation(
            child.annotation,
            aliases,
        ):
            return True
        if isinstance(child, ast.FunctionDef) and child.name == "__init__":
            for argument in (
                *child.args.posonlyargs,
                *child.args.args,
                *child.args.kwonlyargs,
            ):
                if argument.arg == "self":
                    continue
                if _is_injected_container_annotation(argument.annotation, aliases):
                    return True

    return False


def class_can_inject_container(
    relative: Path,
    class_node: ast.ClassDef,
    *,
    source_path: Path,
    context: ArchitectureContext,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
) -> bool:
    return (
        len(relative.parts) == 3
        and relative.parts[0] == "delivery"
        and relative.name == "lifecycle.py"
        and class_node.name.endswith("Lifecycle")
        and class_has_foundation_base_at(
            class_node,
            "BaseLifecycle",
            source_path=source_path,
            context=context,
            definition_index=definition_index,
        )
    )


def is_delivery_composition_module(relative: Path) -> bool:
    return (
        len(relative.parts) == 3
        and relative.parts[0] == "delivery"
        and relative.name in {"__main__.py", "factory.py", "lifecycle.py"}
    )


def _is_diwire_container_expression(
    expression: ast.expr,
    aliases: dict[str, str],
) -> bool:
    if isinstance(expression, ast.Attribute) and expression.attr == "Container":
        chain = attribute_chain(expression)
        if len(chain) >= 2:
            root_alias = aliases.get(chain[0], chain[0])
            return root_alias == "diwire"

    if isinstance(expression, ast.Name):
        return aliases.get(expression.id, expression.id) == "Container"

    return False


def is_logging_logger_expression(
    expression: ast.expr,
    aliases: dict[str, str],
    imports: frozenset[str],
) -> bool:
    if isinstance(expression, ast.Attribute) and expression.attr == "Logger":
        chain = attribute_chain(expression)
        if len(chain) >= 2:
            root_alias = aliases.get(chain[0], chain[0])
            return root_alias == "logging"

    if isinstance(expression, ast.Name):
        return aliases.get(expression.id, expression.id) == "Logger" and "logging.Logger" in imports

    return False


def is_container_registration_call(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Attribute) and node.func.attr in {
        "add",
        "add_context_manager",
        "add_context_manager_class",
        "add_factory",
        "add_factory_class",
        "add_generator",
        "add_generator_class",
        "add_instance",
    }


def project_uses_alembic(context: ArchitectureContext) -> bool:
    return (context.project_root / "alembic.ini").exists() or (
        context.project_root / "migrations"
    ).exists()


def mirrored_test_paths(
    context: ArchitectureContext,
    *,
    test_root: Path,
) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(context.ast_project.files)
        if path.is_relative_to(test_root)
        and (path.name.startswith("test_") or path.name.startswith("fake_"))
        and path.name.endswith(".py")
    )


def source_paths_for_test_path(
    path: Path,
    *,
    test_root: Path,
    src_root: Path,
) -> tuple[Path, ...]:
    relative = path.relative_to(test_root)
    source_file_name = relative.name.removeprefix("test_").removeprefix("fake_")
    direct_mirror_path = src_root / relative.parent / source_file_name

    return (direct_mirror_path,)


def is_fake_module_path(path: Path) -> bool:
    return path.name.startswith("fake_") and path.name.endswith(".py")


def is_allowed_mirrored_fake_module_path(path: Path, *, test_root: Path) -> bool:
    allowed_fake_package_names = {"capabilities", "gateways", "repositories"}
    unit_core_root = test_root / "unit" / "core"
    if not path.is_relative_to(unit_core_root):
        return False
    relative = path.relative_to(unit_core_root)

    return len(relative.parts) >= 3 and relative.parts[1] in allowed_fake_package_names


def is_core_behavior_test_path(relative: Path) -> bool:
    parts = relative.parts
    return len(parts) >= 4 and parts[0] == "core" and parts[2] in CORE_BEHAVIOR_TEST_PACKAGE_NAMES


def is_core_behavior_target_test_path(relative: Path) -> bool:
    source_file_name = relative.name.removeprefix("test_")
    source_stem = Path(source_file_name).stem
    return len(relative.parts) >= 5 and relative.parent.name == source_stem


def flat_test_path_for_source_path(
    path: Path,
    *,
    test_root: Path,
    src_root: Path,
) -> Path:
    relative = path.relative_to(src_root)
    return test_root / relative.parent / f"test_{relative.name}"


def is_target_specific_test_factory_or_harness(class_name: str) -> bool:
    return class_name.endswith(
        (
            "CapabilityFactory",
            "CapabilityHarness",
            "ControllerFactory",
            "ControllerHarness",
            "ServiceFactory",
            "ServiceHarness",
            "UseCaseFactory",
            "UseCaseHarness",
        )
    )


def is_test_double_class_name(class_name: str) -> bool:
    normalized = class_name.lower()
    return (
        normalized.startswith(
            (
                "fake",
                "stub",
                "spy",
                "inmemory",
                "sequenced",
                "fixed",
                "tracking",
                "recording",
                "failing",
                "broken",
            )
        )
        or normalized.endswith(("fake", "stub", "spy", "double", "helper"))
        or "fake" in normalized
        or "double" in normalized
        or "unavailable" in normalized
    )


def support_fakes_package_exists(path: Path) -> bool:
    return path.exists()


def is_non_source_integration_test(path: Path, *, test_root: Path) -> bool:
    relative = path.relative_to(test_root)
    return relative.parts[:1] == ("migrations",)


def required_unit_test_source_paths(context: ArchitectureContext) -> tuple[Path, ...]:
    core_root = context.src_root / "core"
    required_package_names = {"capabilities", "services", "use_cases"}
    return tuple(
        path
        for path in sorted(context.ast_project.files)
        if path.is_relative_to(core_root)
        and path.name != "__init__.py"
        and len((relative := path.relative_to(core_root)).parts) >= 3
        and relative.parts[1] in required_package_names
    )


def required_integration_test_source_paths(context: ArchitectureContext) -> tuple[Path, ...]:
    definition_index = class_definition_base_index(context)
    core_root = context.src_root / "core"
    return tuple(
        path
        for path in sorted(context.ast_project.files)
        if path.name != "__init__.py"
        and path.is_relative_to(core_root)
        and len((relative := path.relative_to(core_root)).parts) >= 3
        and relative.parts[1] == "use_cases"
        and _module_has_persistence_use_case(context, path, definition_index)
    )


def _module_has_persistence_use_case(
    context: ArchitectureContext,
    path: Path,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
) -> bool:
    tree = context.tree(path)
    aliases = context.aliases(path)
    return any(
        is_use_case_class_at(
            class_node,
            path=path,
            context=context,
            definition_index=definition_index,
        )
        and bool(class_injected_unit_of_work_manager_field_names(class_node, aliases))
        for class_node in ast.walk(tree)
        if isinstance(class_node, ast.ClassDef)
    )


def is_pytest_fixture(
    node: ast.AsyncFunctionDef | ast.FunctionDef,
    aliases: dict[str, str],
) -> bool:
    for decorator in node.decorator_list:
        expression = decorator.func if isinstance(decorator, ast.Call) else decorator
        if annotation_name(expression, aliases) == "fixture":
            return True
    return False


def fixture_returns_use_closure(node: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    inner_use_functions = {
        child.name
        for child in node.body
        if isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef))
        and child.name.startswith("use_")
    }
    if not inner_use_functions:
        return False
    return any(
        isinstance(child, ast.Return)
        and isinstance(child.value, ast.Name)
        and child.value.id in inner_use_functions
        for child in node.body
    )


def function_mocks_internal_app_collaborator(
    node: ast.AsyncFunctionDef | ast.FunctionDef,
    aliases: dict[str, str],
    imports: frozenset[str],
    package_name: str,
    factory_return_annotations: dict[str, str],
) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if _mock_call_uses_internal_app_collaborator_spec(
                child,
                aliases,
                imports,
                package_name,
            ):
                return True
            if _registration_call_targets_internal_app_collaborator(
                child,
                aliases,
                imports,
                package_name,
                factory_return_annotations,
            ):
                return True
            if _patch_call_targets_internal_app_collaborator(
                child,
                aliases,
                imports,
                package_name,
            ):
                return True
            if _monkeypatch_call_targets_internal_app_collaborator(
                child,
                aliases,
                imports,
                package_name,
            ):
                return True
    return False


def _mock_call_uses_internal_app_collaborator_spec(
    node: ast.Call,
    aliases: dict[str, str],
    imports: frozenset[str],
    package_name: str,
) -> bool:
    if not _is_mock_factory_call(node, aliases):
        return False
    spec_name = _mock_call_spec_name(node, aliases)
    return _is_internal_app_collaborator_name(
        spec_name,
        aliases=aliases,
        imports=imports,
        package_name=package_name,
    )


def _mock_call_spec_name(node: ast.Call, aliases: dict[str, str]) -> str:
    for keyword in node.keywords:
        if keyword.arg in {"spec", "spec_set"}:
            return _qualified_expression_name(keyword.value, aliases)
    if node.args:
        return _qualified_expression_name(node.args[0], aliases)
    return ""


def _registration_call_targets_internal_app_collaborator(
    node: ast.Call,
    aliases: dict[str, str],
    imports: frozenset[str],
    package_name: str,
    factory_return_annotations: dict[str, str],
) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in {"add", "add_factory", "add_instance", "override"}:
        return False
    provides = next((keyword.value for keyword in node.keywords if keyword.arg == "provides"), None)
    if _is_internal_app_collaborator_name(
        _qualified_expression_name(provides, aliases),
        aliases=aliases,
        imports=imports,
        package_name=package_name,
    ):
        return True
    if node.func.attr in {"add", "add_factory"} and node.args:
        registered_name = _qualified_expression_name(node.args[0], aliases)
        if _is_internal_app_collaborator_name(
            registered_name,
            aliases=aliases,
            imports=imports,
            package_name=package_name,
        ):
            return True
        if isinstance(node.args[0], ast.Name) and _is_internal_app_collaborator_name(
            factory_return_annotations.get(node.args[0].id, ""),
            aliases=aliases,
            imports=imports,
            package_name=package_name,
        ):
            return True
    if node.func.attr in {"add_instance", "override"} and node.args:
        instance = node.args[0]
        if isinstance(instance, ast.Call):
            return _is_internal_app_collaborator_name(
                _qualified_expression_name(instance.func, aliases),
                aliases=aliases,
                imports=imports,
                package_name=package_name,
            )
    return False


def _patch_call_targets_internal_app_collaborator(
    node: ast.Call,
    aliases: dict[str, str],
    imports: frozenset[str],
    package_name: str,
) -> bool:
    call_chain = tuple(aliases.get(segment, segment) for segment in attribute_chain(node.func))
    if not _is_patch_call_chain(call_chain):
        return False
    if _is_patch_object_call_chain(call_chain):
        if not node.args:
            return False
        return _object_attribute_target_names_internal_app_collaborator(
            target=node.args[0],
            attribute=node.args[1] if len(node.args) > 1 else None,
            aliases=aliases,
            imports=imports,
            package_name=package_name,
        )
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return False
    return _string_target_names_internal_app_collaborator(
        node.args[0].value,
        package_name=package_name,
    )


def _monkeypatch_call_targets_internal_app_collaborator(
    node: ast.Call,
    aliases: dict[str, str],
    imports: frozenset[str],
    package_name: str,
) -> bool:
    call_chain = tuple(aliases.get(segment, segment) for segment in attribute_chain(node.func))
    if call_chain[-1:] != ("setattr",) or not node.args:
        return False
    target = node.args[0]
    if isinstance(target, ast.Constant) and _string_target_names_internal_app_collaborator(
        target.value,
        package_name=package_name,
    ):
        return True
    return _object_attribute_target_names_internal_app_collaborator(
        target=target,
        attribute=node.args[1] if len(node.args) > 1 else None,
        aliases=aliases,
        imports=imports,
        package_name=package_name,
    )


def _object_attribute_target_names_internal_app_collaborator(
    *,
    target: ast.expr,
    attribute: ast.expr | None,
    aliases: dict[str, str],
    imports: frozenset[str],
    package_name: str,
) -> bool:
    target_name = _qualified_expression_name(target, aliases)
    if _is_internal_app_collaborator_name(
        target_name,
        aliases=aliases,
        imports=imports,
        package_name=package_name,
    ):
        return True
    return (
        isinstance(attribute, ast.Constant)
        and isinstance(attribute.value, str)
        and _name_looks_like_internal_app_collaborator(attribute.value)
        and _name_resolves_to_internal_core(
            target_name,
            aliases=aliases,
            imports=imports,
            package_name=package_name,
        )
    )


def _name_resolves_to_internal_core(
    name: str,
    *,
    aliases: dict[str, str],
    imports: frozenset[str],
    package_name: str,
) -> bool:
    name_chain = tuple(aliases.get(segment, segment) for segment in name.split("."))
    qualified_name = ".".join(name_chain)
    if qualified_name.startswith(f"{package_name}.core."):
        return True
    return any(
        imported.startswith(f"{package_name}.core.")
        and (imported == qualified_name or imported.endswith(f".{qualified_name}"))
        for imported in imports
    )


def _string_target_names_internal_app_collaborator(
    value: object,
    *,
    package_name: str,
) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(f"{package_name}.core.")
        and any(_name_looks_like_internal_app_collaborator(segment) for segment in value.split("."))
    )


def _is_internal_app_collaborator_name(
    name: str,
    *,
    aliases: dict[str, str],
    imports: frozenset[str],
    package_name: str,
) -> bool:
    if not _name_looks_like_internal_app_collaborator(name.rsplit(".", maxsplit=1)[-1]):
        return False
    name_chain = tuple(aliases.get(segment, segment) for segment in name.split("."))
    if len(name_chain) >= 2:
        root = name_chain[0]
        suffix = ".".join(name_chain[1:])
        qualified_name = ".".join(name_chain)
        if qualified_name.startswith(f"{package_name}.core."):
            return True
        return any(
            imported.startswith(f"{package_name}.core.")
            and imported.endswith((f".{root}", f".{suffix}"))
            for imported in imports
        )
    return any(
        imported.startswith(f"{package_name}.core.") and imported.endswith(f".{name}")
        for imported in imports
    )


def _name_looks_like_internal_app_collaborator(name: str) -> bool:
    return name.endswith(("Capability", "Service", "UseCase"))


def _is_patch_call_chain(call_chain: tuple[str, ...]) -> bool:
    return call_chain[-1:] == ("patch",) or _is_patch_object_call_chain(call_chain)


def _is_patch_object_call_chain(call_chain: tuple[str, ...]) -> bool:
    return call_chain[-2:] == ("patch", "object")


def local_function_return_annotations(
    tree: ast.Module,
    aliases: dict[str, str],
) -> dict[str, str]:
    return {
        node.name: annotation_name(node.returns, aliases)
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.returns is not None
    }


def _qualified_expression_name(
    expression: ast.expr | None,
    aliases: dict[str, str],
) -> str:
    chain = attribute_chain(expression)
    if chain:
        return ".".join(aliases.get(segment, segment) for segment in chain)
    return annotation_name(expression, aliases)


def explicit_import_modules(tree: ast.Module) -> tuple[str, ...]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return tuple(modules)


def fixture_bundles_mocks(
    node: ast.AsyncFunctionDef | ast.FunctionDef,
    aliases: dict[str, str],
) -> bool:
    mock_names = _fixture_mock_assignment_names(node, aliases)
    if _fixture_returns_mock_dict(node, aliases):
        return True
    if _returns_literal_with_multiple_mock_calls(node, aliases):
        return True
    if node.name.endswith("_mocks") and _function_mock_call_count(node, aliases) > 1:
        return True
    if len(mock_names) <= 1:
        return False
    if node.name.endswith("_mocks"):
        return True
    if _returns_dict_of_names(node, mock_names):
        return True
    return _container_add_instance_call_count(node) > 1


def _fixture_returns_mock_dict(
    node: ast.AsyncFunctionDef | ast.FunctionDef,
    aliases: dict[str, str],
) -> bool:
    return_annotation = annotation_name(node.returns, aliases)
    return return_annotation.startswith("dict[") and "Mock" in return_annotation


def _fixture_mock_assignment_names(
    node: ast.AsyncFunctionDef | ast.FunctionDef,
    aliases: dict[str, str],
) -> set[str]:
    mock_names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Assign) and _is_mock_factory_call(child.value, aliases):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    mock_names.add(target.id)
        elif (
            isinstance(child, ast.AnnAssign)
            and isinstance(child.target, ast.Name)
            and _is_mock_factory_call(child.value, aliases)
        ):
            mock_names.add(child.target.id)
    return mock_names


def _is_mock_factory_call(expression: ast.expr | None, aliases: dict[str, str]) -> bool:
    if not isinstance(expression, ast.Call):
        return False
    return annotation_name(expression.func, aliases) in {
        "AsyncMock",
        "MagicMock",
        "Mock",
        "create_autospec",
    }


def _returns_dict_of_names(
    node: ast.AsyncFunctionDef | ast.FunctionDef,
    names: set[str],
) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Return) or not isinstance(child.value, ast.Dict):
            continue
        if any(isinstance(value, ast.Name) and value.id in names for value in child.value.values):
            return True
    return False


def _returns_literal_with_multiple_mock_calls(
    node: ast.AsyncFunctionDef | ast.FunctionDef,
    aliases: dict[str, str],
) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Return):
            continue
        values = _literal_values(child.value)
        if sum(1 for value in values if _is_mock_factory_call(value, aliases)) > 1:
            return True
    return False


def _literal_values(expression: ast.expr | None) -> tuple[ast.expr | None, ...]:
    if isinstance(expression, ast.Dict):
        return tuple(expression.values)
    if isinstance(expression, (ast.List, ast.Set, ast.Tuple)):
        return tuple(expression.elts)
    return ()


def _function_mock_call_count(
    node: ast.AsyncFunctionDef | ast.FunctionDef,
    aliases: dict[str, str],
) -> int:
    return sum(
        1
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and _is_mock_factory_call(child, aliases)
    )


def _container_add_instance_call_count(node: ast.AsyncFunctionDef | ast.FunctionDef) -> int:
    return sum(
        1
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "add_instance"
    )
