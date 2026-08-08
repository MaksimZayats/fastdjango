from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HUMAN_FACING_ROOT_FILES = (
    PROJECT_ROOT / "AGENTS.md",
    PROJECT_ROOT / "CONTRIBUTING.md",
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "THIRD_PARTY_NOTICES.md",
    PROJECT_ROOT / "pyproject.toml",
)
HUMAN_FACING_DIRECTORIES = (
    PROJECT_ROOT / ".agents" / "skills",
    PROJECT_ROOT / ".github",
    PROJECT_ROOT / "docs",
    PROJECT_ROOT / "examples",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "skills",
    PROJECT_ROOT / "src",
)
IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "dist",
        "node_modules",
        "storybook-static",
    }
)
IGNORED_FILE_NAMES = frozenset({"package-lock.json"})
DOCUMENTATION_ROOT_NAMES = frozenset({".agents", "docs", "examples", "skills"})
DOCUMENTATION_ROOT_FILE_NAMES = frozenset({"AGENTS.md", "CONTRIBUTING.md", "README.md"})


def _human_facing_texts() -> Iterator[tuple[Path, str]]:
    candidates = [*HUMAN_FACING_ROOT_FILES]
    for root in HUMAN_FACING_DIRECTORIES:
        candidates.extend(root.rglob("*"))

    for path in candidates:
        relative_path = path.relative_to(PROJECT_ROOT)
        if (
            not path.is_file()
            or path.name in IGNORED_FILE_NAMES
            or IGNORED_DIRECTORY_NAMES.intersection(relative_path.parts)
        ):
            continue
        try:
            yield relative_path, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


def _is_documentation_path(path: Path) -> bool:
    return (
        path.name in DOCUMENTATION_ROOT_FILE_NAMES
        or path.parts[0] in DOCUMENTATION_ROOT_NAMES
        or "templates" in path.parts
    )


def test_repository_uses_lowercase_product_branding() -> None:
    product_name_pattern = re.compile(r"\bspecx\b", re.IGNORECASE)

    violations = [
        f"{path}: product name uses {match.group()!r}"
        for path, contents in _human_facing_texts()
        for match in product_name_pattern.finditer(contents)
        if match.group() != "specx"
    ]

    assert violations == []


def test_documentation_omits_retired_product_messaging() -> None:
    alpha = "alpha"
    retired_status_pattern = re.compile(
        rf"{alpha} software|{alpha}-stage|{alpha} namespace|"
        rf"Development Status :: 3 - {alpha.title()}",
        re.IGNORECASE,
    )
    retired_topic_pattern = re.compile(rf"\b{'limitation' + 's'}\b", re.IGNORECASE)

    violations = [
        f"{path}: retired product messaging"
        for path, contents in _human_facing_texts()
        if retired_status_pattern.search(contents)
        or (_is_documentation_path(path) and retired_topic_pattern.search(contents))
    ]

    assert violations == []


def test_human_facing_text_omits_retired_skill_catalog_and_renderer() -> None:
    retired_references = ("skills/specx-", "render_architecture_guardrails.py")

    violations = [
        f"{path}: retired skill-catalog reference"
        for path, contents in _human_facing_texts()
        if any(reference in contents for reference in retired_references)
    ]

    assert violations == []


def test_human_facing_text_avoids_em_dashes() -> None:
    em_dash = chr(0x2014)

    violations = [
        f"{path}: em dash"
        for path, contents in _human_facing_texts()
        if not path.name.startswith("THIRD_PARTY_NOTICES") and em_dash in contents
    ]

    assert violations == []
