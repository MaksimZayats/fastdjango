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
        runtime_settings_names = {
            qualified_class_name(node, source_path=path, context=context)
            for path in context.source_paths()
            for node in ast.walk(context.tree(path))
            if isinstance(node, ast.ClassDef)
            and class_has_foundation_base_at(
                node,
                "BaseRuntimeSettings",
                source_path=path,
                context=context,
                definition_index=definition_index,
            )
        }
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
                {
                    context.qualified_name(path, annotation)
                    for annotation in _annotation_expressions(tree)
                    if context.qualified_name(path, annotation) in runtime_settings_names
                    or context.qualified_name(path, annotation).endswith(".BaseRuntimeSettings")
                }
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
            behavior_nodes = _behavior_method_node_ids(
                tree,
                path=path,
                context=context,
                definition_index=definition_index,
            )
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


def _annotation_expressions(tree: ast.Module) -> tuple[ast.expr, ...]:
    expressions: list[ast.expr] = []
    for node in ast.walk(tree):
        annotation = node.annotation if isinstance(node, (ast.arg, ast.AnnAssign)) else None
        if annotation is not None:
            expressions.append(annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            expressions.append(node.returns)
        elif isinstance(node, ast.ClassDef):
            expressions.extend(node.bases)
    return tuple(expressions)


def _behavior_method_node_ids(
    tree: ast.Module,
    *,
    path: Path,
    context: ArchitectureContext,
    definition_index: dict[str, tuple[tuple[Path, set[str]], ...]],
) -> set[int]:
    behavior_bases = {"BaseUseCase", "BasePureService", "BaseReadService", "BaseEffectService"}
    return {
        id(descendant)
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(
            class_has_foundation_base_at(
                node,
                base,
                source_path=path,
                context=context,
                definition_index=definition_index,
            )
            for base in behavior_bases
        )
        for method in node.body
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        for descendant in ast.walk(method)
    }
