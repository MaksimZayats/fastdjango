from __future__ import annotations

import ast
from pathlib import Path

from specx.testing.architecture.context import (
    ArchitectureContext,
    class_definition_base_index,
    class_has_foundation_base_at,
    class_is_statically_abstract,
)
from specx.testing.architecture.models import SpecxArchitectureViolation
from specx.testing.architecture.rule_id import SpecxRuleId
from specx.testing.architecture.rules._shared import ArchitectureRuleBase, violation


class SQLAlchemyModelsRequireAlembicRule(ArchitectureRuleBase):
    """Require Alembic configuration, revisions, commands, and tests for concrete models."""

    id: SpecxRuleId = SpecxRuleId.SQLALCHEMY_MODELS_REQUIRE_ALEMBIC
    remediation: str | None = (
        "Add meaningful Alembic config, environment and revision files, `migrate`, "
        "`makemigrations`, and `migration-check` recipes, plus an upgrade-and-drift test."
    )

    def check(self, context: ArchitectureContext) -> tuple[SpecxArchitectureViolation, ...]:
        if not _has_concrete_model(context):
            return ()
        required_files = _required_files(context)
        missing = sorted(name for name, path in required_files.items() if not path.is_file())
        invalid = sorted(
            name
            for name, path in required_files.items()
            if path.is_file() and not _has_required_markers(name, path.read_text(encoding="utf-8"))
        )
        versions = context.project_root / "migrations" / "versions"
        revisions = (
            tuple(
                path
                for path in versions.iterdir()
                if path.suffix == ".py" and path.name != "__init__.py"
            )
            if versions.is_dir()
            else ()
        )
        if not revisions:
            missing.append("migrations/versions/<revision>.py")
        elif not any(_valid_revision(path.read_text(encoding="utf-8")) for path in revisions):
            invalid.append("migrations/versions/<revision>.py")
        required_targets = {"migrate", "makemigrations", "migration-check"}
        missing_targets = sorted(required_targets - context.makefile_targets())
        invalid_targets = sorted(
            target
            for target in required_targets - set(missing_targets)
            if not _valid_make_recipe(target, context.makefile_target_recipes().get(target, ""))
        )
        if not missing and not invalid and not missing_targets and not invalid_targets:
            return ()
        details: list[str] = []
        if missing:
            details.append(f"missing files {missing}")
        if invalid:
            details.append(f"invalid or placeholder files {invalid}")
        if missing_targets:
            details.append(f"missing Make targets {missing_targets}")
        if invalid_targets:
            details.append(f"Make targets without Alembic recipes {invalid_targets}")
        return (
            violation(
                self.id,
                path=context.project_root,
                message="; ".join(details),
            ),
        )


def _has_concrete_model(context: ArchitectureContext) -> bool:
    definition_index = class_definition_base_index(context)
    for path in context.source_paths():
        if any(
            isinstance(node, ast.ClassDef)
            and not class_is_statically_abstract(node, context.aliases(path))
            and class_has_foundation_base_at(
                node,
                "BaseSQLAlchemyModel",
                source_path=path,
                context=context,
                definition_index=definition_index,
            )
            for node in ast.walk(context.tree(path))
        ):
            return True
    return False


def _required_files(context: ArchitectureContext) -> dict[str, Path]:
    return {
        "alembic.ini": context.project_root / "alembic.ini",
        "migrations/env.py": context.project_root / "migrations" / "env.py",
        "migrations/script.py.mako": context.project_root / "migrations" / "script.py.mako",
        "tests/integration/migrations/test_migrations.py": (
            context.project_root / "tests" / "integration" / "migrations" / "test_migrations.py"
        ),
    }


def _has_required_markers(name: str, text: str) -> bool:
    markers = {
        "alembic.ini": (("[alembic]",), ("script_location",)),
        "migrations/env.py": (("context.configure",), ("run_migrations",)),
        "migrations/script.py.mako": (("def upgrade",), ("def downgrade",)),
        "tests/integration/migrations/test_migrations.py": (
            ("def test_", "async def test_"),
            ("upgrade",),
            ("compare_metadata", "produce_migrations", "command.check", "alembic check"),
        ),
    }
    return all(any(option in text for option in alternatives) for alternatives in markers[name])


def _valid_revision(text: str) -> bool:
    return all(marker in text for marker in ("revision", "def upgrade", "def downgrade"))


def _valid_make_recipe(target: str, recipe: str) -> bool:
    required_fragments = {
        "migrate": ("alembic", "upgrade"),
        "makemigrations": ("alembic", "revision"),
        "migration-check": ("alembic", "check"),
    }
    return all(fragment in recipe for fragment in required_fragments[target])
