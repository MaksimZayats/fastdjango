from __future__ import annotations

from pathlib import Path

import pytest

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxRuleId,
    check_specx_architecture,
)


def test_standard_async_alembic_helper_chain_is_valid(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "migrations/env.py",
        "import asyncio\n"
        "from alembic import context\n\n"
        "def do_run_migrations(connection):\n"
        "    context.configure(connection=connection)\n"
        "    context.run_migrations()\n\n"
        "async def run_async_migrations():\n"
        "    async with connectable.connect() as connection:\n"
        "        await connection.run_sync(do_run_migrations)\n\n"
        "def run_migrations_online():\n"
        "    asyncio.run(run_async_migrations())\n\n"
        "if context.is_offline_mode():\n"
        "    raise RuntimeError('offline mode is disabled')\n"
        "else:\n"
        "    run_migrations_online()\n",
    )

    report = _check(tmp_path)

    assert report.violations == ()


def test_unreachable_async_alembic_helper_is_not_evidence(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "migrations/env.py",
        "from alembic import context\n\n"
        "def unused_helper(connection):\n"
        "    context.configure(connection=connection)\n"
        "    context.run_migrations()\n\n"
        "def run_migrations_online():\n"
        "    pass\n\n"
        "run_migrations_online()\n",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "migrations/env.py" in report.violations[0].message


def test_shadowed_async_callback_is_not_helper_evidence(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "migrations/env.py",
        "from alembic import context\n\n"
        "def do_run_migrations(connection):\n"
        "    context.configure(connection=connection)\n"
        "    context.run_migrations()\n\n"
        "async def run_async_migrations(do_run_migrations):\n"
        "    await connection.run_sync(do_run_migrations)\n\n"
        "def run_migrations_online():\n"
        "    run_async_migrations(None)\n\n"
        "run_migrations_online()\n",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "migrations/env.py" in report.violations[0].message


@pytest.mark.parametrize(
    "test_body",
    [
        (
            "    try:\n"
            "        command.upgrade(None, 'head')\n"
            "        command.check(None)\n"
            "    except Exception:\n"
            "        pass\n"
        ),
        (
            "    with expect_error(Exception):\n"
            "        command.upgrade(None, 'head')\n"
            "        command.check(None)\n"
        ),
    ],
)
def test_swallowed_migration_failures_are_not_integration_evidence(
    tmp_path: Path,
    test_body: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "from pytest import raises as expect_error\n\n"
        "def test_migrations():\n"
        f"{test_body}",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "tests/integration/migrations/test_migrations.py" in report.violations[0].message


@pytest.mark.parametrize(
    "decorator",
    [
        "@pytest.mark.skip",
        "@pytest.mark.skip(reason='disabled')",
        "@pytest.mark.xfail",
        "@pytest.mark.xfail(reason='unstable')",
        "@pytest.mark.skipif(True, reason='disabled')",
        "@pytest.mark.skipif(1, reason='disabled')",
        "@pytest.mark.skipif(condition=True, reason='disabled')",
    ],
)
def test_skipped_or_xfailed_tests_are_not_integration_evidence(
    tmp_path: Path,
    decorator: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n\n"
        f"{decorator}\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "tests/integration/migrations/test_migrations.py" in report.violations[0].message


def test_statically_false_skipif_remains_valid_integration_evidence(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "from pytest import mark as test_mark\n\n"
        "@test_mark.skipif(False, reason='enabled')\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    report = _check(tmp_path)

    assert report.violations == ()


def test_statically_false_xfail_remains_valid_integration_evidence(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n\n"
        "@pytest.mark.xfail(condition=False, reason='enabled')\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    report = _check(tmp_path)

    assert report.violations == ()


def test_revision_evidence_after_return_is_unreachable(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "migrations/versions/0001.py",
        "from alembic import op\n\n"
        "revision = '0001'\n"
        "down_revision = None\n\n"
        "def upgrade():\n"
        "    return\n"
        "    op.create_table('orders')\n\n"
        "def downgrade(): pass\n",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "migrations/versions/<revision>.py" in report.violations[0].message


def test_integration_evidence_after_return_is_unreachable(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n\n"
        "def test_migrations():\n"
        "    return\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "tests/integration/migrations/test_migrations.py" in report.violations[0].message


@pytest.mark.parametrize(
    "command_prefix",
    [
        "env -u DATABASE_URL alembic",
        "env --unset DATABASE_URL alembic",
        "env --unset=DATABASE_URL alembic",
        "env -uDATABASE_URL alembic",
        "env -C /workspace alembic",
        "env --chdir /workspace alembic",
        "env --chdir=/workspace alembic",
        "env -C/workspace alembic",
    ],
)
def test_env_options_with_values_preserve_alembic_command(
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
        "revision = '0001'\n"
        "down_revision = None\n\n"
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
