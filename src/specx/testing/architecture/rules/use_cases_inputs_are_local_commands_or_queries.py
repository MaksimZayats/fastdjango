from __future__ import annotations

import ast

from specx.testing.architecture.context import (
    USE_CASE_INPUT_ARGUMENTS,
    USE_CASE_INPUT_BASE_NAMES,
    ArchitectureContext,
    annotation_name,
    class_definition_base_index,
    class_direct_base_names,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import (
    ArchitectureRuleBase,
    is_use_case_class_at,
    violation,
)


class UseCaseInputsAreLocalCommandsOrQueriesRule(ArchitectureRuleBase):
    """Require every use case to accept one same-file command or query input.

    A single local input object makes use-case contracts reviewable, typed, and
    easy for agents to evolve without leaking delivery schemas into core code.
    """

    id: SpecxRuleId = SpecxRuleId.USE_CASE_INPUTS_ARE_LOCAL_COMMANDS_OR_QUERIES

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        violations: list[SpecxArchitectureViolation] = []
        definition_index = class_definition_base_index(context)
        for path in (context.src_root / "core").glob("*/use_cases/**/*.py"):
            if path.name == "__init__.py" or path not in context.ast_project.files:
                continue
            tree = context.tree(path)
            aliases = context.aliases(path)
            local_inputs: dict[str, str] = {}
            use_cases: list[ast.ClassDef] = []
            consumed_inputs: set[str] = set()
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                base_names = class_direct_base_names(node, aliases)
                input_base = next(
                    (
                        found_base
                        for found_base in base_names
                        if found_base in USE_CASE_INPUT_BASE_NAMES
                    ),
                    None,
                )
                if input_base is not None:
                    local_inputs[node.name] = input_base
                if is_use_case_class_at(
                    node,
                    path=path,
                    context=context,
                    definition_index=definition_index,
                ):
                    use_cases.append(node)

            for use_case in use_cases:
                execute_methods = [
                    node
                    for node in use_case.body
                    if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
                    and node.name == "execute"
                ]
                if len(execute_methods) != 1:
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message="missing one execute method",
                            symbol=use_case.name,
                        )
                    )
                    continue
                execute = execute_methods[0]
                args = execute.args
                if (
                    len(args.args) != 1
                    or args.args[0].arg != "self"
                    or args.vararg is not None
                    or args.kwarg is not None
                    or len(args.kwonlyargs) != 1
                    or args.kw_defaults != [None]
                ):
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message="execute must accept one keyword-only input",
                            symbol=use_case.name,
                        )
                    )
                    continue
                input_arg = args.kwonlyargs[0]
                input_name = input_arg.arg
                input_annotation = annotation_name(input_arg.annotation, aliases)
                input_base = local_inputs.get(input_annotation)
                if input_name not in USE_CASE_INPUT_ARGUMENTS or input_base is None:
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message="execute input is not a local command/query",
                            symbol=use_case.name,
                        )
                    )
                    continue
                consumed_inputs.add(input_annotation)
                if input_name == "command" and input_base != "BaseCommand":
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message="command input does not inherit BaseCommand",
                            symbol=use_case.name,
                        )
                    )
                if input_name == "query" and input_base != "BaseQuery":
                    violations.append(
                        violation(
                            self.id,
                            path=path,
                            message="query input does not inherit BaseQuery",
                            symbol=use_case.name,
                        )
                    )

            for input_class_name in sorted(set(local_inputs) - consumed_inputs):
                violations.append(
                    violation(
                        self.id, path=path, message="local input is unused", symbol=input_class_name
                    )
                )
        return tuple(violations)
