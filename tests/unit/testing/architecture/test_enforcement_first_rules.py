from __future__ import annotations

from pathlib import Path

import pytest

from specx.testing.architecture import (
    SpecxArchitectureConfig,
    SpecxArchitectureReport,
    SpecxConfigurationError,
    SpecxRuleId,
    check_specx_architecture,
)


def test_use_case_orchestration_resolves_aliases_constructors_and_allowlist(
    tmp_path: Path,
) -> None:
    path = _source(tmp_path, "core/orders/use_cases/place_order.py")
    _write(
        path,
        "from asyncio import gather as join\n"
        "from diwire import Injected\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class OrderDTO:\n    pass\n\n"
        "class OrderService:\n    async def place(self, *, command: object) -> OrderDTO: ...\n\n"
        "class PlaceOrderUseCase(BaseUseCase):\n"
        "    service: Injected[OrderService]\n"
        "    async def execute(self, *, command: object) -> OrderDTO:\n"
        "        placed = self.service.place(command=command)\n"
        "        await join(placed)\n"
        "        return OrderDTO()\n",
    )

    rejected = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )
    allowed = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
        allowed_use_case_functions=frozenset({"asyncio.gather"}),
    )

    assert [item.message for item in rejected.violations] == [
        "direct call 'asyncio.gather' is not an approved constructor or collaborator call"
    ]
    assert allowed.violations == ()


def test_ambient_call_has_one_diagnostic_owner(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/place_order.py"),
        "from datetime import datetime as Clock\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class PlaceOrderUseCase(BaseUseCase):\n"
        "    def execute(self, *, command: object) -> object:\n"
        "        return Clock.now()\n",
    )
    enabled = {
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    }
    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=frozenset(set(SpecxRuleId) - enabled),
        )
    )

    assert [item.rule_id for item in report.violations] == [
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS
    ]


def test_services_may_call_deterministic_local_functions(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/price_service.py"),
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "def add_tax(value: int) -> int:\n    return value + 1\n\n"
        "class PriceService(BasePureService):\n"
        "    def total(self, *, value: int) -> int:\n"
        "        return add_tax(value)\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS)

    assert report.violations == ()


def test_ambient_rule_resolves_path_objects_and_environment_methods(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/file_service.py"),
        "import os\n"
        "from pathlib import Path as FilePath\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class FileService(BaseEffectService):\n"
        "    def load(self, *, name: str) -> str:\n"
        "        path = FilePath(name)\n"
        "        return path.read_text() + os.environ.get('SUFFIX', '')\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS)

    assert len(report.violations) == 2


def test_use_case_allows_manager_owned_unit_of_work_calls(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/place_order.py"),
        "from diwire import Injected\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class OrderUnitOfWorkManager:\n    pass\n\n"
        "class PlaceOrderUseCase(BaseUseCase):\n"
        "    manager: Injected[OrderUnitOfWorkManager]\n"
        "    async def execute(self, *, command: object) -> object:\n"
        "        async with self.manager() as uow:\n"
        "            await uow.orders.add(command)\n"
        "        return command\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert report.violations == ()


def test_core_contract_requires_all_dataclass_flags_and_inheritance(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/dtos/order.py"),
        "from dataclasses import dataclass\n"
        "from specx.core.foundation.dto import BaseDTO\n\n"
        "class ProjectDTO(BaseDTO):\n    pass\n\n"
        "@dataclass(frozen=True, kw_only=True)\n"
        "class OrderDTO(ProjectDTO):\n    order_id: str\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.CORE_CONTRACTS_USE_IMMUTABLE_DATACLASSES)

    assert {item.symbol for item in report.violations} == {"ProjectDTO", "OrderDTO"}

    _write(
        _source(tmp_path, "core/orders/dtos/order.py"),
        "from dataclasses import dataclass\n"
        "from specx.core.foundation.dto import BaseDTO\n\n"
        "@dataclass(frozen=True, kw_only=True, slots=True)\n"
        "class OrderDTO(BaseDTO):\n    order_id: str\n",
    )
    accepted = _check_only(tmp_path, SpecxRuleId.CORE_CONTRACTS_USE_IMMUTABLE_DATACLASSES)
    assert accepted.violations == ()


def test_core_rejects_pydantic_and_environment_but_allows_typed_values(tmp_path: Path) -> None:
    path = _source(tmp_path, "core/orders/services/order_service.py")
    _write(path, "from pydantic import BaseModel\nimport os\nVALUE = os.environ['X']\n")
    rejected = _check_only(tmp_path, SpecxRuleId.CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC)
    _write(path, "RETRY_LIMIT: int = 3\n")
    accepted = _check_only(tmp_path, SpecxRuleId.CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC)

    assert len(rejected.violations) == 2
    assert accepted.violations == ()


def test_service_public_arguments_are_keyword_only(tmp_path: Path) -> None:
    path = _source(tmp_path, "core/orders/services/price_service.py")
    _write(
        path,
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class PriceService(BasePureService):\n"
        "    def total(self, price: int, *, quantity: int) -> int:\n"
        "        return price * quantity\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS)

    assert len(report.violations) == 1
    assert "price" in report.violations[0].message

    _write(
        path,
        path.read_text(encoding="utf-8").replace(
            "def total(self, price: int, *, quantity: int)",
            "def total(self, *, price: int, quantity: int)",
        ),
    )
    assert (
        _check_only(tmp_path, SpecxRuleId.SERVICE_METHODS_USE_KEYWORD_ONLY_ARGUMENTS).violations
        == ()
    )


def test_every_behavior_in_mirrored_module_resolves_from_container(tmp_path: Path) -> None:
    _write_native_container_fixture(tmp_path)
    _write(
        _source(tmp_path, "core/orders/services/order_service.py"),
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class FirstService(BasePureService):\n    pass\n\n"
        "class SecondService(BasePureService):\n    pass\n",
    )
    test_path = tmp_path / "tests/unit/core/orders/services/test_order_service.py"
    _write(
        test_path,
        "from demo_service.core.orders.services.order_service import (\n"
        "    FirstService, SecondService as OtherService,\n"
        ")\n\n"
        "def test_graph(container):\n"
        "    container.resolve(FirstService)\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.TESTS_CORE_BEHAVIOR_RESOLVES_FROM_CONTAINER)
    _write(
        test_path,
        test_path.read_text(encoding="utf-8") + "    container.resolve(OtherService)\n",
    )
    accepted = _check_only(tmp_path, SpecxRuleId.TESTS_CORE_BEHAVIOR_RESOLVES_FROM_CONTAINER)

    assert [item.symbol for item in report.violations] == ["SecondService"]
    assert accepted.violations == ()


def test_function_injection_rejected_but_ordinary_fixture_allowed(tmp_path: Path) -> None:
    path = tmp_path / "tests/unit/test_handler.py"
    _write(
        path,
        "from diwire import Injected\n\ndef test_bad(service: Injected[object]):\n    pass\n",
    )
    rejected = _check_only(tmp_path, SpecxRuleId.DIWIRE_NO_FUNCTION_INJECTION)
    _write(path, "def test_ok(container):\n    pass\n")
    accepted = _check_only(tmp_path, SpecxRuleId.DIWIRE_NO_FUNCTION_INJECTION)

    assert len(rejected.violations) == 1
    assert accepted.violations == ()


def test_delivery_foundation_subclass_must_live_under_delivery(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/controllers/order.py"),
        "from specx.delivery.foundation.controller import BaseController\n\n"
        "class OrderController(BaseController):\n    pass\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.DELIVERY_FOUNDATION_CLASSES_LIVE_UNDER_DELIVERY,
    )

    assert len(report.violations) == 1

    delivery_path = _source(tmp_path, "delivery/http/controllers/order.py")
    _write(delivery_path, _source(tmp_path, "core/orders/controllers/order.py").read_text())
    _source(tmp_path, "core/orders/controllers/order.py").unlink()
    assert (
        _check_only(
            tmp_path, SpecxRuleId.DELIVERY_FOUNDATION_CLASSES_LIVE_UNDER_DELIVERY
        ).violations
        == ()
    )


def test_sqlalchemy_model_placement_and_alembic_surface(tmp_path: Path) -> None:
    path = _source(tmp_path, "models/order.py")
    source = (
        "from specx.infrastructure.foundation.sqlalchemy_model import BaseSQLAlchemyModel\n\n"
        "class OrderModel(BaseSQLAlchemyModel):\n    pass\n"
    )
    _write(path, source)
    placement = _check_only(
        tmp_path,
        SpecxRuleId.SQLALCHEMY_MODELS_LIVE_UNDER_SCOPE_INFRASTRUCTURE,
    )
    required = _check_only(tmp_path, SpecxRuleId.SQLALCHEMY_MODELS_REQUIRE_ALEMBIC)
    _write(_source(tmp_path, "core/orders/infrastructure/sqlalchemy/models/order.py"), source)
    path.unlink()
    placed = _check_only(
        tmp_path,
        SpecxRuleId.SQLALCHEMY_MODELS_LIVE_UNDER_SCOPE_INFRASTRUCTURE,
    )

    assert len(placement.violations) == 1
    assert len(required.violations) == 1
    assert placed.violations == ()

    _write(tmp_path / "alembic.ini", "[alembic]\nscript_location = migrations\n")
    _write(
        tmp_path / "migrations/env.py",
        "def run_migrations_online():\n    context.configure(connection=connection)\n",
    )
    _write(
        tmp_path / "migrations/script.py.mako",
        "def upgrade(): ...\ndef downgrade(): ...\n",
    )
    _write(
        tmp_path / "migrations/versions/0001_orders.py",
        "revision = '0001'\ndef upgrade(): ...\ndef downgrade(): ...\n",
    )
    _write(
        tmp_path / "tests/integration/migrations/test_migrations.py",
        "def test_upgrade_and_drift():\n"
        "    command.upgrade(config, 'head')\n"
        "    compare_metadata(context, metadata)\n",
    )
    _write(
        tmp_path / "Makefile",
        "migrate:\n\tuv run alembic upgrade head\n\n"
        "makemigrations:\n\tuv run alembic revision --autogenerate\n\n"
        "migration-check:\n\tuv run alembic check\n",
    )
    assert _check_only(tmp_path, SpecxRuleId.SQLALCHEMY_MODELS_REQUIRE_ALEMBIC).violations == ()


def test_use_case_call_analysis_handles_qualified_constructors_and_uppercase_helpers(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/dtos/result.py"),
        "class ResultDTO:\n    pass\n",
    )
    _write(
        _source(tmp_path, "core/orders/use_cases/place_order.py"),
        "from demo_service.core.orders import dtos\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "def Normalize(value: object) -> object:\n    return value\n\n"
        "class PlaceOrderUseCase(BaseUseCase):\n"
        "    def execute(self, *, command: object) -> object:\n"
        "        Normalize(command)\n"
        "        return dtos.result.ResultDTO()\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert [item.message for item in report.violations] == [
        "direct call 'demo_service.core.orders.use_cases.place_order.Normalize' is not an "
        "approved constructor or collaborator call"
    ]


def test_use_case_call_analysis_handles_local_imports_shadowing_and_builtins(
    tmp_path: Path,
) -> None:
    path = _source(tmp_path, "core/orders/use_cases/place_order.py")
    _write(
        path,
        "import time\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class PlaceOrderUseCase(BaseUseCase):\n"
        "    def execute(self, *, command: object, time: object) -> object:\n"
        "        time.time()\n"
        "        from datetime import datetime as LocalClock\n"
        "        LocalClock.now()\n"
        "        return len([command])\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
    )
    orchestration = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
        allowed_use_case_functions=frozenset({"builtins.len"}),
    )

    assert len(report.violations) == 1
    assert "datetime.datetime.now" in report.violations[0].message
    assert len(orchestration.violations) == 1
    assert "<local>.time.time" in orchestration.violations[0].message


def test_ambient_rule_catches_os_path_fields_derived_paths_and_environment_aliases(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/file_service.py"),
        "import os\n"
        "from os import environ as runtime_environment\n"
        "from pathlib import Path\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class FileService(BaseEffectService):\n"
        "    root: Path\n"
        "    def load(self, *, name: str) -> str:\n"
        "        child = self.root / name\n"
        "        os.remove(child)\n"
        "        return child.read_text() + runtime_environment['SUFFIX']\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS)

    assert len(report.violations) == 3


def test_core_configuration_scans_init_and_avoids_behavior_duplicate(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/__init__.py"),
        "from pydantic import BaseModel\n",
    )
    _write(
        _source(tmp_path, "core/orders/services/env_service.py"),
        "import os\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class EnvService(BaseEffectService):\n"
        "    def value(self) -> str:\n"
        "        return os.getenv('VALUE', '')\n",
    )
    enabled = {
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
        SpecxRuleId.CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC,
    }

    report = check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            disabled_rules=frozenset(set(SpecxRuleId) - enabled),
        )
    )

    assert [item.rule_id for item in report.violations] == [
        SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS,
        SpecxRuleId.CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC,
    ]


def test_path_qualified_inheritance_ignores_same_named_unrelated_classes(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/a/dtos/shared.py"),
        "from specx.core.foundation.dto import BaseDTO\n\nclass Shared(BaseDTO):\n    pass\n",
    )
    _write(_source(tmp_path, "core/z/value.py"), "class Shared:\n    pass\n")

    report = _check_only(tmp_path, SpecxRuleId.CORE_CONTRACTS_USE_IMMUTABLE_DATACLASSES)

    assert [item.symbol for item in report.violations] == ["Shared"]


def test_use_case_accepts_inherited_injected_collaborator(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/foundation/order_use_case.py"),
        "from diwire import Injected\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class OrderService:\n"
        "    def run(self, *, value: object) -> object: ...\n\n"
        "class BaseOrderUseCase(BaseUseCase):\n"
        "    service: Injected[OrderService]\n",
    )
    _write(
        _source(tmp_path, "core/orders/use_cases/place_order.py"),
        "from demo_service.core.orders.foundation.order_use_case import BaseOrderUseCase\n\n"
        "class PlaceOrderUseCase(BaseOrderUseCase):\n"
        "    def execute(self, *, command: object) -> object:\n"
        "        return self.service.run(value=command)\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert report.violations == ()


def test_container_resolution_requires_exact_concrete_target(tmp_path: Path) -> None:
    _write_native_container_fixture(tmp_path)
    _write(
        _source(tmp_path, "core/orders/services/order.py"),
        "from abc import abstractmethod\n"
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class AbstractService(BasePureService):\n"
        "    @abstractmethod\n"
        "    def run(self) -> None: ...\n\n"
        "class OrderService(BasePureService):\n    pass\n",
    )
    _write(
        _source(tmp_path, "core/other/services/order.py"),
        "class OrderService:\n    pass\n",
    )
    _write(
        tmp_path / "tests/unit/core/orders/services/test_order.py",
        "from demo_service.core.other.services.order import OrderService\n\n"
        "def test_graph(container):\n"
        "    container.resolve(OrderService)\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.TESTS_CORE_BEHAVIOR_RESOLVES_FROM_CONTAINER)

    assert [item.symbol for item in report.violations] == ["OrderService"]


def test_function_injection_detects_decorators_methods_and_exact_annotations(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "tests/unit/test_handler.py",
        "from diwire import Injected as Wired, resolver_context as context\n\n"
        "class NotInjected:\n"
        "    def __class_getitem__(cls, item): return cls\n\n"
        "@context.inject\n"
        "def decorated() -> None: pass\n\n"
        "class Handler:\n"
        "    def bad(self, service: Wired[object]) -> None: pass\n"
        "    def ok(self, value: NotInjected[object]) -> None: pass\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.DIWIRE_NO_FUNCTION_INJECTION)

    assert {item.symbol for item in report.violations} == {"decorated", "bad"}


def test_foundation_paths_do_not_hide_concrete_delivery_or_sql_models(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "foundation/sqlalchemy_model.py"),
        "from specx.infrastructure.foundation.sqlalchemy.model import BaseSQLAlchemyModel\n\n"
        "class BaseProjectModel(BaseSQLAlchemyModel):\n    pass\n\n"
        "class HiddenModel(BaseProjectModel):\n    pass\n",
    )
    _write(
        _source(tmp_path, "core/orders/foundation/controller.py"),
        "from specx.delivery.foundation.controller import BaseController\n\n"
        "class HiddenController(BaseController):\n    pass\n",
    )

    sql = _check_only(
        tmp_path,
        SpecxRuleId.SQLALCHEMY_MODELS_LIVE_UNDER_SCOPE_INFRASTRUCTURE,
    )
    delivery = _check_only(
        tmp_path,
        SpecxRuleId.DELIVERY_FOUNDATION_CLASSES_LIVE_UNDER_DELIVERY,
    )
    alembic = _check_only(tmp_path, SpecxRuleId.SQLALCHEMY_MODELS_REQUIRE_ALEMBIC)

    assert [item.symbol for item in sql.violations] == ["HiddenModel"]
    assert [item.symbol for item in delivery.violations] == ["HiddenController"]
    assert len(alembic.violations) == 1


def test_alembic_rule_rejects_placeholder_files_and_recipes(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/infrastructure/sqlalchemy/models/order.py"),
        "from specx.infrastructure.foundation.sqlalchemy.model import BaseSQLAlchemyModel\n\n"
        "class OrderModel(BaseSQLAlchemyModel):\n    pass\n",
    )
    for path in (
        tmp_path / "alembic.ini",
        tmp_path / "migrations/env.py",
        tmp_path / "migrations/script.py.mako",
        tmp_path / "migrations/versions/0001.py",
        tmp_path / "tests/integration/migrations/test_migrations.py",
    ):
        _write(path, "# placeholder\n")
    _write(
        tmp_path / "Makefile",
        "migrate:\n\t@true\nmakemigrations:\n\t@true\nmigration-check:\n\t@true\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.SQLALCHEMY_MODELS_REQUIRE_ALEMBIC)

    assert len(report.violations) == 1
    assert "placeholder" in report.violations[0].message
    assert "without Alembic recipes" in report.violations[0].message


def test_statement_order_aliases_preserve_ambient_and_diwire_ownership(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/services/time_service.py"),
        "import time\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class TimeService(BaseEffectService):\n"
        "    def current(self) -> float:\n"
        "        now = time.time\n"
        "        return now()\n",
    )
    _write(
        tmp_path / "tests/unit/test_handler.py",
        "from diwire import resolver_context\n\n"
        "inject = resolver_context.inject\n\n"
        "@inject\n"
        "def handler() -> None: pass\n",
    )

    ambient = _check_only(tmp_path, SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS)
    injection = _check_only(tmp_path, SpecxRuleId.DIWIRE_NO_FUNCTION_INJECTION)

    assert len(ambient.violations) == 1
    assert "time.time" in ambient.violations[0].message
    assert [item.symbol for item in injection.violations] == ["handler"]


def test_use_case_accepts_collaborator_alias_but_rejects_injected_callable(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/place_order.py"),
        "from collections.abc import Callable\n"
        "from diwire import Injected\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class Worker:\n"
        "    def run(self, *, value: object) -> object: ...\n\n"
        "class PlaceOrderUseCase(BaseUseCase):\n"
        "    worker: Injected[Worker]\n"
        "    formatter: Injected[Callable[[str], str]]\n"
        "    def execute(self, *, command: object) -> object:\n"
        "        worker = self.worker\n"
        "        worker.run(value=command)\n"
        "        return self.formatter('done')\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert len(report.violations) == 1
    assert "self.formatter" in report.violations[0].message


def test_ambient_rule_catches_process_random_filesystem_and_optional_paths(
    tmp_path: Path,
) -> None:
    _write(
        _source(tmp_path, "core/orders/services/runtime_service.py"),
        "import io\nimport os\nimport sys\n"
        "from pathlib import Path\n"
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class RuntimeService(BaseEffectService):\n"
        "    def inspect(self, *, path: Path | None) -> object:\n"
        "        os.urandom(8)\n"
        "        os.path.exists('x')\n"
        "        io.open('x')\n"
        "        if path is not None:\n"
        "            path.read_text()\n"
        "        return sys.argv\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.CORE_BEHAVIOR_NO_AMBIENT_RUNTIME_ACCESS)

    assert len(report.violations) == 5


def test_deterministic_stdlib_value_constructors_are_allowed(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/use_cases/total.py"),
        "from decimal import Decimal\n"
        "from specx.core.foundation.use_case import BaseUseCase\n\n"
        "class TotalUseCase(BaseUseCase):\n"
        "    def execute(self, *, query: object) -> Decimal:\n"
        "        return Decimal('1.25')\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.USE_CASES_ORCHESTRATE_THROUGH_COLLABORATORS,
    )

    assert report.violations == ()


def test_abstract_inheritance_and_base_prefix_are_classified_precisely(tmp_path: Path) -> None:
    _write_native_container_fixture(tmp_path)
    _write(
        _source(tmp_path, "core/orders/services/order.py"),
        "from abc import abstractmethod\n"
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class AbstractOrderService(BasePureService):\n"
        "    @abstractmethod\n"
        "    def run(self) -> None: ...\n\n"
        "class PendingOrderService(AbstractOrderService):\n    pass\n\n"
        "class BaseballService(BasePureService):\n    pass\n",
    )
    _write(
        tmp_path / "tests/unit/core/orders/services/test_order.py",
        "from demo_service.core.orders.services.order import BaseballService\n\n"
        "def test_graph(container):\n"
        "    container.resolve(BaseballService)\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.TESTS_CORE_BEHAVIOR_RESOLVES_FROM_CONTAINER)

    assert report.violations == ()


@pytest.mark.parametrize("escape", ["nested", "parametrized", "local-fixture"])
def test_container_resolution_requires_executed_native_fixture_use(
    tmp_path: Path,
    escape: str,
) -> None:
    _write_native_container_fixture(tmp_path)
    _write(
        _source(tmp_path, "core/orders/services/order.py"),
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class OrderService(BasePureService):\n    pass\n",
    )
    test_path = tmp_path / "tests/unit/core/orders/services/test_order.py"
    source = {
        "nested": (
            "from demo_service.core.orders.services.order import OrderService\n\n"
            "def test_graph(container):\n"
            "    def never_called():\n"
            "        container.resolve(OrderService)\n"
            "    del never_called\n"
        ),
        "parametrized": (
            "import pytest\n"
            "from demo_service.core.orders.services.order import OrderService\n\n"
            "@pytest.mark.parametrize('container', [object()])\n"
            "def test_graph(container):\n"
            "    container.resolve(OrderService)\n"
        ),
        "local-fixture": (
            "import pytest\n"
            "from demo_service.core.orders.services.order import OrderService\n\n"
            "@pytest.fixture\n"
            "def container(): return object()\n\n"
            "def test_graph(container):\n"
            "    container.resolve(OrderService)\n"
        ),
    }[escape]
    _write(test_path, source)

    report = _check_only(tmp_path, SpecxRuleId.TESTS_CORE_BEHAVIOR_RESOLVES_FROM_CONTAINER)

    assert [item.symbol for item in report.violations] == ["OrderService"]


def test_core_rejects_project_wrapped_pydantic_types(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "contracts.py"),
        "from pydantic import BaseModel\n\nclass SharedRequest(BaseModel):\n    pass\n",
    )
    _write(
        _source(tmp_path, "core/orders/services/order.py"),
        "from demo_service.contracts import SharedRequest\n\n"
        "def handle(request: SharedRequest) -> None: pass\n",
    )

    report = _check_only(tmp_path, SpecxRuleId.CORE_NO_RUNTIME_CONFIGURATION_OR_PYDANTIC)

    assert len(report.violations) == 1
    assert "project Pydantic" in report.violations[0].message


def test_abstract_delivery_foundation_must_still_live_under_delivery(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/orders/foundation/orders_controller.py"),
        "from abc import abstractmethod\n"
        "from specx.delivery.foundation.controller import BaseController\n\n"
        "class BaseOrdersController(BaseController):\n"
        "    @abstractmethod\n"
        "    def register(self) -> None: ...\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.DELIVERY_FOUNDATION_CLASSES_LIVE_UNDER_DELIVERY,
    )

    assert len(report.violations) == 1


def test_same_named_services_do_not_corrupt_path_qualified_inheritance(tmp_path: Path) -> None:
    _write(
        _source(tmp_path, "core/a/services/order.py"),
        "import random\n"
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class OrderService(BasePureService):\n"
        "    def pick(self) -> float:\n"
        "        return random.random()\n",
    )
    _write(
        _source(tmp_path, "core/z/services/order.py"),
        "from specx.core.foundation.effect_service import BaseEffectService\n\n"
        "class OrderService(BaseEffectService):\n    pass\n",
    )

    report = _check_only(
        tmp_path,
        SpecxRuleId.PURE_SERVICES_DO_NOT_DEPEND_ON_IO_OR_RUNTIME_STATE,
    )

    assert len(report.violations) == 1
    assert report.violations[0].path == _source(tmp_path, "core/a/services/order.py")


@pytest.mark.parametrize("name", ["gather", "asyncio.*", "asyncio..gather", "class.call"])
def test_allowed_function_names_must_be_exact_qualified_names(
    tmp_path: Path,
    name: str,
) -> None:
    with pytest.raises(SpecxConfigurationError, match="exact dotted Python names"):
        SpecxArchitectureConfig(
            project_root=tmp_path,
            package_name="demo_service",
            allowed_use_case_functions=frozenset({name}),
        )


def _check_only(
    project_root: Path,
    rule_id: SpecxRuleId,
    *,
    allowed_use_case_functions: frozenset[str] = frozenset(),
) -> SpecxArchitectureReport:
    return check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=project_root,
            package_name="demo_service",
            disabled_rules=frozenset(
                candidate for candidate in SpecxRuleId if candidate != rule_id
            ),
            allowed_use_case_functions=allowed_use_case_functions,
        )
    )


def _source(project_root: Path, relative: str) -> Path:
    return project_root / "src/demo_service" / relative


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_native_container_fixture(project_root: Path) -> None:
    _write(
        project_root / "tests/unit/conftest.py",
        "import pytest\n"
        "from demo_service.ioc.container import get_container\n\n"
        "@pytest.fixture\n"
        "def container():\n"
        "    return get_container()\n",
    )
