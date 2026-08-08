from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from specx.cli import main


def test_cli_help_lists_primary_commands(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--help"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "check" in output
    assert "init" in output
    assert "project" in output
    assert "rule" in output


def test_init_help_lists_project_options(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["init", "--help"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "--name" in output
    assert "--package" in output
    assert "--python" in output
    assert "--no-sync" in output


def test_cli_version_nested_short_help_and_project_metavars(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip()

    assert main(["project", "use-case", "create", "-h"]) == 0
    help_output = capsys.readouterr().out
    assert "COMPONENT/NAME" in help_output
    assert "NAME:TYPE" in help_output
    assert "note:str?" in help_output
    assert "track_ids:list[str]" in help_output
    assert "--output-format" in help_output


def test_init_creates_neutral_zero_config_project(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "Order Service"

    exit_code = main(["init", str(target), "--no-sync"])

    output = capsys.readouterr().out
    pyproject_text = (target / "pyproject.toml").read_text(encoding="utf-8")
    pyproject = tomllib.loads(pyproject_text)
    assert exit_code == 0
    assert "Initialized project 'order-service'" in output
    assert "Package: order_service" in output
    assert "Python: 3.14" in output
    assert "uv add specx diwire" in output
    assert pyproject["project"]["name"] == "order-service"
    assert pyproject["project"]["requires-python"] == ">=3.14"
    assert pyproject["project"]["dependencies"] == []
    assert "dependency-groups" not in pyproject
    assert pyproject["tool"]["uv"]["build-backend"]["module-name"] == "order_service"
    assert pyproject["tool"]["mypy"]["python_version"] == "3.14"
    assert pyproject["tool"]["ruff"]["target-version"] == "py314"
    assert pyproject["tool"]["ruff"]["lint"]["select"] == ["ALL"]
    assert "D100" in pyproject["tool"]["ruff"]["lint"]["ignore"]
    assert "CPY001" in pyproject["tool"]["ruff"]["lint"]["ignore"]
    assert "D203" in pyproject["tool"]["ruff"]["lint"]["ignore"]
    assert pyproject["tool"]["ruff"]["lint"]["per-file-ignores"]["**/__init__.py"] == ["D104"]
    assert pyproject["tool"]["specx"]["select"] == ["ALL"]
    makefile = (target / "Makefile").read_text(encoding="utf-8")
    assert "check: lint test" in makefile
    assert "\tuv run --locked specx check\n" in makefile
    assert "guardrails:" not in makefile
    assert "lock-check:" not in makefile
    assert "uv lock --check" not in makefile
    ignored_rules = set(pyproject["tool"]["ruff"]["lint"]["ignore"])
    for rules in pyproject["tool"]["ruff"]["lint"]["per-file-ignores"].values():
        ignored_rules.update(rules)
    commented_rules = {
        line.split('"', maxsplit=2)[1] for line in pyproject_text.splitlines() if '", # ' in line
    }
    assert ignored_rules <= commented_rules
    assert (target / ".python-version").read_text(encoding="utf-8") == "3.14\n"
    gitignore = (target / ".gitignore").read_text(encoding="utf-8")
    assert "__pycache__/" in gitignore
    assert "__pypackages__/" in gitignore
    assert ".ruff_cache/" in gitignore
    assert "test_db.sqlite3-journal" in gitignore
    assert ".local/" in gitignore
    assert (target / "src" / "order_service" / "__init__.py").read_text() == ""
    assert (target / "tests" / "__init__.py").read_text() == ""
    assert not (target / "tests" / "test_package.py").exists()
    assert "fastapi" not in (target / "AGENTS.md").read_text(encoding="utf-8").lower()
    assert (
        target
        / "src"
        / "order_service"
        / "core"
        / "health"
        / "services"
        / "health_status_service.py"
    ).is_file()
    health_service = (
        target
        / "src"
        / "order_service"
        / "core"
        / "health"
        / "services"
        / "health_status_service.py"
    )
    assert not health_service.read_text(encoding="utf-8").startswith('"""')
    assert (
        target / "src" / "order_service" / "core" / "health" / "use_cases" / "check_health.py"
    ).is_file()
    assert (target / "src" / "order_service" / "ioc" / "container.py").is_file()
    assert (
        target / "tests" / "unit" / "core" / "health" / "services" / "test_health_status_service.py"
    ).is_file()
    assert (
        target / "tests" / "unit" / "core" / "health" / "use_cases" / "test_check_health.py"
    ).is_file()
    unit_conftest = (target / "tests" / "unit" / "conftest.py").read_text(encoding="utf-8")
    assert "from order_service.ioc.container import get_container" in unit_conftest
    assert "return get_container()" in unit_conftest
    assert "MissingPolicy" not in unit_conftest
    assert "DependencyRegistrationPolicy" not in unit_conftest
    assert not (target / "src" / "order_service" / "delivery").exists()
    assert not (target / "src" / "order_service" / "infrastructure").exists()
    assert not (target / "src" / "order_service" / "foundation").exists()
    for initializer in target.rglob("__init__.py"):
        assert initializer.read_text(encoding="utf-8") == ""

    check_exit_code = main(["check", str(target)])

    assert check_exit_code == 0
    assert "specx checks passed with 0 warning(s)." in capsys.readouterr().out

    _assert_generated_ruff_passes(target)


def test_init_defaults_to_current_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "current-project"
    target.mkdir()
    monkeypatch.chdir(target)

    exit_code = main(["init", "--no-sync"])

    assert exit_code == 0
    assert (target / "src" / "current_project" / "__init__.py").is_file()
    assert str(target) in capsys.readouterr().out


def test_init_accepts_name_package_and_python_overrides(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "ignored-directory-name"

    exit_code = main(
        [
            "init",
            str(target),
            "--name",
            "Orders API.v2",
            "--package",
            "orders_api",
            "--python",
            "3.11",
            "--no-sync",
        ]
    )

    pyproject = tomllib.loads((target / "pyproject.toml").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert pyproject["project"]["name"] == "orders-api-v2"
    assert pyproject["project"]["requires-python"] == ">=3.11"
    assert pyproject["tool"]["mypy"]["python_version"] == "3.11"
    assert pyproject["tool"]["ruff"]["target-version"] == "py311"
    assert (target / ".python-version").read_text(encoding="utf-8") == "3.11\n"
    assert (target / "src" / "orders_api" / "__init__.py").is_file()
    assert "Package: orders_api" in capsys.readouterr().out


@pytest.mark.parametrize("python_version", ["3.10", "3.12", "3.13", "3.15", "4.0"])
def test_init_accepts_any_python_major_minor_version(
    tmp_path: Path,
    python_version: str,
) -> None:
    target = tmp_path / f"service-{python_version}"

    exit_code = main(["init", str(target), "--python", python_version, "--no-sync"])

    pyproject = tomllib.loads((target / "pyproject.toml").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert pyproject["project"]["requires-python"] == f">={python_version}"
    assert pyproject["tool"]["mypy"]["python_version"] == python_version
    assert pyproject["tool"]["ruff"]["target-version"] == f"py{python_version.replace('.', '')}"


@pytest.mark.parametrize(
    ("directory_name", "expected_package"),
    [
        ("123 service", "_123_service"),
        ("class", "class_package"),
        ("Mixed.Case_name", "mixed_case_name"),
    ],
)
def test_init_derives_safe_package_names(
    tmp_path: Path,
    directory_name: str,
    expected_package: str,
) -> None:
    target = tmp_path / directory_name

    assert main(["init", str(target), "--no-sync"]) == 0

    assert (target / "src" / expected_package / "__init__.py").is_file()
    _assert_generated_ruff_passes(target)


@pytest.mark.parametrize("python_version", ["3", "3.15.1", "3.x", "invalid"])
def test_init_rejects_malformed_python_without_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    python_version: str,
) -> None:
    target = tmp_path / "demo-service"

    exit_code = main(["init", str(target), "--python", python_version, "--no-sync"])

    assert exit_code == 2
    assert not target.exists()
    assert "invalid Python version" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("--name", "!!!"), "project name must contain"),
        (("--package", "Invalid-Package"), "package must be a lowercase ASCII"),
        (("--package", "class"), "package must be a lowercase ASCII"),
    ],
)
def test_init_rejects_invalid_names_without_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    arguments: tuple[str, str],
    message: str,
) -> None:
    target = tmp_path / "demo-service"

    exit_code = main(["init", str(target), *arguments, "--no-sync"])

    assert exit_code == 2
    assert not target.exists()
    assert message in capsys.readouterr().err


def test_init_accepts_empty_target_with_existing_git_directory(tmp_path: Path) -> None:
    target = tmp_path / "demo-service"
    git_directory = target / ".git"
    git_directory.mkdir(parents=True)

    exit_code = main(["init", str(target), "--no-sync"])

    assert exit_code == 0
    assert git_directory.is_dir()
    assert (target / ".gitignore").is_file()
    assert (target / "pyproject.toml").is_file()


def test_init_rejects_nonempty_target_without_overwriting(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "demo-service"
    existing_file = target / "README.md"
    _write(existing_file, "existing content\n")

    exit_code = main(["init", str(target), "--no-sync"])

    assert exit_code == 2
    assert existing_file.read_text(encoding="utf-8") == "existing content\n"
    assert not (target / "pyproject.toml").exists()
    assert "must be empty" in capsys.readouterr().err


def test_init_rejects_file_target_without_overwriting(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "demo-service"
    target.write_text("existing content\n", encoding="utf-8")

    exit_code = main(["init", str(target), "--no-sync"])

    assert exit_code == 2
    assert target.read_text(encoding="utf-8") == "existing content\n"
    assert "not a directory" in capsys.readouterr().err


def test_init_rejects_symlink_target_without_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_target = tmp_path / "real-target"
    real_target.mkdir()
    symlink_target = tmp_path / "linked-target"
    symlink_target.symlink_to(real_target, target_is_directory=True)

    exit_code = main(["init", str(symlink_target), "--no-sync"])

    assert exit_code == 2
    assert tuple(real_target.iterdir()) == ()
    assert "must not be a symlink" in capsys.readouterr().err


def test_init_adds_runtime_and_dev_dependencies_with_uv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "demo-service"
    calls: list[tuple[tuple[str, ...], Path, bool]] = []

    def fake_run(
        command: tuple[str, ...],
        *,
        cwd: Path,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, cwd, check))
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(
        "specx._internal.project_init.shutil.which",
        _find_uv,
    )
    monkeypatch.setattr("specx._internal.project_init.subprocess.run", fake_run)

    exit_code = main(["init", str(target)])

    assert exit_code == 0
    assert calls == [
        (("uv", "add", "specx", "diwire"), target.resolve(), True),
        (("uv", "add", "--dev", "mypy", "pytest", "ruff"), target.resolve(), True),
    ]
    assert "uv add --dev mypy pytest ruff" in capsys.readouterr().out


def test_init_requires_uv_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "demo-service"
    monkeypatch.setattr("specx._internal.project_init.shutil.which", _missing_uv)

    exit_code = main(["init", str(target)])

    assert exit_code == 2
    assert not target.exists()
    assert "uv is required" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("failure_index", "expected_command"),
    [
        (0, "uv add specx diwire"),
        (1, "uv add --dev mypy pytest ruff"),
    ],
)
def test_init_retains_scaffold_when_uv_add_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_index: int,
    expected_command: str,
) -> None:
    target = tmp_path / "demo-service"
    call_index = 0

    def fail_add(
        command: tuple[str, ...],
        *,
        cwd: Path,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal call_index
        current_index = call_index
        call_index += 1
        if current_index == failure_index:
            raise subprocess.CalledProcessError(returncode=7, cmd=command)
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(
        "specx._internal.project_init.shutil.which",
        _find_uv,
    )
    monkeypatch.setattr("specx._internal.project_init.subprocess.run", fail_add)

    exit_code = main(["init", str(target)])

    assert exit_code == 2
    assert (target / "pyproject.toml").is_file()
    error = capsys.readouterr().err
    assert f"{expected_command} failed" in error
    assert "failed with exit code 7" in error
    assert "project files remain" in error


def test_check_uses_zero_config_package_discovery(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_passing_project(tmp_path)

    exit_code = main(["check", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "specx checks passed with 0 warning(s)." in output


def test_check_reports_violation_location_and_exit_one(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_passing_project(
        tmp_path,
        tool_specx=(
            'ignore = ["tests.mirror-source-structure", '
            '"tests.core-behavior-resolves-from-container", '
            '"packages.init-files-are-empty"]'
        ),
    )
    _write(
        tmp_path / "src" / "demo_service" / "core" / "tasks" / "services" / "title_service.py",
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class TitleService(BasePureService):\n"
        "    pass\n",
    )

    exit_code = main(["check", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "title_service.py:3:1: error classes.require-example-docstrings" in output
    assert "  help:" in output
    assert "  docs: https://specx.dev/docs/reference/architecture-rules/" in output


def test_check_json_emits_versioned_machine_readable_diagnostics(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_passing_project(
        tmp_path,
        tool_specx=(
            'ignore = ["tests.mirror-source-structure", '
            '"tests.core-behavior-resolves-from-container", '
            '"packages.init-files-are-empty"]'
        ),
    )
    _write(
        tmp_path / "src" / "demo_service" / "core" / "tasks" / "services" / "title_service.py",
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class TitleService(BasePureService):\n"
        "    pass\n",
    )

    exit_code = main(["check", str(tmp_path), "--output-format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["version"] == 2
    assert payload["summary"] == {"errors": 1, "warnings": 0}
    assert payload["diagnostics"] == [
        {
            "column": 1,
            "line": 3,
            "message": "missing scoped Example docstring",
            "hint": (
                "Add a scoped class docstring with a concrete Example: section that "
                "contains real code or usage."
            ),
            "documentation_url": (
                "https://specx.dev/docs/reference/architecture-rules/"
                "#classes_require_example_docstrings"
            ),
            "path": "src/demo_service/core/tasks/services/title_service.py",
            "rule_id": "classes.require-example-docstrings",
            "severity": "error",
        }
    ]


def test_selected_fastapi_family_without_delivery_warns_and_passes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_passing_project(tmp_path, tool_specx='extend-select = ["fastapi"]')

    exit_code = main(["check", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "warning fastapi selected rule family requires Python files" in output
    assert "specx checks passed with 1 warning(s)." in output


@pytest.mark.parametrize(
    ("tool_specx", "message"),
    [
        ("unknown = true", "unknown [tool.specx] keys"),
        ('select = ["unknown-family"]', "unknown rule selectors"),
        ('extend-select = ["unknown-family"]', "unknown extended rule selectors"),
        ('ignore = ["unknown.rule"]', "unknown disabled rule selectors"),
    ],
)
def test_check_rejects_unknown_configuration(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    tool_specx: str,
    message: str,
) -> None:
    _write_passing_project(tmp_path, tool_specx=tool_specx)

    exit_code = main(["check", str(tmp_path)])

    error = capsys.readouterr().err
    assert exit_code == 2
    assert message in error


def test_check_json_emits_versioned_machine_readable_configuration_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_passing_project(tmp_path, tool_specx="unknown = true")

    exit_code = main(["check", str(tmp_path), "--output-format", "json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert exit_code == 2
    assert captured.out == ""
    assert payload == {
        "command": "check",
        "error": {
            "available": [],
            "code": "configuration.error",
            "details": {},
            "hint": None,
            "message": "unknown [tool.specx] keys: ['unknown']",
            "suggestions": [],
        },
        "exit_code": 2,
        "root": str(tmp_path.resolve()),
        "version": 2,
    }


def test_check_rejects_malformed_pyproject(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(tmp_path / "pyproject.toml", "[tool.specx\n")

    exit_code = main(["check", str(tmp_path)])

    assert exit_code == 2
    assert "invalid pyproject.toml" in capsys.readouterr().err


def test_check_loads_exact_call_policy_names(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_passing_project(
        tmp_path,
        tool_specx=(
            'select = []\n\n[tool.specx.call-policy]\nextend-allowed-functions = ["asyncio.gather"]'
        ),
    )

    exit_code = main(["check", str(tmp_path)])

    assert exit_code == 0
    assert "specx checks passed" in capsys.readouterr().out


def test_check_rejects_wildcard_call_policy_name(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_passing_project(
        tmp_path,
        tool_specx=(
            'select = []\n\n[tool.specx.call-policy]\nextend-allowed-functions = ["asyncio.*"]'
        ),
    )

    exit_code = main(["check", str(tmp_path)])

    assert exit_code == 2
    assert "exact dotted Python names" in capsys.readouterr().err


@pytest.mark.parametrize(
    "value",
    ['"asyncio.gather"', '["asyncio.gather", ""]'],
)
def test_check_reports_nested_path_for_invalid_call_policy_type_or_item(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    value: str,
) -> None:
    _write_passing_project(
        tmp_path,
        tool_specx=(f"[tool.specx.call-policy]\nextend-allowed-functions = {value}"),
    )

    exit_code = main(["check", str(tmp_path)])

    assert exit_code == 2
    assert (
        "tool.specx.call-policy.extend-allowed-functions must be an array of non-empty strings"
        in capsys.readouterr().err
    )


def test_check_requires_package_override_when_discovery_is_ambiguous(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_passing_project(tmp_path)
    _write(tmp_path / "src" / "second_service" / "__init__.py", "")

    exit_code = main(["check", str(tmp_path)])

    assert exit_code == 2
    assert "multiple importable packages" in capsys.readouterr().err


def test_check_accepts_explicit_package_override(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_passing_project(tmp_path, tool_specx='package = "demo_service"')
    _write(tmp_path / "src" / "second_service" / "__init__.py", "")

    exit_code = main(["check", str(tmp_path)])

    assert exit_code == 0
    assert "specx checks passed" in capsys.readouterr().out


def test_check_honors_excluded_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_passing_project(
        tmp_path,
        tool_specx='exclude = ["src/demo_service/generated/**"]',
    )
    _write(
        tmp_path / "src" / "demo_service" / "generated" / "bad.py",
        "class BareGeneratedClass:\n    pass\n",
    )

    exit_code = main(["check", str(tmp_path)])

    assert exit_code == 0
    assert "specx checks passed" in capsys.readouterr().out


def test_rule_list_and_explain_show_metadata(capsys: pytest.CaptureFixture[str]) -> None:
    list_exit_code = main(["rule", "list"])
    listed = capsys.readouterr().out
    explain_exit_code = main(["rule", "explain", "delivery.routes-use-full-api-v1-paths"])
    explained = capsys.readouterr().out

    assert list_exit_code == 0
    assert "delivery.routes-use-full-api-v1-paths [fastapi, opt-in]" in listed
    assert explain_exit_code == 0
    assert "Family: fastapi" in explained
    assert "Enabled by default: no" in explained
    assert "Required project surface: delivery/fastapi" in explained
    assert "Remediation:" in explained
    assert "Documentation: https://specx.dev/docs/reference/architecture-rules/" in explained
    assert "Detection boundary:" in explained


def test_rule_explain_rejects_unknown_rule(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["rule", "explain", "unknown.rule"])

    assert exit_code == 2
    assert "unknown rule" in capsys.readouterr().err


def _write_passing_project(project_root: Path, *, tool_specx: str = "") -> None:
    pyproject = '[project]\nname = "demo-service"\nversion = "0.1.0"\n'
    if tool_specx:
        pyproject = f"{pyproject}\n[tool.specx]\n{tool_specx}\n"
    _write(project_root / "pyproject.toml", pyproject)
    _write(project_root / "src" / "demo_service" / "__init__.py", "")
    _write(
        project_root / "AGENTS.md",
        "# Agent Instructions\n\n"
        "- Package lives under `src/demo_service`\n"
        "- make check\n"
        "- make lint\n"
        "- make test\n"
        "- uv run --locked specx check --output-format json\n"
        "- BasePureService\n"
        "- Runtime logging uses `LoggingConfigurator`.\n"
        "- Do not inject loggers.\n",
    )
    _write(project_root / "Makefile", "check:\n\nlint:\n\ntest:\n")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _assert_generated_ruff_passes(project_root: Path) -> None:
    ruff = str(Path(sys.executable).with_name("ruff"))
    commands = ((ruff, "check", "."), (ruff, "format", "--check", "."))
    for command in commands:
        result = subprocess.run(
            command,
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stdout + result.stderr


def _find_uv(command: str) -> str:
    return f"/usr/bin/{command}"


def _missing_uv(command: str) -> None:
    return None
