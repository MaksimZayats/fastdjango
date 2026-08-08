from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")
REFERENCE_PATH_PATTERN = re.compile(r"`(references/[A-Za-z0-9_./-]+)`")
MAX_SKILL_LINES = 500
LONG_REFERENCE_LINES = 100
CANONICAL_SKILL_NAMES = frozenset({"specx"})


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("skills")
    failures: list[str] = []

    if not root.is_dir():
        failures.append(f"{root}: skills directory does not exist")
        return _finish(failures=failures)

    skill_dirs = sorted(path for path in root.iterdir() if path.is_dir())
    skill_names = {path.name for path in skill_dirs}
    if skill_names != CANONICAL_SKILL_NAMES:
        failures.append(
            f"{root}: canonical skill directories must be {sorted(CANONICAL_SKILL_NAMES)}; "
            f"found {sorted(skill_names)}"
        )

    for skill_dir in skill_dirs:
        failures.extend(_validate_skill(skill_dir=skill_dir))

    mirror_root = root.parent / ".agents" / "skills"
    if mirror_root.parent.is_dir():
        if not mirror_root.is_dir():
            failures.append(f"{mirror_root}: tracked local skill mirror is missing")
        else:
            failures.extend(_validate_mirror(source_root=root, mirror_root=mirror_root))

    return _finish(failures=failures)


def _validate_skill(*, skill_dir: Path) -> list[str]:
    failures: list[str] = []
    skill_name = skill_dir.name

    if not SKILL_NAME_PATTERN.fullmatch(skill_name):
        failures.append(f"{skill_dir}: skill directory name must be lowercase kebab-case")

    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        failures.append(f"{skill_dir}: missing SKILL.md")
        return failures

    text = skill_file.read_text(encoding="utf-8")
    if "TODO" in text:
        failures.append(f"{skill_file}: contains TODO placeholder text")
    if len(text.splitlines()) > MAX_SKILL_LINES:
        failures.append(f"{skill_file}: must stay at or below {MAX_SKILL_LINES} lines")

    for relative_reference in REFERENCE_PATH_PATTERN.findall(text):
        reference_path = skill_dir / relative_reference
        if not reference_path.is_file():
            failures.append(f"{skill_file}: references missing file {relative_reference}")

    references_dir = skill_dir / "references"
    if references_dir.is_dir():
        for reference_path in sorted(references_dir.glob("*.md")):
            reference_text = reference_path.read_text(encoding="utf-8")
            if (
                len(reference_text.splitlines()) > LONG_REFERENCE_LINES
                and "\n## Contents\n" not in reference_text
            ):
                failures.append(
                    f"{reference_path}: references over {LONG_REFERENCE_LINES} lines "
                    "need a Contents section"
                )

    frontmatter = _frontmatter(text=text)
    if frontmatter is None:
        failures.append(f"{skill_file}: missing YAML frontmatter")
        return failures

    metadata = yaml.safe_load(frontmatter)
    if not isinstance(metadata, dict):
        failures.append(f"{skill_file}: frontmatter must be a mapping")
        return failures

    allowed_keys = {"name", "description"}
    unexpected_keys = set(metadata) - allowed_keys
    if unexpected_keys:
        failures.append(f"{skill_file}: unexpected frontmatter keys {sorted(unexpected_keys)}")

    name = metadata.get("name")
    if name != skill_name:
        failures.append(f"{skill_file}: name must match directory name")

    description = metadata.get("description")
    if not isinstance(description, str) or not description.strip():
        failures.append(f"{skill_file}: description is required")
    elif "<" in description or ">" in description:
        failures.append(f"{skill_file}: description cannot contain angle brackets")

    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if openai_yaml.exists():
        failures.extend(_validate_openai_yaml(path=openai_yaml, skill_name=skill_name))

    return failures


def _frontmatter(*, text: str) -> str | None:
    if not text.startswith("---\n"):
        return None

    end_marker = text.find("\n---\n", 4)
    if end_marker == -1:
        return None

    return text[4:end_marker]


def _validate_openai_yaml(*, path: Path, skill_name: str) -> list[str]:
    failures: list[str] = []
    data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return [f"{path}: must contain a YAML mapping"]

    interface = data.get("interface")
    if not isinstance(interface, dict):
        return [f"{path}: missing interface mapping"]

    default_prompt = interface.get("default_prompt")
    if not isinstance(default_prompt, str) or f"${skill_name}" not in default_prompt:
        failures.append(f"{path}: default_prompt must mention ${skill_name}")

    short_description = interface.get("short_description")
    if not isinstance(short_description, str) or not 25 <= len(short_description) <= 64:
        failures.append(f"{path}: short_description must be 25-64 characters")

    return failures


def _validate_mirror(*, source_root: Path, mirror_root: Path) -> list[str]:
    source_files = _catalog_files(source_root)
    mirror_files = _catalog_files(mirror_root)
    failures: list[str] = []

    for relative_path in sorted(source_files.keys() - mirror_files.keys()):
        failures.append(f"{mirror_root}: missing mirrored file {relative_path}")
    for relative_path in sorted(mirror_files.keys() - source_files.keys()):
        failures.append(f"{mirror_root}: unexpected mirrored file {relative_path}")
    for relative_path in sorted(source_files.keys() & mirror_files.keys()):
        if source_files[relative_path].read_bytes() != mirror_files[relative_path].read_bytes():
            failures.append(f"{mirror_root}: stale mirrored file {relative_path}")

    return failures


def _catalog_files(root: Path) -> dict[Path, Path]:
    return {
        path.relative_to(root): path
        for path in root.rglob("*")
        if path.is_file()
        and path.name != ".DS_Store"
        and path.suffix != ".pyc"
        and "__pycache__" not in path.parts
    }


def _finish(*, failures: list[str]) -> int:
    if failures:
        for failure in failures:
            print(failure)
        return 1

    print("All skills are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
