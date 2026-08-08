from __future__ import annotations

import ast
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_has_foundation_base_at,
    class_is_statically_abstract,
    qualified_class_name,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    flat_test_path_for_source_path,
    violation,
)


class TestsCoreBehaviorResolvesFromContainerRule(ArchitectureRuleBase):
    """Require mirrored core-behavior tests to resolve every concrete target from DIWire."""

    id: SpecxRuleId = SpecxRuleId.TESTS_CORE_BEHAVIOR_RESOLVES_FROM_CONTAINER
    remediation: str | None = (
        "Add a test using the native `container` fixture and call "
        "`container.resolve(Target)` for every concrete behavior in the mirrored module."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        definition_index = class_definition_base_index(context)
        target_bases = {
            "BaseUseCase",
            "BaseCapability",
            "BasePureService",
            "BaseReadService",
            "BaseEffectService",
        }
        unit_root = context.project_root / "tests" / "unit"
        findings: list[SpecxArchitectureViolation] = []
        for source_path in context.source_paths():
            targets = [
                node
                for node in ast.walk(context.tree(source_path))
                if isinstance(node, ast.ClassDef)
                and not class_is_statically_abstract(node, context.aliases(source_path))
                and any(
                    class_has_foundation_base_at(
                        node,
                        base,
                        source_path=source_path,
                        context=context,
                        definition_index=definition_index,
                    )
                    for base in target_bases
                )
            ]
            if not targets:
                continue
            test_path = flat_test_path_for_source_path(
                source_path,
                test_root=unit_root,
                src_root=context.src_root,
            )
            test_tree = context.tree(test_path) if test_path in context.ast_project.files else None
            for target in targets:
                if test_tree is None or not _target_resolved_by_container(
                    test_tree,
                    qualified_class_name(
                        target,
                        source_path=source_path,
                        context=context,
                    ),
                    test_path=test_path,
                    context=context,
                ):
                    findings.append(
                        violation(
                            self.id,
                            path=test_path,
                            symbol=target.name,
                            message=(
                                f"mirrored unit test does not resolve {target.name} from container"
                            ),
                        )
                    )
        return tuple(findings)


def _target_resolved_by_container(
    tree: ast.Module,
    target_qualified_name: str,
    *,
    test_path: Path,
    context: ArchitectureContext,
) -> bool:
    for function in (
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ):
        arguments = (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)
        if not any(argument.arg == "container" for argument in arguments):
            continue
        for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
            if not (
                isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "container"
                and call.func.attr in {"resolve", "aresolve"}
                and call.args
            ):
                continue
            argument = call.args[0]
            if (
                isinstance(argument, (ast.Name, ast.Attribute))
                and context.qualified_name(test_path, argument) == target_qualified_name
            ):
                return True
    return False
