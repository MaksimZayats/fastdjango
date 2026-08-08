from __future__ import annotations

import inspect
import json
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from diwire import Container
from pydantic import TypeAdapter, ValidationError
from pydantic_core import to_jsonable_python

from specx._internal.cli_config import LoadedSpecxConfig
from specx._internal.project_management.exceptions import SpecxProjectRuntimeError
from specx._internal.project_management.models import UseCaseDescriptor


def load_input_payload(value: str | None, *, stdin_text: str | None = None) -> dict[str, Any]:
    """Load one JSON object from inline text, a file reference, or stdin."""

    if value is None:
        return {}
    if value == "-":
        text = sys.stdin.read() if stdin_text is None else stdin_text
        source = "stdin"
    elif value.startswith("@"):
        path_value = value[1:]
        if not path_value:
            raise SpecxProjectRuntimeError(
                "input file reference must have the form @path.json",
                code="run.invalid-input-reference",
            )
        path = Path(path_value).expanduser()
        source = f"input file {path}"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            raise SpecxProjectRuntimeError(
                f"cannot read {source}: {error}",
                code="run.input-file-unreadable",
                hint="Relative @FILE paths are resolved from the current working directory.",
            ) from error
    else:
        text = value
        source = "inline input"
    if not text.strip():
        raise SpecxProjectRuntimeError(
            f"{source} is empty",
            code="run.empty-input",
            hint="Pass `{}` for a fieldless input object.",
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise SpecxProjectRuntimeError(
            f"invalid JSON in {source}: {error}",
            code="run.invalid-json",
            hint="Input must be one JSON object; pass `{}` for a fieldless input.",
        ) from error
    if not isinstance(payload, dict):
        raise SpecxProjectRuntimeError(
            f"{source} must contain a JSON object",
            code="run.input-not-object",
            hint="Wrap named fields in `{}` rather than passing an array or scalar.",
        )
    return cast(dict[str, Any], payload)


async def execute_use_case(
    *,
    loaded: LoadedSpecxConfig,
    descriptor: UseCaseDescriptor,
    payload: dict[str, Any],
    allow_effects: bool,
) -> dict[str, Any]:
    """Import, resolve, execute, and close one trusted project use case."""

    if descriptor.kind == "command" and not allow_effects:
        raise SpecxProjectRuntimeError(
            f"{descriptor.resource_id} is state-changing; rerun with --allow-effects",
            code="run.effects-not-allowed",
            hint=(
                "Review the command first, then rerun with `--allow-effects` only when "
                "the state change is intended."
            ),
        )
    allowed_fields = tuple(field.name for field in descriptor.input_fields)
    unknown_fields = tuple(sorted(set(payload) - set(allowed_fields)))
    if unknown_fields:
        allowed_text = ", ".join(allowed_fields) or "none (this input is fieldless)"
        raise SpecxProjectRuntimeError(
            f"unknown input field(s): {', '.join(unknown_fields)}; allowed fields: {allowed_text}",
            code="run.unknown-input-fields",
            hint=(
                "Inspect the contract with `specx project use-case show "
                f"{descriptor.resource_id} --output-format json`."
            ),
            available=allowed_fields,
            details={"unknown_fields": list(unknown_fields)},
        )
    root = loaded.architecture.project_root
    package_name = loaded.architecture.package_name
    factory_path = loaded.project.container_factory or f"{package_name}.ioc.container:get_container"
    with _project_import_context(root, package_name=package_name):
        use_case_type = _load_symbol(f"{descriptor.module_name}:{descriptor.class_name}")
        input_type = _load_symbol(f"{descriptor.module_name}:{descriptor.input_class_name}")
        factory = _load_symbol(factory_path)
        try:
            input_value = TypeAdapter(input_type).validate_python(payload)
        except (TypeError, ValidationError) as error:
            details: dict[str, Any] = {}
            if isinstance(error, ValidationError):
                details["issues"] = [
                    {
                        "path": ".".join(str(part) for part in issue["loc"]),
                        "code": issue["type"],
                        "message": issue["msg"],
                    }
                    for issue in error.errors(include_url=False)
                ]
            raise SpecxProjectRuntimeError(
                f"invalid {descriptor.kind} input: {error}",
                code="run.invalid-input",
                hint=(
                    "Inspect the contract with `specx project use-case show "
                    f"{descriptor.resource_id} --output-format json`."
                ),
                details=details,
            ) from error
        if not callable(factory):
            raise SpecxProjectRuntimeError(f"container factory {factory_path!r} is not callable")
        try:
            container = factory()
        except Exception as error:
            raise SpecxProjectRuntimeError(
                f"container factory {factory_path!r} failed: {type(error).__name__}: {error}"
            ) from error
        if not isinstance(container, Container):
            raise SpecxProjectRuntimeError(
                f"container factory {factory_path!r} must return diwire.Container"
            )
        error_info: tuple[type[BaseException] | None, BaseException | None, Any] = (
            None,
            None,
            None,
        )
        primary_error: BaseException | None = None
        result_payload: dict[str, Any] | None = None
        try:
            use_case = await container.aresolve(use_case_type)
            result = use_case.execute(**{descriptor.input_parameter_name: input_value})
            if inspect.isawaitable(result):
                result = await result
            json_result = to_jsonable_python(result)
            result_payload = {
                "version": 1,
                "use_case": descriptor.resource_id,
                "result": json_result,
            }
        except BaseException as error:
            error_info = (type(error), error, error.__traceback__)
            primary_error = error
        try:
            await container.aclose(*error_info)
        except Exception as cleanup_error:
            cleanup_message = f"{type(cleanup_error).__name__}: {cleanup_error}"
            if primary_error is None:
                raise SpecxProjectRuntimeError(
                    f"container cleanup failed: {cleanup_message}",
                    code="run.container-cleanup-failed",
                ) from cleanup_error
            if isinstance(primary_error, SpecxProjectRuntimeError):
                primary_error.details["cleanup_error"] = cleanup_message
            elif isinstance(primary_error, Exception):
                primary_error = SpecxProjectRuntimeError(
                    f"{descriptor.resource_id} failed: "
                    f"{type(primary_error).__name__}: {primary_error}",
                    code="run.execution-failed",
                    details={"cleanup_error": cleanup_message},
                )
            else:
                primary_error.add_note(f"container cleanup also failed: {cleanup_message}")
        if primary_error is not None:
            if isinstance(primary_error, SpecxProjectRuntimeError):
                raise primary_error
            if isinstance(primary_error, Exception):
                raise SpecxProjectRuntimeError(
                    f"{descriptor.resource_id} failed: "
                    f"{type(primary_error).__name__}: {primary_error}",
                    code="run.execution-failed",
                ) from primary_error
            raise primary_error
        if result_payload is None:
            raise SpecxProjectRuntimeError(
                f"{descriptor.resource_id} completed without a result envelope",
                code="run.missing-result",
            )
        return result_payload


def _load_symbol(import_path: str) -> Any:
    module_name, separator, symbol_name = import_path.partition(":")
    if not separator or not module_name or not symbol_name or ":" in symbol_name:
        raise SpecxProjectRuntimeError(
            f"invalid import path {import_path!r}; expected module:symbol"
        )
    try:
        module = import_module(module_name)
    except Exception as error:
        raise SpecxProjectRuntimeError(
            f"cannot import module {module_name!r}: {type(error).__name__}: {error}"
        ) from error
    try:
        return getattr(module, symbol_name)
    except AttributeError as error:
        raise SpecxProjectRuntimeError(
            f"module {module_name!r} does not define {symbol_name!r}"
        ) from error


@contextmanager
def _project_import_context(
    root: Path,
    *,
    package_name: str,
) -> Generator[None, None, None]:
    source_path = str(root / "src")
    added_path = source_path not in sys.path
    previous_directory = Path.cwd()
    module_prefix = f"{package_name}."
    previous_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == package_name or name.startswith(module_prefix)
    }
    for name in previous_modules:
        del sys.modules[name]
    if added_path:
        sys.path.insert(0, source_path)
    os.chdir(root)
    try:
        yield
    finally:
        os.chdir(previous_directory)
        for name in tuple(sys.modules):
            if name == package_name or name.startswith(module_prefix):
                del sys.modules[name]
        sys.modules.update(previous_modules)
        if added_path:
            sys.path.remove(source_path)
