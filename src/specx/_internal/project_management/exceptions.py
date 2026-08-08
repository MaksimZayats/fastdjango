from __future__ import annotations

from typing import Any

from specx._internal.exceptions import BaseSpecxError


class SpecxProjectError(BaseSpecxError):
    """Raised when project management cannot inspect or change a project safely."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "project.error",
        hint: str | None = None,
        available: tuple[str, ...] = (),
        suggestion: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Store stable metadata for human and machine-readable diagnostics."""

        super().__init__(message)
        self.code = code
        self.hint = hint
        self.available = available
        self.suggestion = suggestion
        self.details = details or {}


class SpecxProjectRuntimeError(SpecxProjectError):
    """Raised when a project use case cannot be executed safely."""
