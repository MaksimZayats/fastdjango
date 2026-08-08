from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from specx._internal.cli_config import load_specx_config
from specx._internal.project_management.exceptions import SpecxProjectRuntimeError
from specx._internal.project_management.models import UseCaseDescriptor
from specx._internal.project_management.runtime import execute_use_case
from specx.core.foundation.query import BaseQuery


@dataclass(frozen=True, kw_only=True, slots=True)
class FailingQuery(BaseQuery):
    """Test input for a failing managed use case."""


class FailingUseCase:
    """Test use case that records runtime cleanup behavior."""

    def execute(self, *, query: FailingQuery) -> object:
        """Raise the application error under test."""
        del query
        raise ValueError("broken application action")


class RecordingContainer:
    """One-off DIWire-shaped double that records close exception details."""

    def __init__(self) -> None:
        """Initialize the cleanup record."""
        self.closed_with: tuple[object, ...] | None = None

    async def aresolve(self, dependency: object) -> FailingUseCase:
        """Resolve the one failing use case."""
        del dependency
        return FailingUseCase()

    async def aclose(self, *error_info: object) -> None:
        """Record the exception details passed during cleanup."""
        self.closed_with = error_info


class SuccessfulUseCase:
    """Test use case that completes before cleanup fails."""

    def execute(self, *, query: FailingQuery) -> dict[str, bool]:
        """Return a JSON-compatible result."""
        del query
        return {"ok": True}


class CleanupFailingContainer:
    """DIWire-shaped double whose cleanup always fails."""

    def __init__(self, use_case: object | None = None) -> None:
        """Select the resolved use-case instance."""
        self.use_case = use_case or SuccessfulUseCase()

    async def aresolve(self, dependency: object) -> object:
        """Return the configured use case."""
        del dependency
        return self.use_case

    async def aclose(self, *error_info: object) -> None:
        """Raise the cleanup failure under test."""
        del error_info
        raise RuntimeError("cleanup broke")


def test_execute_use_case_closes_container_with_application_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project_config(tmp_path)
    loaded = load_specx_config(tmp_path)
    descriptor = UseCaseDescriptor(
        resource_id="tasks/fail",
        component="tasks",
        name="fail",
        module_name="demo_service.core.tasks.use_cases.fail",
        class_name="FailingUseCase",
        input_class_name="FailingQuery",
        input_parameter_name="query",
        kind="query",
        input_fields=(),
        result_class_name="FailureDTO",
        result_fields=(),
        dependencies=(),
        is_async=False,
        summary="Fail for a cleanup test.",
        path=tmp_path / "src" / "demo_service" / "core" / "tasks" / "use_cases" / "fail.py",
        line=1,
    )
    container = RecordingContainer()

    def load_symbol(import_path: str) -> Any:
        if import_path.endswith(":FailingUseCase"):
            return FailingUseCase
        if import_path.endswith(":FailingQuery"):
            return FailingQuery
        return lambda: container

    monkeypatch.setattr("specx._internal.project_management.runtime._load_symbol", load_symbol)
    monkeypatch.setattr(
        "specx._internal.project_management.runtime.Container",
        RecordingContainer,
    )

    with pytest.raises(SpecxProjectRuntimeError, match="ValueError: broken application action"):
        asyncio.run(
            execute_use_case(
                loaded=loaded,
                descriptor=descriptor,
                payload={},
                allow_effects=False,
            )
        )

    assert container.closed_with is not None
    assert container.closed_with[0] is ValueError
    assert isinstance(container.closed_with[1], ValueError)


def test_execute_use_case_wraps_cleanup_failure_and_preserves_primary_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project_config(tmp_path)
    loaded = load_specx_config(tmp_path)
    descriptor = _descriptor(tmp_path)

    def run_with(use_case: object) -> SpecxProjectRuntimeError:
        container = CleanupFailingContainer(use_case)

        def load_symbol(import_path: str) -> Any:
            if import_path.endswith(":FailingUseCase"):
                return type(use_case)
            if import_path.endswith(":FailingQuery"):
                return FailingQuery
            return lambda: container

        monkeypatch.setattr(
            "specx._internal.project_management.runtime._load_symbol",
            load_symbol,
        )
        monkeypatch.setattr(
            "specx._internal.project_management.runtime.Container",
            CleanupFailingContainer,
        )
        with pytest.raises(SpecxProjectRuntimeError) as raised:
            asyncio.run(
                execute_use_case(
                    loaded=loaded,
                    descriptor=descriptor,
                    payload={},
                    allow_effects=False,
                )
            )
        return raised.value

    cleanup_only = run_with(SuccessfulUseCase())
    assert cleanup_only.code == "run.container-cleanup-failed"
    assert "cleanup broke" in str(cleanup_only)

    primary = run_with(FailingUseCase())
    assert primary.code == "run.execution-failed"
    assert "broken application action" in str(primary)
    assert primary.details["cleanup_error"] == "RuntimeError: cleanup broke"


def _descriptor(tmp_path: Path) -> UseCaseDescriptor:
    return UseCaseDescriptor(
        resource_id="tasks/fail",
        component="tasks",
        name="fail",
        module_name="demo_service.core.tasks.use_cases.fail",
        class_name="FailingUseCase",
        input_class_name="FailingQuery",
        input_parameter_name="query",
        kind="query",
        input_fields=(),
        result_class_name="FailureDTO",
        result_fields=(),
        dependencies=(),
        is_async=False,
        summary="Fail for a cleanup test.",
        path=tmp_path / "src" / "demo_service" / "core" / "tasks" / "use_cases" / "fail.py",
        line=1,
    )


def _write_project_config(root: Path) -> None:
    package = root / "src" / "demo_service"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo-service"\nversion = "0.1.0"\n\n'
        '[tool.specx]\npackage = "demo_service"\n',
        encoding="utf-8",
    )
