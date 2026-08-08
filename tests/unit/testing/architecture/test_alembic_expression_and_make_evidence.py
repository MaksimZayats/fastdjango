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


@pytest.mark.parametrize(
    "body",
    [
        "    pytest.skip('disabled')\n",
        "    pytest.xfail('disabled')\n",
        "    stop_test('disabled')\n",
        "    pytest.skip('disabled') or command.upgrade(None, 'head')\n",
    ],
)
def test_runtime_pytest_outcomes_terminate_migration_evidence(
    tmp_path: Path,
    body: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n"
        "from pytest import skip as stop_test\n\n"
        "def test_migrations():\n"
        f"{body}"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _invalid_file(
        _check(tmp_path),
        "tests/integration/migrations/test_migrations.py",
    )


@pytest.mark.parametrize(
    "prefix",
    [
        "    True or pytest.skip('disabled')\n",
        "    False and pytest.xfail('disabled')\n",
        "    pytest.skip('disabled') if False else None\n",
    ],
)
def test_short_circuited_pytest_outcomes_do_not_terminate_migration_evidence(
    tmp_path: Path,
    prefix: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n\n"
        "def test_migrations():\n"
        f"{prefix}"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _check(tmp_path).violations == ()


@pytest.mark.parametrize(
    "module_outcome",
    [
        "import pytest\npytest.skip('disabled', allow_module_level=True)\n",
        "from pytest import xfail as stop_module\nstop_module('disabled')\n",
        "import pytest as pt\npt.importorskip('optional_dependency')\n",
    ],
)
def test_reachable_module_pytest_outcome_disables_migration_evidence(
    tmp_path: Path,
    module_outcome: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        f"from alembic import command\n{module_outcome}\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _invalid_file(
        _check(tmp_path),
        "tests/integration/migrations/test_migrations.py",
    )


@pytest.mark.parametrize(
    ("outcome", "handler"),
    [
        ("pytest.skip('disabled', allow_module_level=True)", "except BaseException:"),
        ("pytest.xfail('disabled')", "except:"),
    ],
)
def test_compatible_module_handler_catches_pytest_outcome_for_migration_evidence(
    tmp_path: Path,
    outcome: str,
    handler: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n\n"
        "try:\n"
        f"    {outcome}\n"
        f"{handler}\n"
        "    pass\n\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _check(tmp_path).violations == ()


@pytest.mark.parametrize(
    "outcome",
    [
        "pytest.skip('disabled', allow_module_level=True)",
        "pytest.xfail('disabled')",
    ],
)
def test_exception_module_handler_does_not_catch_pytest_outcome_for_migration_evidence(
    tmp_path: Path,
    outcome: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n\n"
        "try:\n"
        f"    {outcome}\n"
        "except Exception:\n"
        "    pass\n\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _invalid_file(
        _check(tmp_path),
        "tests/integration/migrations/test_migrations.py",
    )


@pytest.mark.parametrize(
    ("handler", "finally_body", "is_valid"),
    [
        ("except BaseException:", "    cleanup = None\n", True),
        ("except BaseException:", "    pytest.xfail('disabled')\n", False),
        ("except Exception:", "    cleanup = None\n", False),
    ],
)
def test_module_pytest_outcome_handlers_preserve_finally_semantics_for_migration_evidence(
    tmp_path: Path,
    handler: str,
    finally_body: str,
    is_valid: bool,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n\n"
        "try:\n"
        "    pytest.skip('disabled', allow_module_level=True)\n"
        f"{handler}\n"
        "    pass\n"
        "finally:\n"
        f"{finally_body}\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    violations = _check(tmp_path).violations
    assert (violations == ()) is is_valid


@pytest.mark.parametrize(
    "dead_outcome",
    [
        "if False:\n    pytest.skip('disabled', allow_module_level=True)\n",
        "True or pytest.xfail('disabled')\n",
        "False and pytest.importorskip('optional_dependency')\n",
        "pytest.skip('disabled', allow_module_level=True) if False else None\n",
    ],
)
def test_dead_module_pytest_outcome_preserves_migration_evidence(
    tmp_path: Path,
    dead_outcome: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        f"from alembic import command\nimport pytest\n{dead_outcome}\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _check(tmp_path).violations == ()


@pytest.mark.parametrize(
    "definition",
    [
        "def helper(optional=pytest.importorskip('optional_dependency')):\n    pass\n",
        "async def helper(*, optional=pytest.importorskip('optional_dependency')):\n    pass\n",
        "@pytest.skip('disabled', allow_module_level=True)\ndef helper():\n    pass\n",
        "helper = lambda optional=pytest.importorskip('optional_dependency'): None\n",
    ],
)
def test_import_time_definition_outcome_disables_migration_evidence(
    tmp_path: Path,
    definition: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n"
        f"{definition}\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _invalid_file(
        _check(tmp_path),
        "tests/integration/migrations/test_migrations.py",
    )


def test_deferred_function_and_lambda_bodies_preserve_migration_evidence(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n\n"
        "def deferred():\n"
        "    pytest.skip('disabled', allow_module_level=True)\n"
        "callback = lambda: pytest.xfail('disabled')\n\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _check(tmp_path).violations == ()


def test_conditionally_reachable_module_pytest_outcome_disables_migration_evidence(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n"
        "if optional_dependency_enabled:\n"
        "    pytest.importorskip('optional_dependency')\n\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _invalid_file(
        _check(tmp_path),
        "tests/integration/migrations/test_migrations.py",
    )


@pytest.mark.parametrize(
    "class_body",
    [
        "    pytest.skip('disabled', allow_module_level=True)\n",
        "    pytest.importorskip('optional_dependency')\n",
        "    if optional_dependency_enabled:\n        pytest.xfail('disabled')\n",
        "    stop_module = pytest.skip\n    stop_module('disabled', allow_module_level=True)\n",
    ],
)
def test_reachable_class_body_pytest_outcome_disables_migration_evidence(
    tmp_path: Path,
    class_body: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n"
        f"class ImportTimePolicy:\n{class_body}\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _invalid_file(
        _check(tmp_path),
        "tests/integration/migrations/test_migrations.py",
    )


@pytest.mark.parametrize(
    "class_body",
    [
        "    if False:\n        pytest.skip('disabled', allow_module_level=True)\n",
        "    True or pytest.xfail('disabled')\n",
        "    False and pytest.importorskip('optional_dependency')\n",
        "    def deferred():\n"
        "        pytest.skip('disabled', allow_module_level=True)\n"
        "    callback = lambda: pytest.xfail('disabled')\n",
    ],
)
def test_dead_or_deferred_class_body_outcome_preserves_migration_evidence(
    tmp_path: Path,
    class_body: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n"
        f"class ImportTimePolicy:\n{class_body}\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _check(tmp_path).violations == ()


@pytest.mark.parametrize(
    "module_outcome",
    [
        "stop_module = pytest.skip\nstop_module('disabled', allow_module_level=True)\n",
        "stop_module = pytest.xfail\nstop_alias = stop_module\nstop_alias('disabled')\n",
        "stop_module = pytest.skip\n"
        "stop_module('disabled', allow_module_level=True)\n"
        "stop_module = object\n",
        "def stop_two():\n"
        "    pytest.importorskip('optional_dependency')\n"
        "def stop_one():\n"
        "    stop_two()\n"
        "stop_one()\n",
        "def stop_one():\n"
        "    stop_two()\n"
        "def stop_two():\n"
        "    stop_one()\n"
        "    pytest.xfail('disabled')\n"
        "stop_one()\n",
    ],
)
def test_aliased_or_helper_module_outcome_disables_migration_evidence(
    tmp_path: Path,
    module_outcome: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n"
        f"{module_outcome}\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _invalid_file(
        _check(tmp_path),
        "tests/integration/migrations/test_migrations.py",
    )


def test_uninvoked_or_short_circuited_outcome_helper_preserves_migration_evidence(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n\n"
        "def stop_module():\n"
        "    pytest.skip('disabled', allow_module_level=True)\n\n"
        "False and stop_module()\n\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _check(tmp_path).violations == ()


def test_rebound_outcome_alias_preserves_migration_evidence(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n\n"
        "stop_module = pytest.skip\n"
        "stop_module = lambda *args, **kwargs: None\n"
        "stop_module('disabled', allow_module_level=True)\n\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _check(tmp_path).violations == ()


@pytest.mark.parametrize(
    "helper_body",
    [
        "    outcome = pytest.skip\n    outcome('disabled', allow_module_level=True)\n",
        "    outcome = pytest.xfail\n    outcome_alias = outcome\n    outcome_alias('disabled')\n",
        "    outcome = pytest.skip\n"
        "    outcome('disabled', allow_module_level=True)\n"
        "    outcome = object\n",
        "    if True:\n"
        "        outcome = pytest.skip\n"
        "        outcome('disabled', allow_module_level=True)\n",
    ],
)
def test_helper_local_outcome_alias_disables_migration_evidence(
    tmp_path: Path,
    helper_body: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n\n"
        f"def stop_module():\n{helper_body}\n"
        "stop_module()\n\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _invalid_file(
        _check(tmp_path),
        "tests/integration/migrations/test_migrations.py",
    )


@pytest.mark.parametrize(
    "helper_body",
    [
        "    outcome = pytest.skip\n"
        "    outcome = lambda *args, **kwargs: None\n"
        "    outcome('disabled', allow_module_level=True)\n",
        "    outcome = pytest.skip\n    False and outcome('disabled', allow_module_level=True)\n",
        "    outcome = pytest.skip\n"
        "    if True:\n"
        "        outcome = lambda *args, **kwargs: None\n"
        "        outcome('disabled', allow_module_level=True)\n",
    ],
)
def test_rebound_or_dead_helper_alias_preserves_migration_evidence(
    tmp_path: Path,
    helper_body: str,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n\n"
        f"def stop_module():\n{helper_body}\n"
        "stop_module()\n\n"
        "def test_migrations():\n"
        "    command.upgrade(None, 'head')\n"
        "    command.check(None)\n",
    )

    assert _check(tmp_path).violations == ()


def test_exception_handler_does_not_catch_pytest_outcome_for_migration_evidence(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n\n"
        "def test_migrations():\n"
        "    try:\n"
        "        pytest.skip('disabled')\n"
        "    except Exception:\n"
        "        command.upgrade(None, 'head')\n"
        "        command.check(None)\n",
    )

    assert _invalid_file(
        _check(tmp_path),
        "tests/integration/migrations/test_migrations.py",
    )


@pytest.mark.parametrize("handler", ["BaseException", None])
def test_compatible_handler_catches_pytest_outcome_for_migration_evidence(
    tmp_path: Path,
    handler: str | None,
) -> None:
    _write_project(tmp_path)
    except_clause = f"except {handler}:" if handler is not None else "except:"
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "from alembic import command\n"
        "import pytest\n\n"
        "def test_migrations():\n"
        "    try:\n"
        "        pytest.xfail('disabled')\n"
        f"    {except_clause}\n"
        "        command.upgrade(None, 'head')\n"
        "        command.check(None)\n",
    )

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
