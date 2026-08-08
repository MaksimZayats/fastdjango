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
    "disabled_source",
    [
        "pytestmark = pytest.mark.skip(reason='module disabled')\n\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
        "class TestMigrations:\n"
        "    pytestmark = [pytest.mark.skip(reason='class disabled')]\n"
        "    def test_migrations(self):\n"
        "        command.upgrade(None, 'head')\n"
        "        command.check(None)\n",
        "@pytest.mark.skip(reason='class disabled')\n"
        "class TestMigrations:\n"
        "    def test_migrations(self):\n"
        "        command.upgrade(None, 'head')\n"
        "        command.check(None)\n",
    ],
)
def test_module_and_class_pytest_markers_disable_migration_evidence(
    tmp_path: Path,
    disabled_source: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\nimport pytest\n\n" + disabled_source,
    )

    report = _check(tmp_path)

    assert _invalid_file(report, "tests/integration/migrations/test_migrations.py")


@pytest.mark.parametrize(
    "decorators",
    [
        "@pytest.mark.skip(reason='disabled')\n"
        "@pytest.mark.xfail(condition=False, reason='inactive')",
        "@pytest.mark.xfail(condition=False, reason='inactive')\n"
        "@pytest.mark.skip(reason='disabled')",
    ],
)
def test_conditional_marker_order_does_not_hide_unconditional_disable(
    tmp_path: Path,
    decorators: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\nimport pytest\n\n"
        f"{decorators}\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    report = _check(tmp_path)

    assert _invalid_file(report, "tests/integration/migrations/test_migrations.py")


def test_enabled_class_test_and_false_module_xfail_are_valid(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\nimport pytest\n\n"
        "pytestmark = pytest.mark.xfail(condition=False, reason='inactive')\n\n"
        "class TestMigrations:\n"
        "    def test_migrations(self):\n"
        "        command.upgrade(None, 'head')\n"
        "        command.check(None)\n",
    )

    report = _check(tmp_path)

    assert report.violations == ()


@pytest.mark.parametrize(
    "context_source",
    [
        "from contextlib import suppress\n\n"
        "def test_migrations():\n"
        "    with suppress(Exception):\n"
        "        command.upgrade(None, 'head')\n"
        "        command.check(None)\n",
        "from contextlib import suppress as ignore_errors\n\n"
        "def test_migrations():\n"
        "    with ignore_errors(Exception):\n"
        "        command.upgrade(None, 'head')\n"
        "        command.check(None)\n",
        "import pytest\n\n"
        "def test_migrations():\n"
        "    with pytest.raises(Exception):\n"
        "        command.upgrade(None, 'head')\n"
        "        command.check(None)\n",
    ],
)
def test_exception_suppressors_do_not_prove_migrations(
    tmp_path: Path,
    context_source: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n" + context_source,
    )

    report = _check(tmp_path)

    assert _invalid_file(report, "tests/integration/migrations/test_migrations.py")


def test_migration_evidence_in_finally_executes_before_return(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n\n"
        "def test_migrations():\n"
        "    try:\n"
        "        return\n"
        "    finally:\n"
        "        command.upgrade(None, 'head')\n"
        "        command.check(None)\n",
    )

    report = _check(tmp_path)

    assert report.violations == ()


@pytest.mark.parametrize(
    "terminal_prefix",
    [
        "    try:\n        return\n    finally:\n        cleanup()\n",
        "    try:\n        raise RuntimeError\n    except RuntimeError:\n        return\n",
        "    match value:\n"
        "        case True:\n            return\n"
        "        case _:\n            return\n",
    ],
)
def test_evidence_after_exhaustive_terminal_control_flow_is_unreachable(
    tmp_path: Path,
    terminal_prefix: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n\n"
        "def cleanup(): pass\n\n"
        "def test_migrations(value=True):\n"
        f"{terminal_prefix}"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    report = _check(tmp_path)

    assert _invalid_file(report, "tests/integration/migrations/test_migrations.py")


def test_upgrade_and_drift_must_share_every_passing_path(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n\n"
        "def test_migrations(flag=False):\n"
        "    if flag:\n"
        "        command.upgrade(None, 'head')\n"
        "    else:\n"
        "        command.check(None)\n",
    )

    report = _check(tmp_path)

    assert _invalid_file(report, "tests/integration/migrations/test_migrations.py")


def test_env_configure_and_run_migrations_must_share_every_passing_path(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "migrations/env.py",
        "from alembic import context\n\n"
        "def run_migrations_online(flag=False):\n"
        "    if flag:\n"
        "        context.configure(connection=None)\n"
        "    else:\n"
        "        context.run_migrations()\n\n"
        "run_migrations_online()\n",
    )

    report = _check(tmp_path)

    assert _invalid_file(report, "migrations/env.py")


def test_main_guard_only_env_invocation_is_not_alembic_import_evidence(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "migrations/env.py",
        "from alembic import context\n\n"
        "def run_migrations_online():\n"
        "    context.configure(connection=None)\n"
        "    context.run_migrations()\n\n"
        "if __name__ == '__main__':\n"
        "    run_migrations_online()\n",
    )

    report = _check(tmp_path)

    assert _invalid_file(report, "migrations/env.py")


@pytest.mark.parametrize(
    "revision_source",
    [
        "from alembic import op\n\n"
        "revision = '0001'\n\n"
        "def upgrade(): op.create_table('orders')\n"
        "def downgrade(): pass\n",
        "from alembic import op\n\n"
        "revision = '0001'\n"
        "down_revision = None\n\n"
        "def upgrade(): op.get_bind()\n"
        "def downgrade(): pass\n",
        "from alembic import op\n\n"
        "revision = '0001'\n"
        "down_revision = None\n\n"
        "def upgrade():\n"
        "    with suppress(Exception):\n"
        "        op.create_table('orders')\n"
        "def downgrade(): pass\n",
        "from alembic import op\n\n"
        "revision = '0001'\n"
        "down_revision = None\n\n"
        "def upgrade():\n"
        "    try:\n"
        "        op.create_table('orders')\n"
        "    except Exception:\n"
        "        pass\n"
        "def downgrade(): pass\n",
    ],
)
def test_revision_requires_down_revision_and_unsuppressed_forward_effect(
    tmp_path: Path,
    revision_source: str,
) -> None:
    _write_project(tmp_path)
    if "suppress" in revision_source:
        revision_source = "from contextlib import suppress\n" + revision_source
    _write(tmp_path / "migrations/versions/0001.py", revision_source)

    report = _check(tmp_path)

    assert _invalid_file(report, "migrations/versions/<revision>.py")


def test_batch_alter_operation_is_a_forward_revision_effect(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "migrations/versions/0001.py",
        "from alembic import op\n\n"
        "revision = '0001'\n"
        "down_revision = None\n\n"
        "def upgrade():\n"
        "    with op.batch_alter_table('orders') as batch_op:\n"
        "        batch_op.add_column('status')\n"
        "def downgrade(): pass\n",
    )

    report = _check(tmp_path)

    assert report.violations == ()


def test_raw_declarative_base_descendant_activates_alembic_rule(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/demo_service/foundation/model.py",
        "from sqlalchemy.orm import DeclarativeBase\n\n"
        "class ProjectModelBase(DeclarativeBase): pass\n",
    )
    _write(
        tmp_path / "src/demo_service/core/orders/entities/order.py",
        "from sqlalchemy.orm import Mapped, mapped_column\n"
        "from demo_service.foundation.model import ProjectModelBase\n\n"
        "class OrderModel(ProjectModelBase):\n"
        "    __tablename__ = 'orders'\n"
        "    id: Mapped[int] = mapped_column(primary_key=True)\n",
    )

    report = _check(tmp_path)

    assert len(report.violations) == 1
    assert "alembic.ini" in report.violations[0].message


def _write_project(tmp_path: Path) -> None:
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
        "migrate:\n\tuv run alembic upgrade head\n\n"
        "makemigrations:\n\tuv run alembic revision --autogenerate\n\n"
        "migration-check:\n\tuv run alembic check\n",
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
