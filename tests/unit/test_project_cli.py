from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specx._internal.project_management.exceptions import SpecxProjectRuntimeError
from specx._internal.project_management.runtime import load_input_payload
from specx.cli import main


def test_project_lists_components_and_use_cases_as_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _initialize(tmp_path)
    _clear_capture(capsys)

    assert (
        main(
            [
                "project",
                "--root",
                str(project),
                "component",
                "list",
                "--output-format",
                "json",
            ]
        )
        == 0
    )
    component_payload = json.loads(_read_stdout(capsys))
    assert component_payload["version"] == 1
    assert component_payload["components"] == [{"name": "health", "use_case_count": 1}]

    assert (
        main(
            [
                "project",
                "--root",
                str(project),
                "use-case",
                "list",
                "--output-format",
                "json",
            ]
        )
        == 0
    )
    use_case_payload = json.loads(_read_stdout(capsys))
    assert use_case_payload["use_cases"][0]["id"] == "health/check-health"
    assert use_case_payload["use_cases"][0]["kind"] == "query"


def test_project_show_reports_static_contract_without_importing_project(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _initialize(tmp_path)
    duplicate = project / "src" / "demo_service" / "core" / "other" / "duplicate.py"
    duplicate.parent.mkdir(parents=True)
    duplicate.write_text("class HealthStatusDTO:\n    pass\n", encoding="utf-8")
    _clear_capture(capsys)

    exit_code = main(
        [
            "project",
            "--root",
            str(project),
            "use-case",
            "show",
            "health/check-health",
            "--output-format",
            "json",
        ]
    )

    payload = json.loads(_read_stdout(capsys))
    assert exit_code == 0
    assert payload["use_case"]["class"] == "CheckHealthUseCase"
    assert payload["use_case"]["input"] == {
        "class": "CheckHealthQuery",
        "example": {},
        "fields": [],
        "parameter": "query",
    }
    assert payload["use_case"]["execution"] == "sync"


def test_project_create_dry_run_does_not_write_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _initialize(tmp_path)
    _clear_capture(capsys)

    exit_code = main(
        [
            "project",
            "--root",
            str(project),
            "use-case",
            "create",
            "orders/create-order",
            "--kind",
            "command",
            "--input-field",
            "customer_id:str",
            "--result-field",
            "order_ids:list[int]",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert "create_order.py" in _read_stdout(capsys)
    assert not (project / "src" / "demo_service" / "core" / "orders").exists()


def test_project_create_writes_typed_async_scaffold_and_refuses_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _initialize(tmp_path)
    _clear_capture(capsys)
    arguments = [
        "project",
        "--root",
        str(project),
        "use-case",
        "create",
        "orders/create-order",
        "--kind",
        "command",
        "--input-field",
        "customer_id:str",
        "--input-field",
        "note:str?",
        "--result-field",
        "order_id:int",
    ]

    assert main(arguments) == 0
    source = (
        project / "src" / "demo_service" / "core" / "orders" / "use_cases" / "create_order.py"
    ).read_text(encoding="utf-8")
    assert "class CreateOrderCommand(BaseCommand):" in source
    assert "customer_id: str" in source
    assert "note: str | None = None" in source
    assert "async def execute" in source
    assert "raise NotImplementedError" in source
    assert main(arguments) == 2
    assert "refusing to overwrite" in _read_stderr(capsys)
    assert main(["check", str(project)]) == 0


def test_project_create_rejects_unsupported_field_types(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _initialize(tmp_path)
    _clear_capture(capsys)

    exit_code = main(
        [
            "project",
            "--root",
            str(project),
            "use-case",
            "create",
            "orders/create-order",
            "--kind",
            "command",
            "--input-field",
            "customer_id:UUID",
        ]
    )

    assert exit_code == 2
    assert "invalid field type" in _read_stderr(capsys)


@pytest.mark.parametrize(
    "resource_id",
    ["class/create-order", "orders/class", "órders/create-order", "orders/CreateOrder"],
)
def test_project_create_rejects_ids_that_are_not_safe_python_modules(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    resource_id: str,
) -> None:
    project = _initialize(tmp_path)
    _clear_capture(capsys)

    exit_code = main(
        [
            "project",
            "--root",
            str(project),
            "use-case",
            "create",
            resource_id,
            "--kind",
            "query",
        ]
    )

    assert exit_code == 2
    assert not (project / "src" / "demo_service" / "core" / "orders" / "use_cases").exists()


def test_project_run_executes_query_and_returns_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _initialize(tmp_path)
    _clear_capture(capsys)

    exit_code = main(
        [
            "project",
            "--root",
            str(project),
            "use-case",
            "run",
            "health/check-health",
        ]
    )

    payload = json.loads(_read_stdout(capsys))
    assert exit_code == 0
    assert payload == {
        "result": {"status": "ok"},
        "use_case": "health/check-health",
        "version": 1,
    }


def test_project_run_guards_command_effects(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _initialize(tmp_path)
    _clear_capture(capsys)
    assert (
        main(
            [
                "project",
                "--root",
                str(project),
                "use-case",
                "create",
                "orders/create-order",
                "--kind",
                "command",
            ]
        )
        == 0
    )
    _clear_capture(capsys)

    exit_code = main(
        [
            "project",
            "--root",
            str(project),
            "use-case",
            "run",
            "orders/create-order",
        ]
    )

    assert exit_code == 2
    assert "rerun with --allow-effects" in _read_stderr(capsys)

    source_path = (
        project / "src" / "demo_service" / "core" / "orders" / "use_cases" / "create_order.py"
    )
    source = source_path.read_text(encoding="utf-8").replace(
        'message = "Implement CreateOrderUseCase.execute"\n'
        "        raise NotImplementedError(message)",
        "return CreateOrderResultDTO()",
    )
    source_path.write_text(source, encoding="utf-8")
    _clear_capture(capsys)

    assert (
        main(
            [
                "project",
                "--root",
                str(project),
                "use-case",
                "run",
                "orders/create-order",
                "--allow-effects",
            ]
        )
        == 0
    )
    assert json.loads(_read_stdout(capsys))["result"] == {}


def test_project_runtime_config_accepts_factory_override_and_rejects_unknown_key(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _initialize(tmp_path)
    pyproject = project / "pyproject.toml"
    original = pyproject.read_text(encoding="utf-8")
    pyproject.write_text(
        original
        + "\n[tool.specx.project]\n"
        + 'container-factory = "demo_service.ioc.container:get_container"\n',
        encoding="utf-8",
    )
    _clear_capture(capsys)

    assert (
        main(
            [
                "project",
                "--root",
                str(project),
                "use-case",
                "run",
                "health/check-health",
            ]
        )
        == 0
    )
    assert json.loads(_read_stdout(capsys))["result"] == {"status": "ok"}

    pyproject.write_text(
        original + "\n[tool.specx.project]\nunknown = true\n",
        encoding="utf-8",
    )
    assert main(["project", "--root", str(project), "component", "list"]) == 2
    assert "unknown [tool.specx.project] keys" in _read_stderr(capsys)


def test_input_payload_supports_inline_file_and_stdin(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_text('{"value": 2}', encoding="utf-8")

    assert load_input_payload('{"value": 1}') == {"value": 1}
    assert load_input_payload(f"@{path}") == {"value": 2}
    assert load_input_payload("-", stdin_text='{"value": 3}') == {"value": 3}
    assert load_input_payload(None) == {}


def test_missing_and_misspelled_resources_have_contextual_recovery(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _initialize(tmp_path)
    _clear_capture(capsys)

    assert main(["project", "--root", str(project), "component", "show"]) == 2
    missing_error = _read_stderr(capsys)
    assert "component is required" in missing_error
    assert "health" in missing_error
    assert "specx project component show health" in missing_error

    assert (
        main(
            [
                "project",
                "--root",
                str(project),
                "use-case",
                "show",
                "health/chek-health",
                "--output-format",
                "json",
            ]
        )
        == 2
    )
    payload = json.loads(_read_stderr(capsys))
    assert payload["error"]["code"] == "use-case.not-found"
    assert payload["error"]["suggestions"] == ["health/check-health"]
    assert payload["error"]["available"] == ["health/check-health"]


def test_create_json_manifest_is_deterministic_and_rejects_private_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _initialize(tmp_path)
    _clear_capture(capsys)

    assert (
        main(
            [
                "project",
                "--root",
                str(project),
                "use-case",
                "create",
                "orders/get-order",
                "--kind",
                "query",
                "--dry-run",
                "--output-format",
                "json",
            ]
        )
        == 0
    )
    payload = json.loads(_read_stdout(capsys))
    assert payload["version"] == 1
    assert payload["operation"] == "use-case.create"
    assert payload["use_case"] == "orders/get-order"
    assert payload["dry_run"] is True
    assert payload["files"][-1] == {
        "path": "tests/unit/core/orders/use_cases/test_get_order.py",
        "action": "create",
    }
    assert payload["next_commands"][-1] == ["make", "check"]

    assert (
        main(
            [
                "project",
                "--root",
                str(project),
                "use-case",
                "create",
                "orders/get-order",
                "--kind",
                "query",
                "--input-field",
                "__dataclass_fields__:str",
                "--dry-run",
            ]
        )
        == 2
    )
    assert "private names are not supported" in _read_stderr(capsys)


def test_run_rejects_unknown_fields_and_keeps_application_output_out_of_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _initialize(tmp_path)
    source_path = (
        project / "src" / "demo_service" / "core" / "health" / "use_cases" / "check_health.py"
    )
    source_path.write_text(
        source_path.read_text(encoding="utf-8")
        .replace(
            "from dataclasses import dataclass\n",
            "import os\n\nfrom dataclasses import dataclass\n",
        )
        .replace(
            "        del query\n",
            '        print("application chatter")\n'
            '        os.write(1, b"fd chatter\\n")\n'
            "        del query\n",
        ),
        encoding="utf-8",
    )
    _clear_capture(capsys)

    assert (
        main(
            [
                "project",
                "--root",
                str(project),
                "use-case",
                "run",
                "health/check-health",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert json.loads(captured.out)["result"] == {"status": "ok"}
    assert "application chatter" in captured.err
    assert "fd chatter" in captured.err

    assert (
        main(
            [
                "project",
                "--root",
                str(project),
                "use-case",
                "run",
                "health/check-health",
                "--input",
                '{"typo": true}',
            ]
        )
        == 2
    )
    error_payload = json.loads(_read_stderr(capsys))
    assert error_payload["error"]["code"] == "run.unknown-input-fields"
    assert error_payload["error"]["details"]["unknown_fields"] == ["typo"]


def test_project_commands_find_root_from_a_nested_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _initialize(tmp_path)
    monkeypatch.chdir(project / "src" / "demo_service" / "core")
    _clear_capture(capsys)

    assert main(["project", "component", "list", "--output-format", "json"]) == 0
    assert json.loads(_read_stdout(capsys))["root"] == str(project.resolve())


def test_empty_project_text_explains_how_to_create_the_first_use_case(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _initialize(tmp_path)
    shutil.rmtree(project / "src" / "demo_service" / "core" / "health")
    _clear_capture(capsys)

    assert main(["project", "--root", str(project), "use-case", "list"]) == 0
    output = _read_stdout(capsys)
    assert f"Root: {project.resolve()}" in output
    assert "No use cases found" in output
    assert "use-case create" in output


def test_input_payload_errors_name_the_source_and_empty_object_recovery(tmp_path: Path) -> None:
    with pytest.raises(SpecxProjectRuntimeError, match=r"input file .*missing\.json"):
        load_input_payload(f"@{tmp_path / 'missing.json'}")
    with pytest.raises(SpecxProjectRuntimeError, match="stdin is empty"):
        load_input_payload("-", stdin_text="")


def test_generated_async_docstring_awaits_execute(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _initialize(tmp_path)
    _clear_capture(capsys)
    assert (
        main(
            [
                "project",
                "--root",
                str(project),
                "use-case",
                "create",
                "orders/get-order",
                "--kind",
                "query",
            ]
        )
        == 0
    )
    source = (
        project / "src" / "demo_service" / "core" / "orders" / "use_cases" / "get_order.py"
    ).read_text(encoding="utf-8")
    assert "result = await use_case.execute" in source


def test_scaffold_write_failure_rolls_back_new_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _initialize(tmp_path)
    _clear_capture(capsys)
    original_write_text = Path.write_text

    def failing_write_text(
        path: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if path.name == "get_order.py" and path.parent.name == "use_cases":
            raise OSError("disk full")
        return original_write_text(
            path,
            data,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    assert (
        main(
            [
                "project",
                "--root",
                str(project),
                "use-case",
                "create",
                "orders/get-order",
                "--kind",
                "query",
            ]
        )
        == 2
    )
    assert "could not write scaffold atomically" in _read_stderr(capsys)
    assert not (project / "src" / "demo_service" / "core" / "orders").exists()
    assert not (project / "tests" / "unit" / "core" / "orders").exists()


def _initialize(tmp_path: Path) -> Path:
    project = tmp_path / "demo-service"
    assert main(["init", str(project), "--no-sync"]) == 0
    return project


def _clear_capture(capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()


def _read_stdout(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out


def _read_stderr(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().err
