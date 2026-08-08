from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = PROJECT_ROOT / "scripts" / "validate_skills.py"


@pytest.mark.parametrize("skill_names", [(), ("specx", "second-skill")])
def test_skill_validator_requires_exactly_the_specx_skill(
    tmp_path: Path,
    skill_names: tuple[str, ...],
) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    for name in skill_names:
        skill = root / name
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Navigate this test project.\n---\n",
            encoding="utf-8",
        )

    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(root)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "canonical skill directories must be ['specx']" in result.stdout
