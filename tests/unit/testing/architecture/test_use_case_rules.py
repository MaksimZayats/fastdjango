from __future__ import annotations

from pathlib import Path

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxRuleId,
    check_specx_architecture,
)


def test_return_dto_rule_ignores_non_use_case_execute_methods(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "demo_service" / "core" / "tasks" / "use_cases" / "count.py",
        "class Runner:\n"
        "    def execute(self) -> int:\n"
        "        return 1\n\n"
        "class CountTasksUseCase(BaseUseCase):\n"
        "    def execute(self) -> int:\n"
        "        return 1\n",
    )

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(SpecxRuleId.USE_CASES_RETURN_DTOS),
        )
    )

    assert [violation.symbol for violation in report.violations] == ["CountTasksUseCase"]


def test_command_location_rule_follows_transitive_foundation_bases(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "demo_service" / "foundation" / "command.py",
        "class ProjectCommand(BaseCommand):\n    pass\n",
    )
    _write(
        tmp_path / "src" / "demo_service" / "core" / "tasks" / "commands" / "create.py",
        "from demo_service.foundation.command import ProjectCommand\n\n"
        "class CreateTaskCommand(ProjectCommand):\n"
        "    pass\n",
    )
    _write(
        tmp_path / "src" / "demo_service" / "infrastructure" / "unrelated.py",
        "class ProjectCommand(object):\n    pass\n",
    )

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(
                SpecxRuleId.COMMAND_AND_QUERY_CLASSES_LIVE_WITH_USE_CASES
            ),
        )
    )

    assert [violation.symbol for violation in report.violations] == ["CreateTaskCommand"]


def test_command_location_rule_does_not_cross_module_name_collisions(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "demo_service" / "foundation" / "command.py",
        "class ProjectCommand(BaseCommand):\n    pass\n",
    )
    _write(
        tmp_path / "src" / "demo_service" / "infrastructure" / "unrelated.py",
        "class ProjectCommand(object):\n    pass\n",
    )
    _write(
        tmp_path / "src" / "demo_service" / "core" / "tasks" / "models" / "snapshot.py",
        "from demo_service.infrastructure.unrelated import ProjectCommand\n\n"
        "class TaskSnapshot(ProjectCommand):\n"
        "    pass\n",
    )

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(
                SpecxRuleId.COMMAND_AND_QUERY_CLASSES_LIVE_WITH_USE_CASES
            ),
        )
    )

    assert report.violations == ()


def test_query_mutation_rule_follows_transitive_query_bases(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "demo_service" / "foundation" / "query.py",
        "class ProjectQuery(BaseQuery):\n    pass\n",
    )
    _write(
        tmp_path / "src" / "demo_service" / "core" / "tasks" / "repositories" / "task.py",
        "class TaskRepository:\n    async def save(self, task):\n        pass\n",
    )
    _write(
        tmp_path / "src" / "demo_service" / "core" / "tasks" / "use_cases" / "get_task.py",
        "from demo_service.infrastructure.unrelated import ProjectQuery\n"
        "from demo_service.foundation.query import ProjectQuery\n\n"
        "class GetTaskQuery(ProjectQuery):\n"
        "    pass\n\n"
        "class GetTaskUseCase(BaseUseCase):\n"
        "    async def execute(self, *, query: GetTaskQuery) -> TaskDTO:\n"
        "        async with self.uow_manager as uow:\n"
        "            await uow.tasks.save(task)\n",
    )
    _write(
        tmp_path / "src" / "demo_service" / "infrastructure" / "unrelated.py",
        "class ProjectQuery(object):\n    pass\n",
    )

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(
                SpecxRuleId.QUERY_USE_CASES_DO_NOT_CALL_REPOSITORY_MUTATORS
            ),
        )
    )

    assert [violation.symbol for violation in report.violations] == ["GetTaskUseCase"]


def test_query_mutation_rule_does_not_cross_module_name_collisions(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "demo_service" / "foundation" / "query.py",
        "class ProjectQuery(BaseQuery):\n    pass\n",
    )
    _write(
        tmp_path / "src" / "demo_service" / "infrastructure" / "unrelated.py",
        "class ProjectQuery(object):\n    pass\n",
    )
    _write(
        tmp_path / "src" / "demo_service" / "core" / "tasks" / "repositories" / "task.py",
        "class TaskRepository:\n    async def save(self, task):\n        pass\n",
    )
    _write(
        tmp_path / "src" / "demo_service" / "core" / "tasks" / "use_cases" / "get_task.py",
        "from demo_service.foundation.query import ProjectQuery\n"
        "from demo_service.infrastructure.unrelated import ProjectQuery\n\n"
        "class GetTaskQuery(ProjectQuery):\n"
        "    pass\n\n"
        "class GetTaskUseCase(BaseUseCase):\n"
        "    async def execute(self, *, query: GetTaskQuery) -> TaskDTO:\n"
        "        async with self.uow_manager as uow:\n"
        "            await uow.tasks.save(task)\n",
    )

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(
                SpecxRuleId.QUERY_USE_CASES_DO_NOT_CALL_REPOSITORY_MUTATORS
            ),
        )
    )

    assert report.violations == ()


def test_one_use_case_per_module_rule_reports_ambiguous_module(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "demo_service" / "core" / "tasks" / "use_cases" / "manage.py",
        "class CreateTaskUseCase(BaseUseCase):\n    pass\n\n"
        "class CancelTaskUseCase(BaseUseCase):\n    pass\n",
    )

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(SpecxRuleId.USE_CASE_MODULES_DEFINE_ONE_USE_CASE),
        )
    )

    assert len(report.violations) == 1
    assert report.violations[0].message == "module defines 2 use cases; expected one"


def test_one_use_case_per_module_rule_reports_module_without_use_case(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "demo_service" / "core" / "tasks" / "use_cases" / "helpers.py",
        "def normalize_title(value: str) -> str:\n    return value.strip()\n",
    )

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=_disable_all_except(SpecxRuleId.USE_CASE_MODULES_DEFINE_ONE_USE_CASE),
        )
    )

    assert len(report.violations) == 1
    assert report.violations[0].message == "module defines 0 use cases; expected one"


def _disable_all_except(rule_id: SpecxRuleId) -> frozenset[SpecxRuleId]:
    return frozenset(candidate for candidate in SpecxRuleId if candidate != rule_id)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
