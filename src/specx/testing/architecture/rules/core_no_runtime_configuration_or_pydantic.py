from __future__ import annotations

import ast
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_has_foundation_base_at,
    module_parts,
    qualified_class_name,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._call_analysis import (
    ambient_environment_nodes,
    effective_class_method_declarations,
    function_behavior_nodes,
    reachable_behavior_functions,
    resolved_call_name,
)
from specx.testing.architecture.rules._shared import ArchitectureRuleBase, violation


class CoreNoRuntimeConfigurationOrPydanticRule(ArchitectureRuleBase):
    """Keep Pydantic and runtime configuration objects outside the project core layer."""

    id: SpecxRuleId = SpecxRuleId.CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC
    remediation: str | None = (
        "Move settings and Pydantic models to composition or delivery, then inject typed values "
        "or collaborators into core behavior."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        findings: list[SpecxArchitectureViolation] = []
        core_root = context.src_root / "core"
        definition_index = class_definition_base_index(context)
        runtime_settings_bases = {
            "pydantic_settings.BaseSettings",
            "specx.infrastructure.foundation.settings.BaseRuntimeSettings",
        }
        runtime_settings_names = {
            "specx.infrastructure.foundation.settings.BaseRuntimeSettings"
        } | _project_forbidden_type_names(context, exact_bases=runtime_settings_bases)
        pydantic_bases = {
            "pydantic.BaseModel",
            "pydantic.RootModel",
            "pydantic.root_model.RootModel",
        }
        project_pydantic_names = _project_forbidden_type_names(
            context,
            exact_bases=pydantic_bases,
            exact_decorators={"pydantic.dataclasses.dataclass"},
        )
        behavior_nodes = _behavior_method_node_ids(
            context=context,
            definition_index=definition_index,
        )
        for path in sorted(context.ast_project.files):
            if not path.is_relative_to(core_root):
                continue
            tree = context.tree(path)
            bad_imports = sorted(
                module
                for module in context.imports(path)
                if module_parts(module)[:1] in {("pydantic",), ("pydantic_settings",)}
            )
            bad_settings_references = sorted(
                _qualified_project_type_references(
                    tree,
                    path=path,
                    context=context,
                    qualified_types=runtime_settings_names,
                )
                | (
                    _imported_symbol_names(tree, path=path, context=context)
                    & runtime_settings_names
                )
            )
            bad_pydantic_references = sorted(
                _qualified_project_type_references(
                    tree,
                    path=path,
                    context=context,
                    qualified_types=project_pydantic_names,
                )
                | (
                    _imported_symbol_names(tree, path=path, context=context)
                    & project_pydantic_names
                )
            )
            if bad_imports:
                findings.append(
                    violation(
                        self.id,
                        path=path,
                        message=f"core imports runtime configuration or Pydantic: {bad_imports}",
                    )
                )
            if bad_settings_references:
                findings.append(
                    violation(
                        self.id,
                        path=path,
                        message=(
                            f"core depends on runtime settings types: {bad_settings_references}"
                        ),
                    )
                )
            if bad_pydantic_references:
                findings.append(
                    violation(
                        self.id,
                        path=path,
                        message=(
                            "core depends on project Pydantic model types: "
                            f"{bad_pydantic_references}"
                        ),
                    )
                )
            environment_calls = [
                call
                for call in ast.walk(tree)
                if isinstance(call, ast.Call)
                and (
                    resolved_call_name(call, path=path, context=context)
                    in {"os.getenv", "os.putenv", "os.unsetenv"}
                    or resolved_call_name(call, path=path, context=context).startswith(
                        "os.environ."
                    )
                )
            ]
            for call in environment_calls:
                if id(call) in behavior_nodes:
                    continue
                findings.append(
                    violation(
                        self.id,
                        path=path,
                        node=call,
                        message="core reads or mutates environment state directly",
                    )
                )
            for node in ambient_environment_nodes(tree, path=path, context=context):
                if id(node) in behavior_nodes or any(
                    node in ast.walk(call) for call in environment_calls
                ):
                    continue
                findings.append(
                    violation(
                        self.id,
                        path=path,
                        node=node,
                        message="core reads environment state directly",
                    )
                )
        return tuple(findings)


def _qualified_project_type_references(
    tree: ast.Module,
    *,
    path: Path,
    context: ArchitectureContext,
    qualified_types: set[str],
) -> set[str]:
    references = {
        qualified
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load)
        if (qualified := context.qualified_name(path, node)) in qualified_types
    }
    for annotation in (
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ):
        value = annotation.value
        if not isinstance(value, str):
            continue
        try:
            parsed = ast.parse(value, mode="eval")
        except SyntaxError:
            continue
        expression = parsed.body
        for node in ast.walk(expression):
            ast.copy_location(node, annotation)
            if not isinstance(node, (ast.Name, ast.Attribute)) or not isinstance(
                node.ctx, ast.Load
            ):
                continue
            qualified = context.qualified_name(path, node)
            if qualified in qualified_types:
                references.add(qualified)
    return references


def _project_forbidden_type_names(
    context: ArchitectureContext,
    *,
    exact_bases: set[str],
    exact_decorators: set[str] | None = None,
) -> set[str]:
    exact_decorators = exact_decorators or set()
    classes = {
        qualified_class_name(node, source_path=path, context=context): (
            path,
            node,
        )
        for path in context.source_paths()
        for node in context.tree(path).body
        if isinstance(node, ast.ClassDef)
    }
    forbidden_names = {
        qualified_name
        for qualified_name, (path, node) in classes.items()
        if any(
            context.qualified_name(
                path,
                decorator.func if isinstance(decorator, ast.Call) else decorator,
            )
            in exact_decorators
            for decorator in node.decorator_list
        )
    }
    aliases = tuple(
        alias
        for path in context.source_paths()
        for statement in context.tree(path).body
        if (alias := _project_alias(statement, path=path, context=context)) is not None
    )
    reexports = tuple(
        (
            path,
            f"{_source_module_name(path, context=context)}.{imported.asname or imported.name}",
            ast.copy_location(
                ast.Name(id=imported.asname or imported.name, ctx=ast.Load()),
                statement,
            ),
        )
        for path in context.source_paths()
        for statement in context.tree(path).body
        if isinstance(statement, ast.ImportFrom)
        for imported in statement.names
        if imported.name != "*"
    )
    changed = True
    while changed:
        changed = False
        qualified_types = exact_bases | forbidden_names
        for qualified_name, (path, node) in classes.items():
            if qualified_name in forbidden_names:
                continue
            resolved_bases = {context.qualified_name(path, base) for base in node.bases}
            if resolved_bases & qualified_types:
                forbidden_names.add(qualified_name)
                changed = True
        for path, qualified_alias, value, explicit_type_alias in aliases:
            if qualified_alias in forbidden_names:
                continue
            if _expression_contains_forbidden_type(
                value,
                path=path,
                context=context,
                qualified_types=qualified_types,
                parse_root_string=explicit_type_alias,
                resolve_forward_names=False,
                visited_quotes=frozenset(),
            ):
                forbidden_names.add(qualified_alias)
                changed = True
        for path, qualified_alias, reference in reexports:
            if qualified_alias in forbidden_names:
                continue
            if context.qualified_name(path, reference) in qualified_types:
                forbidden_names.add(qualified_alias)
                changed = True
    return forbidden_names


def _project_alias(
    statement: ast.stmt,
    *,
    path: Path,
    context: ArchitectureContext,
) -> tuple[Path, str, ast.expr, bool] | None:
    alias_name: str | None = None
    value: ast.expr | None = None
    explicit_type_alias = False
    type_alias_name = getattr(statement, "name", None)
    type_alias_value = getattr(statement, "value", None)
    if (
        type(statement).__name__ == "TypeAlias"
        and isinstance(type_alias_name, ast.Name)
        and isinstance(type_alias_value, ast.expr)
    ):
        alias_name, value, explicit_type_alias = type_alias_name.id, type_alias_value, True
    elif (
        isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
    ):
        alias_name, value = statement.targets[0].id, statement.value
    elif (
        isinstance(statement, ast.AnnAssign)
        and isinstance(statement.target, ast.Name)
        and statement.value is not None
    ):
        alias_name, value = statement.target.id, statement.value
        explicit_type_alias = context.qualified_name(path, statement.annotation) in {
            "typing.TypeAlias",
            "typing_extensions.TypeAlias",
        }
    if alias_name is None or value is None:
        return None
    return (
        path,
        f"{_source_module_name(path, context=context)}.{alias_name}",
        value,
        explicit_type_alias,
    )


def _source_module_name(path: Path, *, context: ArchitectureContext) -> str:
    return ".".join(
        (
            context.config.package_name,
            *path.relative_to(context.src_root).with_suffix("").parts,
        )
    )


def _expression_contains_forbidden_type(
    expression: ast.expr,
    *,
    path: Path,
    context: ArchitectureContext,
    qualified_types: set[str],
    parse_root_string: bool,
    resolve_forward_names: bool,
    visited_quotes: frozenset[str],
) -> bool:
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        if not parse_root_string or expression.value in visited_quotes:
            return False
        try:
            parsed = ast.parse(expression.value, mode="eval").body
        except SyntaxError:
            return False
        for node in ast.walk(parsed):
            ast.copy_location(node, expression)
        return _expression_contains_forbidden_type(
            parsed,
            path=path,
            context=context,
            qualified_types=qualified_types,
            parse_root_string=True,
            resolve_forward_names=True,
            visited_quotes=visited_quotes | {expression.value},
        )
    if isinstance(expression, ast.Subscript):
        root = context.qualified_name(path, expression.value)
        elements = expression.slice.elts if isinstance(expression.slice, ast.Tuple) else ()
        if root in {"typing.Annotated", "typing_extensions.Annotated"}:
            payload = elements[0] if elements else expression.slice
            return _expression_contains_forbidden_type(
                payload,
                path=path,
                context=context,
                qualified_types=qualified_types,
                parse_root_string=True,
                resolve_forward_names=resolve_forward_names,
                visited_quotes=visited_quotes,
            )
        if root in {"typing.Literal", "typing_extensions.Literal"}:
            return False
    if isinstance(expression, (ast.Name, ast.Attribute)) and isinstance(
        expression.ctx,
        ast.Load,
    ):
        candidates = {context.qualified_name(path, expression)}
        if resolve_forward_names and isinstance(expression, ast.Name):
            candidates.add(f"{_source_module_name(path, context=context)}.{expression.id}")
        if candidates & qualified_types:
            return True
    return any(
        _expression_contains_forbidden_type(
            child,
            path=path,
            context=context,
            qualified_types=qualified_types,
            parse_root_string=True,
            resolve_forward_names=resolve_forward_names,
            visited_quotes=visited_quotes,
        )
        for child in ast.iter_child_nodes(expression)
        if isinstance(child, ast.expr)
    )


def _imported_symbol_names(
    tree: ast.Module,
    *,
    path: Path,
    context: ArchitectureContext,
) -> set[str]:
    return {
        context.qualified_name(
            path,
            ast.Name(id=alias.asname or alias.name, ctx=ast.Load()),
        )
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name != "*"
    }


def _behavior_method_node_ids(
    *,
    context: ArchitectureContext,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
) -> set[int]:
    behavior_bases = {"BaseUseCase", "BasePureService", "BaseReadService", "BaseEffectService"}
    node_ids: set[int] = set()
    for path in context.source_paths():
        for node in (
            candidate
            for candidate in ast.walk(context.tree(path))
            if isinstance(candidate, ast.ClassDef)
        ):
            if not any(
                class_has_foundation_base_at(
                    node,
                    base,
                    source_path=path,
                    context=context,
                    definition_index=definition_index,
                )
                for base in behavior_bases
            ):
                continue
            for _method_name, declaration in effective_class_method_declarations(
                node,
                path=path,
                context=context,
            ):
                for _helper_path, helper in reachable_behavior_functions(
                    declaration.function,
                    path=declaration.path,
                    context=context,
                ):
                    node_ids.update(
                        id(descendant) for descendant in function_behavior_nodes(helper)
                    )
    return node_ids
