from __future__ import annotations

import keyword
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from specx.testing.architecture.models import SpecxArchitectureConfig, SpecxConfigurationError

_ALLOWED_CONFIG_KEYS = frozenset(
    {"exclude", "extend-select", "ignore", "package", "project", "select"}
)
_ALLOWED_PROJECT_CONFIG_KEYS = frozenset({"container-factory"})


@dataclass(frozen=True, kw_only=True, slots=True)
class LoadedProjectConfig:
    """Resolved project-management configuration."""

    container_factory: str | None


@dataclass(frozen=True, kw_only=True, slots=True)
class LoadedSpecxConfig:
    """Resolved CLI configuration for one project root."""

    architecture: SpecxArchitectureConfig
    project: LoadedProjectConfig
    pyproject_path: Path


def load_specx_config(project_root: Path) -> LoadedSpecxConfig:
    """Load optional specx settings from the project's required pyproject file."""

    root = project_root.expanduser().resolve()
    if not root.is_dir():
        raise SpecxConfigurationError(f"project root is not a directory: {root}")

    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.is_file():
        raise SpecxConfigurationError(f"pyproject.toml is missing under project root: {root}")

    try:
        document = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise SpecxConfigurationError(f"invalid pyproject.toml: {error}") from error

    raw_config = _read_tool_specx(cast(dict[str, object], document))
    unknown_keys = set(raw_config) - _ALLOWED_CONFIG_KEYS
    if unknown_keys:
        raise SpecxConfigurationError(f"unknown [tool.specx] keys: {sorted(unknown_keys)}")

    package_name = _read_optional_string(raw_config, "package") or _discover_package(root)
    select = frozenset(_read_string_list(raw_config, "select")) if "select" in raw_config else None
    extend_select = frozenset(_read_string_list(raw_config, "extend-select"))
    ignored_rules = frozenset(_read_string_list(raw_config, "ignore"))
    path_exclusions = tuple(_read_string_list(raw_config, "exclude"))
    project_config = _read_project_config(raw_config)

    return LoadedSpecxConfig(
        architecture=SpecxArchitectureConfig(
            project_root=root,
            package_name=package_name,
            select=select,
            extend_select=extend_select,
            disabled_rules=ignored_rules,
            path_exclusions=path_exclusions,
        ),
        project=project_config,
        pyproject_path=pyproject_path,
    )


def _read_project_config(config: dict[str, object]) -> LoadedProjectConfig:
    raw_value = config.get("project", {})
    if not isinstance(raw_value, dict):
        raise SpecxConfigurationError("tool.specx.project must be a TOML table")
    raw_project = cast(dict[str, object], raw_value)
    unknown_keys = set(raw_project) - _ALLOWED_PROJECT_CONFIG_KEYS
    if unknown_keys:
        raise SpecxConfigurationError(f"unknown [tool.specx.project] keys: {sorted(unknown_keys)}")
    return LoadedProjectConfig(
        container_factory=_read_optional_string(raw_project, "container-factory")
    )


def _read_tool_specx(document: dict[str, object]) -> dict[str, object]:
    tool_value = document.get("tool", {})
    if not isinstance(tool_value, dict):
        raise SpecxConfigurationError("[tool] must be a TOML table")
    tool = cast(dict[str, object], tool_value)

    raw_config_value = tool.get("specx", {})
    if not isinstance(raw_config_value, dict):
        raise SpecxConfigurationError("[tool.specx] must be a TOML table")
    return cast(dict[str, object], raw_config_value)


def _read_optional_string(config: dict[str, object], key: str) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise SpecxConfigurationError(f"tool.specx.{key} must be a non-empty string")
    return value


def _read_string_list(config: dict[str, object], key: str) -> tuple[str, ...]:
    value = config.get(key, [])
    if not isinstance(value, list):
        raise SpecxConfigurationError(f"tool.specx.{key} must be an array of non-empty strings")
    items = cast(list[object], value)
    if any(not isinstance(item, str) or not item for item in items):
        raise SpecxConfigurationError(f"tool.specx.{key} must be an array of non-empty strings")
    return tuple(cast(str, item) for item in items)


def _discover_package(project_root: Path) -> str:
    src_root = project_root / "src"
    if not src_root.is_dir():
        raise SpecxConfigurationError("cannot discover package because src/ is missing")

    candidates = tuple(
        path.name
        for path in sorted(src_root.iterdir())
        if path.is_dir()
        and path.name.isidentifier()
        and not keyword.iskeyword(path.name)
        and any(path.rglob("*.py"))
    )
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise SpecxConfigurationError(
            "cannot discover an importable package under src/; configure tool.specx.package"
        )
    raise SpecxConfigurationError(
        f"multiple importable packages found under src/: {list(candidates)}; "
        "configure tool.specx.package"
    )
