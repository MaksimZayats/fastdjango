from __future__ import annotations

from pathlib import Path

import pytest

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


@pytest.mark.parametrize(
    "effect",
    [
        "True or op.create_table('orders')",
        "op.create_table('orders') if False else None",
        "enabled and op.create_table('orders')",
        "[op.create_table('orders') for _ in ()]",
        "(op.create_table('orders') for _ in ())",
    ],
)
def test_revision_rejects_calls_that_need_not_execute(
    tmp_path: Path,
    effect: str,
) -> None:
    _write_project(tmp_path)
    source = (
        "from alembic import op\n"
        "revision = '0001'\n"
        "down_revision = None\n"
        "enabled = False\n"
        f"def upgrade(): {effect}\n"
        "def downgrade(): pass\n"
    )
    _write(tmp_path / "migrations/versions/0001.py", source)

    assert _invalid_file(_check(tmp_path), "migrations/versions/<revision>.py")


@pytest.mark.parametrize(
    "effect",
    [
        "False or op.create_table('orders')",
        "op.create_table('orders') if True else None",
    ],
)
def test_revision_accepts_statically_guaranteed_expression_calls(
    tmp_path: Path,
    effect: str,
) -> None:
    _write_project(tmp_path)
    source = (
        "from alembic import op\n"
        "revision = '0001'\n"
        "down_revision = None\n"
        f"def upgrade(): {effect}\n"
        "def downgrade(): pass\n"
    )
    _write(tmp_path / "migrations/versions/0001.py", source)

    assert _check(tmp_path).violations == ()


@pytest.mark.parametrize(
    ("artifact", "source"),
    [
        (
            "migrations/env.py",
            "from alembic import context\n"
            "def run_migrations_online():\n"
            "    True or context.configure(connection=None)\n"
            "    True or context.run_migrations()\n"
            "run_migrations_online()\n",
        ),
        (
            "tests/integration/migrations/test_migrations.py",
            "from alembic import command\n"
            "def test_migrations():\n"
            "    True or command.upgrade(None, 'head')\n"
            "    True or command.check(None)\n",
        ),
        (
            "tests/integration/migrations/test_migrations.py",
            "from alembic import command\n"
            "def test_migrations(enabled=False):\n"
            "    enabled and command.upgrade(None, 'head')\n"
            "    enabled and command.check(None)\n",
        ),
    ],
)
def test_required_artifacts_reject_calls_that_need_not_execute(
    tmp_path: Path,
    artifact: str,
    source: str,
) -> None:
    _write_project(tmp_path)
    _write(tmp_path / artifact, source)

    assert _invalid_file(_check(tmp_path), artifact)


@pytest.mark.parametrize(
    ("artifact", "source"),
    [
        (
            "migrations/env.py",
            "from alembic import context\n"
            "def run_migrations_online():\n"
            "    False or context.configure(connection=None)\n"
            "    context.run_migrations() if True else None\n"
            "run_migrations_online()\n",
        ),
        (
            "tests/integration/migrations/test_migrations.py",
            "from alembic import command\n"
            "def test_migrations():\n"
            "    False or command.upgrade(None, 'head')\n"
            "    command.check(None) if True else None\n",
        ),
    ],
)
def test_required_artifacts_accept_statically_guaranteed_expression_calls(
    tmp_path: Path,
    artifact: str,
    source: str,
) -> None:
    _write_project(tmp_path)
    _write(tmp_path / artifact, source)

    assert _check(tmp_path).violations == ()


@pytest.mark.parametrize("prefix", ["-", "@-", "-@", "+-"])
def test_make_recipe_rejects_ignore_errors_prefix(tmp_path: Path, prefix: str) -> None:
    _write_project(tmp_path)
    _write_makefile(
        tmp_path,
        migration_check=f"{prefix}uv run --locked alembic check",
    )

    assert "migration-check" in _check(tmp_path).violations[0].message


@pytest.mark.parametrize(
    "suffix",
    [
        " || true",
        "||true",
        " ; true",
        ";true",
        " | cat",
        "|cat",
        " &",
    ],
)
def test_make_recipe_rejects_shell_constructs_that_can_mask_failure(
    tmp_path: Path,
    suffix: str,
) -> None:
    _write_project(tmp_path)
    _write_makefile(
        tmp_path,
        migration_check=f"uv run --locked alembic check{suffix}",
    )

    assert "migration-check" in _check(tmp_path).violations[0].message


@pytest.mark.parametrize(
    ("target", "command"),
    [
        ("migrate", "@uv run --locked alembic upgrade head"),
        ("makemigrations", "+env APP_ENV=test alembic revision --autogenerate"),
        ("migration-check", "/opt/project/.venv/bin/alembic check && echo checked"),
    ],
)
def test_make_recipe_preserves_safe_wrappers_and_failure_propagation(
    tmp_path: Path,
    target: str,
    command: str,
) -> None:
    _write_project(tmp_path)
    arguments = {
        "migrate": {},
        "makemigrations": {"makemigrations": command},
        "migration-check": {"migration_check": command},
    }[target]
    if target == "migrate":
        arguments = {"migrate": command}
    _write_makefile(tmp_path, **arguments)

    assert _check(tmp_path).violations == ()


def _write_project(project_root: Path) -> None:
    _write(
        project_root / "src/demo_service/core/orders/infrastructure/sqlalchemy/models/order.py",
        "from specx.infrastructure.foundation.sqlalchemy.model import BaseSQLAlchemyModel\n\n"
        "class OrderModel(BaseSQLAlchemyModel): pass\n",
    )
    _write(project_root / "alembic.ini", "[alembic]\nscript_location = migrations\n")
    _write(
        project_root / "migrations/env.py",
        "from alembic import context\n\n"
        "def run_migrations_online():\n"
        "    context.configure(connection=None)\n"
        "    context.run_migrations()\n\n"
        "run_migrations_online()\n",
    )
    _write(
        project_root / "migrations/script.py.mako",
        "def upgrade():\n    pass\n\ndef downgrade():\n    pass\n",
    )
    _write(
        project_root / "migrations/versions/0001.py",
        "from alembic import op\n\n"
        "revision = '0001'\n"
        "down_revision = None\n\n"
        "def upgrade(): op.create_table('orders')\n"
        "def downgrade(): pass\n",
    )
    _write(
        project_root / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )
    _write_makefile(project_root)


def _write_makefile(
    project_root: Path,
    *,
    migrate: str = "uv run alembic upgrade head",
    makemigrations: str = "uv run alembic revision --autogenerate",
    migration_check: str = "uv run alembic check",
) -> None:
    _write(
        project_root / "Makefile",
        f"migrate:\n\t{migrate}\n\n"
        f"makemigrations:\n\t{makemigrations}\n\n"
        f"migration-check:\n\t{migration_check}\n",
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


def _invalid_file(report: SpecxArchitectureReport, name: str) -> bool:
    return len(report.violations) == 1 and name in report.violations[0].message


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
