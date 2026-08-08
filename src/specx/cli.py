from __future__ import annotations

import asyncio
import contextlib
import importlib.metadata
import json
import os
import sys
import tempfile
import tomllib
from collections.abc import Callable, Generator, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from inspect import getdoc
from pathlib import Path
from typing import Annotated, Any, TypeVar, cast

import typer
from rich.console import Console
from rich.table import Table

from specx._internal.cli_config import load_specx_config
from specx._internal.exceptions import BaseSpecxError
from specx._internal.project_init import initialize_project
from specx._internal.project_management.discovery import (
    discover_project,
    require_component,
    require_use_case,
)
from specx._internal.project_management.exceptions import SpecxProjectError
from specx._internal.project_management.models import ProjectDescriptor
from specx._internal.project_management.presentation import (
    component_payload,
    components_payload,
    print_component,
    print_components,
    print_use_case,
    print_use_cases,
    use_case_payload,
    use_cases_payload,
)
from specx._internal.project_management.runtime import execute_use_case, load_input_payload
from specx._internal.project_management.scaffold import scaffold_use_case
from specx.testing.architecture import (
    SpecxArchitectureReport,
    SpecxArchitectureViolation,
    SpecxArchitectureWarning,
    SpecxConfigurationError,
    check_specx_architecture,
)
from specx.testing.architecture.registry import SpecxRuleRegistry

T = TypeVar("T")


class OutputFormat(StrEnum):
    """Supported human and machine-readable output formats."""

    TEXT = "text"
    JSON = "json"


class UseCaseKindOption(StrEnum):
    """Supported generated use-case input kinds."""

    COMMAND = "command"
    QUERY = "query"


@dataclass(frozen=True, kw_only=True, slots=True)
class ProjectCommandContext:
    """Shared root for nested project commands."""

    root: Path
    error_format: OutputFormat


@dataclass(kw_only=True, slots=True)
class CapturedApplicationOutput:
    """Output emitted by trusted project code while a use case runs."""

    stdout: str = ""
    stderr: str = ""


def _complete_component(context: typer.Context, incomplete: str) -> list[tuple[str, str]]:
    return [
        (name, "core component")
        for name in _completion_resources(context)[0]
        if name.startswith(incomplete)
    ]


def _complete_use_case(context: typer.Context, incomplete: str) -> list[tuple[str, str]]:
    return [
        (resource_id, "managed use case")
        for resource_id in _completion_resources(context)[1]
        if resource_id.startswith(incomplete)
    ]


def _complete_create_use_case(context: typer.Context, incomplete: str) -> list[tuple[str, str]]:
    return [
        (f"{component}/", "create in component")
        for component in _completion_resources(context)[0]
        if f"{component}/".startswith(incomplete)
    ]


_HELP_CONTEXT = {"help_option_names": ["-h", "--help"]}


app: typer.Typer = typer.Typer(
    help="Build, inspect, run, and check structured Python application projects.",
    no_args_is_help=True,
    context_settings=_HELP_CONTEXT,
    pretty_exceptions_enable=False,
)
rule_app: typer.Typer = typer.Typer(
    help="Inspect built-in architecture rules.",
    no_args_is_help=True,
    context_settings=_HELP_CONTEXT,
)
project_app: typer.Typer = typer.Typer(
    help="Inspect, scaffold, and run components and use cases.",
    epilog=(
        "Examples: `specx project component list`; "
        "`specx project --root ../service use-case list --output-format json`."
    ),
    no_args_is_help=True,
    context_settings=_HELP_CONTEXT,
)
component_app: typer.Typer = typer.Typer(
    help="Inspect structural core components.",
    no_args_is_help=True,
    context_settings=_HELP_CONTEXT,
)
use_case_app: typer.Typer = typer.Typer(
    help="Inspect, scaffold, and run use cases.",
    no_args_is_help=True,
    context_settings=_HELP_CONTEXT,
)

app.add_typer(rule_app, name="rule")
app.add_typer(project_app, name="project")
project_app.add_typer(component_app, name="component")
project_app.add_typer(use_case_app, name="use-case")
project_app.add_typer(component_app, name="components", hidden=True)
project_app.add_typer(use_case_app, name="use-cases", hidden=True)


def _version_callback(value: bool) -> bool:
    if value:
        typer.echo(importlib.metadata.version("specx"))
        raise typer.Exit()
    return value


@app.callback()
def application_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the installed specx version and exit.",
            is_eager=True,
            callback=_version_callback,
        ),
    ] = False,
) -> None:
    """Handle application-wide options."""
    del version


@app.command("check")
def check_command(
    root: Annotated[
        Path | None,
        typer.Argument(help="Project root containing pyproject.toml."),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--output-format", help="Diagnostic output format."),
    ] = OutputFormat.TEXT,
) -> None:
    """Check a complete Python project."""

    project_root = root or Path.cwd()
    exit_code = _guard(
        lambda: _run_check(
            project_root=project_root,
            output_format=output_format.value,
        ),
        error_format=output_format,
        error_contract_version=2,
        command="check",
        root=project_root,
    )
    if exit_code:
        raise typer.Exit(exit_code)


@app.command("init")
def init_command(
    path: Annotated[
        Path | None,
        typer.Argument(help="New project directory."),
    ] = None,
    project_name: Annotated[
        str | None,
        typer.Option("--name", help="Distribution name."),
    ] = None,
    package_name: Annotated[
        str | None,
        typer.Option("--package", help="Lowercase Python import package."),
    ] = None,
    python_version: Annotated[
        str,
        typer.Option("--python", help="Python major.minor version."),
    ] = "3.14",
    no_sync: Annotated[
        bool,
        typer.Option("--no-sync", help="Write files without adding dependencies."),
    ] = False,
) -> None:
    """Initialize a new framework-neutral Python project."""

    _guard(
        lambda: _run_init(
            target=path or Path.cwd(),
            project_name=project_name,
            package_name=package_name,
            python_version=python_version,
            synchronize=not no_sync,
        )
    )


@rule_app.command("list")
def rule_list_command() -> None:
    """List built-in architecture rules."""

    _guard(_run_rule_list)


@rule_app.command("explain")
def rule_explain_command(
    rule_id: Annotated[str, typer.Argument(help="Exact semantic rule identifier.")],
) -> None:
    """Explain one built-in architecture rule."""

    _guard(lambda: _run_rule_explain(rule_id))


@project_app.callback()
def project_callback(
    context: typer.Context,
    root: Annotated[
        Path | None,
        typer.Option(
            "--root",
            "-r",
            metavar="PATH",
            help="Project root. Defaults to the nearest pyproject.toml ancestor.",
        ),
    ] = None,
    error_format: Annotated[
        OutputFormat,
        typer.Option(
            "--error-format",
            help="Render project/config/runtime errors as text or versioned JSON.",
        ),
    ] = OutputFormat.TEXT,
) -> None:
    """Resolve shared project-management options."""

    context.obj = ProjectCommandContext(
        root=_resolve_project_root(root),
        error_format=error_format,
    )


@component_app.command(
    "list",
    epilog=(
        "Examples: `specx project component list`; "
        "`specx project --root ../service component list --output-format json`."
    ),
)
def component_list_command(
    context: typer.Context,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--output-format", "-o", help="Text for humans or stable JSON for tools."),
    ] = OutputFormat.TEXT,
) -> None:
    """List structural core components and their use-case counts."""

    def action() -> None:
        _, project = discover_project(_project_root(context))
        if output_format is OutputFormat.JSON:
            _print_json(components_payload(project))
        else:
            print_components(_console(), project)

    _guard(
        action,
        error_format=_error_format(context, output_format),
        command="project.component.list",
        root=_project_root(context),
    )


@component_app.command(
    "show",
    epilog=(
        "Examples: `specx project component list`; "
        "`specx project component show playback --output-format json`."
    ),
)
def component_show_command(
    context: typer.Context,
    component: Annotated[
        str | None,
        typer.Argument(
            metavar="COMPONENT",
            help="Required component ID in lowercase kebab-case.",
            autocompletion=_complete_component,
        ),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--output-format", "-o", help="Text for humans or stable JSON for tools."),
    ] = OutputFormat.TEXT,
) -> None:
    """Show one component and its use cases."""

    def action() -> None:
        _, project = discover_project(_project_root(context))
        selected = require_component(project, _required_component(project, component))
        if output_format is OutputFormat.JSON:
            _print_json(component_payload(project, selected))
        else:
            print_component(_console(), project, selected)

    _guard(
        action,
        error_format=_error_format(context, output_format),
        command="project.component.show",
        root=_project_root(context),
    )


@use_case_app.command(
    "list",
    epilog=(
        "Examples: `specx project use-case list`; "
        "`specx project use-case list --component playback --output-format json`."
    ),
)
def use_case_list_command(
    context: typer.Context,
    component: Annotated[
        str | None,
        typer.Option(
            "--component",
            metavar="COMPONENT",
            help="Restrict results to one component.",
            autocompletion=_complete_component,
        ),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--output-format", "-o", help="Text for humans or stable JSON for tools."),
    ] = OutputFormat.TEXT,
) -> None:
    """List statically discovered project use cases."""

    def action() -> None:
        _, project = discover_project(_project_root(context))
        selected = project.use_cases
        if component is not None:
            found_component = require_component(project, component)
            selected = tuple(
                candidate
                for candidate in selected
                if candidate.resource_id in found_component.use_case_ids
            )
        if output_format is OutputFormat.JSON:
            _print_json(use_cases_payload(project, selected))
        else:
            print_use_cases(_console(), project, selected)

    _guard(
        action,
        error_format=_error_format(context, output_format),
        command="project.use-case.list",
        root=_project_root(context),
    )


@use_case_app.command(
    "show",
    epilog=(
        "Examples: `specx project use-case list`; `specx project use-case show "
        "playback/get-playback-status --output-format json`."
    ),
)
def use_case_show_command(
    context: typer.Context,
    resource_id: Annotated[
        str | None,
        typer.Argument(
            metavar="COMPONENT/NAME",
            help="Required use-case ID in lowercase kebab-case.",
            autocompletion=_complete_use_case,
        ),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--output-format", "-o", help="Text for humans or stable JSON for tools."),
    ] = OutputFormat.TEXT,
) -> None:
    """Show the static contract and dependencies of one use case."""

    def action() -> None:
        _, project = discover_project(_project_root(context))
        selected = require_use_case(
            project,
            _required_use_case(project, resource_id, action="show"),
        )
        if output_format is OutputFormat.JSON:
            _print_json(use_case_payload(project, selected))
        else:
            print_use_case(_console(), project, selected)

    _guard(
        action,
        error_format=_error_format(context, output_format),
        command="project.use-case.show",
        root=_project_root(context),
    )


@use_case_app.command(
    "create",
    epilog=(
        "Examples: `specx project use-case create orders/get-order --kind query --dry-run`; "
        "quote shell-sensitive fields: `--input-field 'note:str?' --result-field "
        "'track_ids:list\\[str]'`; add `--output-format json` for a deterministic manifest."
    ),
)
def use_case_create_command(
    context: typer.Context,
    resource_id: Annotated[
        str | None,
        typer.Argument(
            metavar="COMPONENT/NAME",
            help="Required new use-case ID in lowercase kebab-case.",
            autocompletion=_complete_create_use_case,
        ),
    ] = None,
    kind: Annotated[
        UseCaseKindOption | None,
        typer.Option("--kind", help="Required input kind: command or query."),
    ] = None,
    input_fields: Annotated[
        list[str] | None,
        typer.Option(
            "--input-field",
            metavar="NAME:TYPE",
            help="Repeatable input field; quote TYPE? and list[TYPE] in shells.",
        ),
    ] = None,
    result_fields: Annotated[
        list[str] | None,
        typer.Option(
            "--result-field",
            metavar="NAME:TYPE",
            help="Repeatable result field; types: str, int, float, bool, TYPE?, list[TYPE].",
        ),
    ] = None,
    synchronous: Annotated[
        bool,
        typer.Option("--sync", help="Generate sync execute; the default is async."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show files without writing them."),
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--output-format", "-o", help="Text for humans or stable JSON for tools."),
    ] = OutputFormat.TEXT,
) -> None:
    """Create one typed use-case contract, result DTO, and temporary test."""

    def action() -> None:
        root = _project_root(context).expanduser().resolve()
        resolved_resource_id, resolved_kind = _required_create_values(resource_id, kind)
        files = scaffold_use_case(
            root,
            resource_id=resolved_resource_id,
            kind=resolved_kind.value,
            input_field_values=tuple(input_fields or ()),
            result_field_values=tuple(result_fields or ()),
            synchronous=synchronous,
            dry_run=dry_run,
        )
        relative_files = [file.path.relative_to(root).as_posix() for file in files]
        next_commands = [
            ["specx", "project", "use-case", "show", resolved_resource_id],
            ["make", "check"],
        ]
        if output_format is OutputFormat.JSON:
            _print_json(
                {
                    "version": 1,
                    "operation": "use-case.create",
                    "root": str(root),
                    "use_case": resolved_resource_id,
                    "dry_run": dry_run,
                    "files": [{"path": path, "action": "create"} for path in relative_files],
                    "next_commands": next_commands,
                }
            )
            return
        verb = "Would create" if dry_run else "Created"
        table = Table(title=f"{verb} {len(files)} files for {resolved_resource_id}")
        table.add_column("File", style="cyan", overflow="fold")
        for path in relative_files:
            table.add_row(path)
        console = _console()
        console.print(f"Root: {root}", soft_wrap=True)
        console.print(table)
        if dry_run:
            console.print("No files written. Remove --dry-run to create this scaffold.")
        else:
            console.print(
                "Next: implement execute, replace the temporary test, then run `make check`."
            )

    _guard(
        action,
        error_format=_error_format(context, output_format),
        command="project.use-case.create",
        root=_project_root(context),
    )


@use_case_app.command(
    "run",
    epilog=(
        "Examples: `specx project use-case run playback/status`; "
        "`specx project use-case run playback/find --input @request.json`; "
        "`printf '%s' '{\"track_id\":\"123\"}' | specx project use-case run "
        "playback/find --input -`. Commands additionally require `--allow-effects`."
    ),
)
def use_case_run_command(
    context: typer.Context,
    resource_id: Annotated[
        str | None,
        typer.Argument(
            metavar="COMPONENT/NAME",
            help="Required use-case ID in lowercase kebab-case.",
            autocompletion=_complete_use_case,
        ),
    ] = None,
    input_payload: Annotated[
        str | None,
        typer.Option(
            "--input",
            "-i",
            metavar="JSON|@FILE|-",
            help="Input object as inline JSON, @UTF-8-file, or stdin (-). Defaults to {}.",
        ),
    ] = None,
    allow_effects: Annotated[
        bool,
        typer.Option(
            "--allow-effects",
            help="Acknowledge and allow state-changing command execution.",
        ),
    ] = False,
) -> None:
    """Resolve and execute one trusted project use case."""

    def action() -> None:
        loaded, project = discover_project(_project_root(context))
        selected = require_use_case(project, _required_use_case(project, resource_id, action="run"))
        payload = load_input_payload(input_payload)
        captured = CapturedApplicationOutput()
        try:
            with _capture_application_output(captured):
                result = asyncio.run(
                    execute_use_case(
                        loaded=loaded,
                        descriptor=selected,
                        payload=payload,
                        allow_effects=allow_effects,
                    )
                )
        except SpecxProjectError as error:
            _attach_captured_output(error, captured)
            raise
        _replay_captured_output(captured)
        _print_json(result)

    _guard(
        action,
        error_format=OutputFormat.JSON,
        command="project.use-case.run",
        root=_project_root(context),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the specx command-line interface and return a process exit code."""

    command = typer.main.get_command(app)
    try:
        command.main(
            args=list(argv) if argv is not None else None,
            prog_name="specx",
            standalone_mode=True,
        )
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 1
    return 0


def _guard(
    action: Callable[[], T],
    *,
    error_format: OutputFormat = OutputFormat.TEXT,
    error_contract_version: int = 1,
    command: str | None = None,
    root: Path | None = None,
) -> T:
    try:
        return action()
    except (BaseSpecxError, OSError, SyntaxError) as error:
        if error_format is OutputFormat.JSON:
            typer.echo(
                json.dumps(
                    _error_payload(
                        error,
                        command=command,
                        root=root,
                        version=error_contract_version,
                    ),
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                ),
                err=True,
            )
        else:
            _print_text_error(error)
        raise typer.Exit(2) from error


def _project_root(context: typer.Context) -> Path:
    command_context = context.find_object(ProjectCommandContext)
    if command_context is None:
        raise SpecxConfigurationError("project command context is missing")
    return command_context.root


def _console() -> Console:
    return Console(highlight=False)


def _print_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))


def _error_format(context: typer.Context, output_format: OutputFormat) -> OutputFormat:
    command_context = context.find_object(ProjectCommandContext)
    if output_format is OutputFormat.JSON:
        return OutputFormat.JSON
    if command_context is not None:
        return command_context.error_format
    return OutputFormat.TEXT


def _error_payload(
    error: BaseException,
    *,
    command: str | None,
    root: Path | None,
    version: int = 1,
) -> dict[str, Any]:
    if isinstance(error, SpecxProjectError):
        code = error.code
        hint = error.hint
        available = list(error.available)
        suggestions = [error.suggestion] if error.suggestion is not None else []
        details = error.details
    elif isinstance(error, OSError):
        code = "io.error"
        hint = None
        available = []
        suggestions = []
        details = {}
    elif isinstance(error, SyntaxError):
        code = "python.syntax-error"
        hint = None
        available = []
        suggestions = []
        details = {}
    else:
        code = "configuration.error"
        hint = None
        available = []
        suggestions = []
        details = {}
    return {
        "version": version,
        "command": command,
        "root": str(root.expanduser().resolve()) if root is not None else None,
        "exit_code": 2,
        "error": {
            "code": code,
            "message": str(error),
            "hint": hint,
            "available": available,
            "suggestions": suggestions,
            "details": details,
        },
    }


def _print_text_error(error: BaseException) -> None:
    typer.echo(f"specx error: {error}", err=True)
    if not isinstance(error, SpecxProjectError):
        return
    if error.suggestion is not None:
        typer.echo(f"Did you mean: {error.suggestion}", err=True)
    if error.available:
        typer.echo("Available:", err=True)
        for value in error.available[:10]:
            typer.echo(f"  {value}", err=True)
        if len(error.available) > 10:
            typer.echo(f"  ... and {len(error.available) - 10} more", err=True)
    if error.hint is not None:
        typer.echo(f"Hint: {error.hint}", err=True)


def _required_component(project: ProjectDescriptor, value: str | None) -> str:
    if value is not None:
        return value
    available = tuple(component.name for component in project.components)
    example = available[0] if available else "<component>"
    raise SpecxProjectError(
        "component is required",
        code="component.required",
        hint=(
            f"Try `specx project component show {example}` or list all components with "
            "`specx project component list`."
        ),
        available=available,
    )


def _required_use_case(
    project: ProjectDescriptor,
    value: str | None,
    *,
    action: str,
) -> str:
    if value is not None:
        return value
    available = tuple(use_case.resource_id for use_case in project.use_cases)
    example = available[0] if available else "<component>/<name>"
    raise SpecxProjectError(
        "use-case ID is required",
        code="use-case.required",
        hint=(
            f"Try `specx project use-case {action} {example}` or list all use cases with "
            "`specx project use-case list`."
        ),
        available=available,
    )


def _required_create_values(
    resource_id: str | None,
    kind: UseCaseKindOption | None,
) -> tuple[str, UseCaseKindOption]:
    missing: list[str] = []
    if resource_id is None:
        missing.append("COMPONENT/NAME")
    if kind is None:
        missing.append("--kind command|query")
    if missing:
        raise SpecxProjectError(
            f"missing required create value(s): {', '.join(missing)}",
            code="scaffold.missing-values",
            hint=(
                "Example: `specx project use-case create orders/get-order --kind query --dry-run`."
            ),
        )
    if resource_id is None or kind is None:
        raise AssertionError("create values were not narrowed")
    return resource_id, kind


def _resolve_project_root(explicit_root: Path | None) -> Path:
    if explicit_root is not None:
        return explicit_root.expanduser()
    candidate = Path.cwd().resolve()
    for directory in (candidate, *candidate.parents):
        if (directory / "pyproject.toml").is_file():
            return directory
    return candidate


def _completion_resources(context: typer.Context) -> tuple[tuple[str, ...], tuple[str, ...]]:
    command_context = context.find_object(ProjectCommandContext)
    root = command_context.root if command_context is not None else _resolve_project_root(None)
    try:
        document = cast(
            dict[str, object],
            tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")),
        )
        tool_value = document.get("tool", {})
        tool = cast(dict[str, object], tool_value) if isinstance(tool_value, dict) else {}
        specx_value = tool.get("specx", {})
        specx = cast(dict[str, object], specx_value) if isinstance(specx_value, dict) else {}
        configured = specx.get("package")
        src_root = root / "src"
        if isinstance(configured, str):
            package_name = configured
        else:
            candidates = tuple(
                path.name
                for path in sorted(src_root.iterdir() if src_root.is_dir() else ())
                if path.is_dir() and not path.name.startswith("_")
            )
            if len(candidates) != 1:
                return (), ()
            package_name = candidates[0]
        core_root = src_root / package_name / "core"
        component_paths = tuple(
            path
            for path in sorted(core_root.iterdir() if core_root.is_dir() else ())
            if path.is_dir() and path.name.isidentifier() and not path.name.startswith("_")
        )
        components = tuple(path.name.replace("_", "-") for path in component_paths)
        use_cases = tuple(
            f"{component_path.name.replace('_', '-')}/{path.stem.replace('_', '-')}"
            for component_path in component_paths
            for path in sorted((component_path / "use_cases").glob("*.py"))
            if path.name != "__init__.py"
        )
        return components, use_cases
    except (OSError, tomllib.TOMLDecodeError):
        return (), ()


@contextlib.contextmanager
def _capture_application_output(captured: CapturedApplicationOutput) -> Generator[None]:
    with (
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stdout,
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr,
    ):
        saved_stdout = os.dup(1)
        saved_stderr = os.dup(2)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(stdout.fileno(), 1)
            os.dup2(stderr.fileno(), 2)
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                yield
        finally:
            stdout.flush()
            stderr.flush()
            os.dup2(saved_stdout, 1)
            os.dup2(saved_stderr, 2)
            os.close(saved_stdout)
            os.close(saved_stderr)
            stdout.seek(0)
            stderr.seek(0)
            captured.stdout = stdout.read()
            captured.stderr = stderr.read()


def _attach_captured_output(
    error: SpecxProjectError,
    captured: CapturedApplicationOutput,
) -> None:
    if captured.stdout:
        error.details["captured_stdout"] = _bounded_output(captured.stdout)
    if captured.stderr:
        error.details["captured_stderr"] = _bounded_output(captured.stderr)


def _replay_captured_output(captured: CapturedApplicationOutput) -> None:
    for stream_name, value in (("stdout", captured.stdout), ("stderr", captured.stderr)):
        if value:
            typer.echo(f"[application {stream_name}]", err=True)
            typer.echo(_bounded_output(value).rstrip("\n"), err=True)


def _bounded_output(value: str, *, limit: int = 16_384) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}\n... application output truncated ...\n"


def _run_init(
    *,
    target: Path,
    project_name: str | None,
    package_name: str | None,
    python_version: str,
    synchronize: bool,
) -> int:
    initialized = initialize_project(
        target,
        project_name=project_name,
        package_name=package_name,
        python_version=python_version,
        synchronize=synchronize,
    )
    print(f"Initialized project {initialized.project_name!r} at {initialized.root}")
    print(f"Package: {initialized.package_name}")
    print(f"Python: {initialized.python_version}")
    if initialized.synchronized:
        print("Dependencies added with `uv add specx diwire` and `uv add --dev mypy pytest ruff`.")
        print(f"Next: run `make check` from {initialized.root}")
    else:
        print(f"Next: run `uv add specx diwire` from {initialized.root}.")
        print("Then run `uv add --dev mypy pytest ruff` and `make check`.")
    return 0


def _run_check(*, project_root: Path, output_format: str) -> int:
    loaded = load_specx_config(project_root)
    report = check_specx_architecture(loaded.architecture)

    if output_format == "json":
        print(_format_json(report))
    else:
        print(_format_text(report))
    return 1 if report.has_violations else 0


def _run_rule_list() -> int:
    registry = SpecxRuleRegistry.build()
    sorted_rules = sorted(
        registry.rules,
        key=lambda candidate: str(candidate.metadata().rule_id),
    )
    for rule_type in sorted_rules:
        metadata = rule_type.metadata()
        status = "default" if metadata.default_enabled else "opt-in"
        print(f"{metadata.rule_id} [{metadata.family}, {status}] {metadata.summary}")
    return 0


def _run_rule_explain(rule_id: str) -> int:
    registry = SpecxRuleRegistry.build()
    rule_type = next(
        (candidate for candidate in registry.rules if str(candidate.metadata().rule_id) == rule_id),
        None,
    )
    if rule_type is None:
        available = ", ".join(sorted(str(rule.metadata().rule_id) for rule in registry.rules))
        raise SpecxConfigurationError(f"unknown rule {rule_id!r}; available rules: {available}")

    metadata = rule_type.metadata()
    print(f"Rule: {metadata.rule_id}")
    print(f"Family: {metadata.family}")
    print(f"Enabled by default: {'yes' if metadata.default_enabled else 'no'}")
    if metadata.required_project_surface is not None:
        print(f"Required project surface: {metadata.required_project_surface}")
    if metadata.remediation is not None:
        print(f"Remediation: {metadata.remediation}")
    if metadata.documentation_url is not None:
        print(f"Documentation: {metadata.documentation_url}")
    print(f"Detection boundary: {metadata.detection_boundary}")
    print()
    print(getdoc(rule_type) or metadata.summary)
    return 0


def _format_text(report: SpecxArchitectureReport) -> str:
    lines = [
        _format_text_diagnostic(
            project_root=report.project_root,
            severity="warning",
            diagnostic=warning,
        )
        for warning in report.warnings
    ]
    lines.extend(
        _format_text_diagnostic(
            project_root=report.project_root,
            severity="error",
            diagnostic=violation,
        )
        for violation in report.violations
    )
    if report.has_violations:
        lines.append(
            f"Found {len(report.violations)} violation(s) and {len(report.warnings)} warning(s)."
        )
    else:
        lines.append(f"specx checks passed with {len(report.warnings)} warning(s).")
    return "\n".join(lines)


def _format_text_diagnostic(
    *,
    project_root: Path,
    severity: str,
    diagnostic: SpecxArchitectureViolation | SpecxArchitectureWarning,
) -> str:
    location = ""
    if diagnostic.path is not None:
        try:
            location = diagnostic.path.relative_to(project_root).as_posix()
        except ValueError:
            location = str(diagnostic.path)
    if diagnostic.line is not None:
        location = f"{location}:{diagnostic.line}"
        if diagnostic.column is not None:
            location = f"{location}:{diagnostic.column}"
    prefix = f"{location}: " if location else ""
    lines = [f"{prefix}{severity} {diagnostic.rule_id} {diagnostic.message}"]
    if diagnostic.hint is not None:
        lines.append(f"  help: {diagnostic.hint}")
    if diagnostic.documentation_url is not None:
        lines.append(f"  docs: {diagnostic.documentation_url}")
    return "\n".join(lines)


def _format_json(report: SpecxArchitectureReport) -> str:
    diagnostics = [
        _json_diagnostic(
            project_root=report.project_root,
            severity="warning",
            diagnostic=warning,
        )
        for warning in report.warnings
    ]
    diagnostics.extend(
        _json_diagnostic(
            project_root=report.project_root,
            severity="error",
            diagnostic=violation,
        )
        for violation in report.violations
    )
    payload = {
        "version": 2,
        "root": str(report.project_root),
        "diagnostics": diagnostics,
        "summary": {
            "errors": len(report.violations),
            "warnings": len(report.warnings),
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _json_diagnostic(
    *,
    project_root: Path,
    severity: str,
    diagnostic: SpecxArchitectureViolation | SpecxArchitectureWarning,
) -> dict[str, Any]:
    values = asdict(diagnostic)
    path = values.pop("path")
    values.pop("symbol", None)
    values["rule_id"] = str(values["rule_id"])
    values["severity"] = severity
    if path is None:
        values["path"] = None
    else:
        try:
            values["path"] = path.relative_to(project_root).as_posix()
        except ValueError:
            values["path"] = str(path)
    return values
