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
    class_hierarchy,
    class_method_declarations,
    function_behavior_nodes,
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
        runtime_settings_names = _project_subclasses_of(
            context,
            exact_bases={
                "pydantic_settings.BaseSettings",
                "specx.infrastructure.foundation.settings.BaseRuntimeSettings",
            },
        )
        project_pydantic_names = _project_subclasses_of(
            context,
            exact_bases={
                "pydantic.BaseModel",
                "pydantic.RootModel",
                "pydantic.root_model.RootModel",
            },
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
                or any(part in {"settings", "runtime_settings"} for part in module_parts(module))
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


def _project_subclasses_of(
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
    subclasses = {
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
    changed = True
    while changed:
        changed = False
        for qualified_name, (path, node) in classes.items():
            if qualified_name in subclasses:
                continue
            resolved_bases = {context.qualified_name(path, base) for base in node.bases}
            if resolved_bases & (exact_bases | subclasses):
                subclasses.add(qualified_name)
                changed = True
    changed = True
    while changed:
        changed = False
        for path in context.source_paths():
            module = ".".join(
                (
                    context.config.package_name,
                    *path.relative_to(context.src_root).with_suffix("").parts,
                )
            )
            for statement in context.tree(path).body:
                alias_name: str | None = None
                value: ast.expr | None = None
                type_alias_name = getattr(statement, "name", None)
                type_alias_value = getattr(statement, "value", None)
                if (
                    type(statement).__name__ == "TypeAlias"
                    and isinstance(type_alias_name, ast.Name)
                    and isinstance(type_alias_value, ast.expr)
                ):
                    alias_name, value = type_alias_name.id, type_alias_value
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
                if alias_name is None or value is None:
                    continue
                qualified_alias = f"{module}.{alias_name}"
                if qualified_alias in subclasses:
                    continue
                if context.qualified_name(path, value) in exact_bases | subclasses:
                    subclasses.add(qualified_alias)
                    changed = True
            for statement in context.tree(path).body:
                if not isinstance(statement, ast.ImportFrom):
                    continue
                for imported in statement.names:
                    if imported.name == "*":
                        continue
                    local_name = imported.asname or imported.name
                    reference = ast.copy_location(
                        ast.Name(id=local_name, ctx=ast.Load()),
                        statement,
                    )
                    if context.qualified_name(path, reference) not in exact_bases | subclasses:
                        continue
                    qualified_alias = f"{module}.{local_name}"
                    if qualified_alias not in subclasses:
                        subclasses.add(qualified_alias)
                        changed = True
    return subclasses


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
            seen_methods: set[str] = set()
            for owner_path, owner in class_hierarchy(node, path=path, context=context):
                for method_name, declarations in class_method_declarations(
                    owner,
                    path=owner_path,
                    context=context,
                ).items():
                    if method_name in seen_methods:
                        continue
                    seen_methods.add(method_name)
                    _method_path, method = declarations[-1]
                    node_ids.update(
                        id(descendant) for descendant in function_behavior_nodes(method)
                    )
    return node_ids
