from __future__ import annotations

from pathlib import Path

import pytest

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_rebound_alembic_imports_are_not_valid_evidence(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "migrations/env.py",
        "from alembic import context\n\n"
        "class FakeContext:\n"
        "    def configure(self): pass\n"
        "    def run_migrations(self): pass\n\n"
        "context = FakeContext()\n\n"
        "def run_migrations_online():\n"
        "    context.configure()\n"
        "    context.run_migrations()\n\n"
        "run_migrations_online()\n",
    )
    _write(
        tmp_path / "migrations/versions/0001.py",
        "from alembic import op\n\n"
        "revision = '0001'\n\n"
        "class FakeOp:\n"
        "    def execute(self, value): pass\n\n"
        "op = FakeOp()\n\n"
        "def upgrade(): op.execute('not a migration')\n"
        "def downgrade(): pass\n",
    )
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n\n"
        "class FakeCommand:\n"
        "    def upgrade(self): pass\n"
        "    def check(self): pass\n\n"
        "command = FakeCommand()\n\n"
        "def test_migrations():\n"
        "    command.upgrade()\n"
        "    command.check()\n",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "migrations/env.py" in report.violations[0].message
    assert "migrations/versions/<revision>.py" in report.violations[0].message
    assert "tests/integration/migrations/test_migrations.py" in report.violations[0].message


def test_revision_requires_upgrade_operation_evidence(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "migrations/versions/0001.py",
        "from alembic import op\n\n"
        "revision = '0001'\n\n"
        "def upgrade(): pass\n"
        "def downgrade(): op.drop_table('orders')\n",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "migrations/versions/<revision>.py" in report.violations[0].message


@pytest.mark.parametrize(
    ("prefix", "statement"),
    [
        ("from typing import TYPE_CHECKING\n", "if TYPE_CHECKING:"),
        ("", "if 0:"),
        ("", "while False:"),
    ],
)
def test_dead_upgrade_evidence_is_rejected(
    tmp_path: Path,
    prefix: str,
    statement: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "migrations/versions/0001.py",
        f"{prefix}from alembic import op\n\n"
        "revision = '0001'\n\n"
        f"def upgrade():\n    {statement}\n        op.create_table('orders')\n"
        "def downgrade(): pass\n",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "migrations/versions/<revision>.py" in report.violations[0].message


@pytest.mark.parametrize(
    "command_prefix",
    [
        "uv run --locked alembic",
        "uv run --group migrations alembic",
        "/opt/venv/bin/alembic",
        "env DATABASE_URL=sqlite:///test.db alembic",
    ],
)
def test_supported_make_wrappers_invoke_alembic(
    tmp_path: Path,
    command_prefix: str,
) -> None:
    _write_project(tmp_path, command_prefix=command_prefix)

    report = _check(tmp_path)

    assert report.violations == ()


def _write_project(tmp_path: Path, *, command_prefix: str = "uv run alembic") -> None:
    _write(
        tmp_path / "src/demo_service/core/orders/infrastructure/sqlalchemy/models/order.py",
        "from specx.infrastructure.foundation.sqlalchemy.model import BaseSQLAlchemyModel\n\n"
        "class OrderModel(BaseSQLAlchemyModel): pass\n",
    )
    _write(tmp_path / "alembic.ini", "[alembic]\nscript_location = migrations\n")
    _write(
        tmp_path / "migrations/env.py",
        "from alembic import context\n\n"
        "def run_migrations_online():\n"
        "    context.configure(connection=None)\n"
        "    context.run_migrations()\n\n"
        "run_migrations_online()\n",
    )
    _write(
        tmp_path / "migrations/script.py.mako",
        "def upgrade():\n    pass\n\ndef downgrade():\n    pass\n",
    )
    _write(
        tmp_path / "migrations/versions/0001.py",
        "from alembic import op\n\n"
        "revision = '0001'\n\n"
        "def upgrade(): op.create_table('orders')\n"
        "def downgrade(): pass\n",
    )
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )
    _write(
        tmp_path / "Makefile",
        f"migrate:\n\t{command_prefix} upgrade head\n\n"
        f"makemigrations:\n\t{command_prefix} revision --autogenerate\n\n"
        f"migration-check:\n\t{command_prefix} check\n",
    )


def _check(project_root: Path) -> SpecxArchitectureReport:
    return check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=project_root,
            package_name="demo_service",
            disabled_rules=frozenset(
                rule
                for rule in SpecxRuleId
                if rule != SpecxRuleId.SQLALCHEMY_MODELS_REQUIRE_ALEMBIC
            ),
        )
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
