from __future__ import annotations

from pathlib import Path

import pytest

from specx.testing.architecture import SpecxArchitectureConfig, check_specx_architecture
from specx.testing.architecture.models import SpecxArchitectureReport
from specx.testing.architecture.rule_id import SpecxRuleId


@pytest.mark.parametrize(
    "fixture_body",
    [
        "    return get_container()\n",
        "    yield get_container()\n",
        ("    if feature_enabled:\n        return get_container()\n    return get_container()\n"),
        "    return get_container()\n    return object()\n",
    ],
)
def test_native_container_fixture_accepts_only_direct_project_factory_outcomes(
    tmp_path: Path,
    fixture_body: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture(name='container')\n"
        "def application_container(feature_enabled=False):\n" + fixture_body,
    )

    assert _check(tmp_path).violations == ()


@pytest.mark.parametrize(
    "fixture_body",
    [
        ("    if feature_enabled:\n        return get_container()\n    return object()\n"),
        "    yield object()\n",
        "    yield get_container()\n    return object()\n",
        "    return object()\n",
    ],
)
def test_native_container_fixture_rejects_any_reachable_non_project_outcome(
    tmp_path: Path,
    fixture_body: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container(feature_enabled=False):\n" + fixture_body,
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


def test_native_container_fixture_prunes_statically_unreachable_outcomes(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\n"
        "def container():\n"
        "    if 0:\n"
        "        return object()\n"
        "    if typing.TYPE_CHECKING:\n"
        "        return object()\n"
        "    while False:\n"
        "        return object()\n"
        "    return get_container()\n",
        import_typing=True,
    )

    assert _check(tmp_path).violations == ()


@pytest.mark.parametrize("location", ["test", "near-conftest"])
def test_exact_pytest_fixture_exposed_as_container_shadows_native_fixture(
    tmp_path: Path,
    location: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    shadow = (
        "import pytest\n\n"
        "@pytest.fixture(name='container')\n"
        "def fake_container():\n"
        "    return object()\n"
    )
    if location == "test":
        test_path = _test_path(tmp_path)
        _write(test_path, shadow + _test_source())
    else:
        _write(_test_path(tmp_path).parent / "conftest.py", shadow)

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


@pytest.mark.parametrize("location", ["test", "near-conftest"])
def test_plain_container_helpers_do_not_shadow_pytest_fixture(
    tmp_path: Path,
    location: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    helper = "def container():\n    return object()\n\n"
    if location == "test":
        test_path = _test_path(tmp_path)
        _write(test_path, helper + _test_source())
    else:
        _write(_test_path(tmp_path).parent / "conftest.py", helper)

    assert _check(tmp_path).violations == ()


@pytest.mark.parametrize(
    "fixture_decorator",
    [
        "@pytest.fixture",
        "@pytest.fixture(name='container')",
    ],
)
def test_class_local_container_fixture_shadows_native_fixture(
    tmp_path: Path,
    fixture_decorator: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    fixture_name = "container" if "name=" not in fixture_decorator else "fake_container"
    _write(
        _test_path(tmp_path),
        "import pytest\n"
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "class TestGraph:\n"
        f"    {fixture_decorator}\n"
        f"    def {fixture_name}(self):\n"
        "        return object()\n\n"
        "    def test_graph(self, container):\n"
        "        container.resolve(OrderService)\n",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


def test_class_local_container_fixture_does_not_shadow_native_module_test(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "import pytest\n"
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_graph(container):\n"
        "    container.resolve(OrderService)\n\n"
        "class TestUnrelated:\n"
        "    @pytest.fixture\n"
        "    def container(self):\n"
        "        return object()\n\n"
        "    def test_something_else(self, container):\n"
        "        assert container is not None\n",
    )

    assert _check(tmp_path).violations == ()


def test_container_proof_rejects_method_mutation_and_swallowed_resolution(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_mutated(container):\n"
        "    container.resolve = lambda target: object()\n"
        "    container.resolve(OrderService)\n\n"
        "def test_swallowed(container):\n"
        "    try:\n"
        "        container.resolve(OrderService)\n"
        "    except Exception:\n"
        "        pass\n",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


def test_native_container_fixture_rejects_reachable_implicit_none(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\n"
        "def container(feature_enabled):\n"
        "    if feature_enabled:\n"
        "        return get_container()\n",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


def test_skipped_container_resolution_is_not_evidence(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "import pytest\n"
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "@pytest.mark.skip(reason='disabled')\n"
        "def test_graph(container):\n"
        "    container.resolve(OrderService)\n",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


@pytest.mark.parametrize("scope", ["module", "class"])
@pytest.mark.parametrize(
    "marker",
    [
        "pytest.mark.skip(reason='disabled')",
        "pytest.mark.xfail(reason='disabled')",
    ],
)
def test_module_and_class_pytestmark_disable_container_evidence(
    tmp_path: Path,
    scope: str,
    marker: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    if scope == "module":
        source = (
            "import pytest\n"
            "from demo_service.core.orders.services.order import OrderService\n\n"
            f"pytestmark = {marker}\n\n"
            "def test_graph(container):\n"
            "    container.resolve(OrderService)\n"
        )
    else:
        source = (
            "import pytest\n"
            "from demo_service.core.orders.services.order import OrderService\n\n"
            "class TestGraph:\n"
            f"    pytestmark = {marker}\n\n"
            "    def test_graph(self, container):\n"
            "        container.resolve(OrderService)\n"
        )
    _write(_test_path(tmp_path), source)

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


@pytest.mark.parametrize(
    "module_outcome",
    [
        "import pytest\npytest.skip('disabled', allow_module_level=True)\n",
        "from pytest import xfail as stop_module\nstop_module('disabled')\n",
        "import pytest as pt\npt.importorskip('optional_dependency')\n",
        "import pytest\n",
    ],
)
def test_reachable_module_pytest_outcome_disables_container_evidence(
    tmp_path: Path,
    module_outcome: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    test_source = _test_source()
    source = (
        f"{module_outcome}{test_source}pytest.xfail('disabled')\n"
        if module_outcome == "import pytest\n"
        else f"{module_outcome}{test_source}"
    )
    _write(_test_path(tmp_path), source)

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


@pytest.mark.parametrize(
    "dead_outcome",
    [
        "if False:\n    pytest.skip('disabled', allow_module_level=True)\n",
        "True or pytest.xfail('disabled')\n",
        "False and pytest.importorskip('optional_dependency')\n",
        "pytest.skip('disabled', allow_module_level=True) if False else None\n",
    ],
)
def test_dead_module_pytest_outcome_preserves_container_evidence(
    tmp_path: Path,
    dead_outcome: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        f"import pytest\n{dead_outcome}{_test_source()}",
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
def test_import_time_definition_outcome_disables_container_evidence(
    tmp_path: Path,
    definition: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        f"import pytest\n{definition}\n{_test_source()}",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


def test_deferred_function_and_lambda_bodies_preserve_container_evidence(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "import pytest\n"
        "def deferred():\n"
        "    pytest.skip('disabled', allow_module_level=True)\n"
        "callback = lambda: pytest.xfail('disabled')\n\n"
        f"{_test_source()}",
    )

    assert _check(tmp_path).violations == ()


def test_conditionally_reachable_module_pytest_outcome_disables_container_evidence(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "import pytest\n"
        "if optional_dependency_enabled:\n"
        "    pytest.importorskip('optional_dependency')\n"
        f"{_test_source()}",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


@pytest.mark.parametrize(
    "class_body",
    [
        "    pytest.skip('disabled', allow_module_level=True)\n",
        "    pytest.importorskip('optional_dependency')\n",
        "    if optional_dependency_enabled:\n        pytest.xfail('disabled')\n",
        "    stop_module = pytest.skip\n    stop_module('disabled', allow_module_level=True)\n",
    ],
)
def test_reachable_class_body_pytest_outcome_disables_container_evidence(
    tmp_path: Path,
    class_body: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        f"import pytest\nclass ImportTimePolicy:\n{class_body}\n{_test_source()}",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


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
def test_dead_or_deferred_class_body_outcome_preserves_container_evidence(
    tmp_path: Path,
    class_body: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        f"import pytest\nclass ImportTimePolicy:\n{class_body}\n{_test_source()}",
    )

    assert _check(tmp_path).violations == ()


def test_keyword_skipif_disables_container_evidence(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "import pytest\n"
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "@pytest.mark.skipif(condition=True, reason='disabled')\n"
        "def test_graph(container):\n"
        "    container.resolve(OrderService)\n",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


def test_statically_false_xfail_still_proves_container_resolution(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "import pytest\n"
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "@pytest.mark.xfail(condition=False, reason='enabled')\n"
        "def test_graph(container):\n"
        "    container.resolve(OrderService)\n",
    )

    assert _check(tmp_path).violations == ()


@pytest.mark.parametrize(
    "terminal_call",
    [
        "pytest.skip('disabled')",
        "pytest.xfail('disabled')",
        "stop_test('disabled')",
    ],
)
def test_runtime_pytest_termination_makes_later_resolution_dead(
    tmp_path: Path,
    terminal_call: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "import pytest\n"
        "from pytest import skip as stop_test\n"
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_graph(container):\n"
        f"    {terminal_call}\n"
        "    container.resolve(OrderService)\n",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


@pytest.mark.parametrize(
    "body",
    [
        "    pytest.skip('disabled') or container.resolve(OrderService)\n",
        "    if pytest.xfail('disabled'):\n        container.resolve(OrderService)\n",
    ],
)
def test_runtime_pytest_termination_short_circuits_its_expression(
    tmp_path: Path,
    body: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "import pytest\n"
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_graph(container):\n"
        f"{body}",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


def test_exception_handler_does_not_catch_pytest_outcome_termination(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "import pytest\n"
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_graph(container):\n"
        "    try:\n"
        "        pytest.skip('disabled')\n"
        "    except Exception:\n"
        "        pass\n"
        "    container.resolve(OrderService)\n",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


@pytest.mark.parametrize("handler", ["BaseException", None])
def test_compatible_handler_catches_pytest_outcome_termination(
    tmp_path: Path,
    handler: str | None,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    except_clause = f"except {handler}:" if handler is not None else "except:"
    _write(
        _test_path(tmp_path),
        "import pytest\n"
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_graph(container):\n"
        "    try:\n"
        "        pytest.xfail('disabled')\n"
        f"    {except_clause}\n"
        "        pass\n"
        "    container.resolve(OrderService)\n",
    )

    assert _check(tmp_path).violations == ()


@pytest.mark.parametrize(
    "expression",
    [
        "True or container.resolve(OrderService)",
        "False and container.resolve(OrderService)",
        "container.resolve(OrderService) if False else None",
        "None if True else container.resolve(OrderService)",
    ],
)
def test_short_circuited_container_resolution_is_not_evidence(
    tmp_path: Path,
    expression: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_graph(container):\n"
        f"    {expression}\n",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


@pytest.mark.parametrize(
    "expression",
    [
        "False or container.resolve(OrderService)",
        "True and container.resolve(OrderService)",
        "container.resolve(OrderService) if True else None",
        "None if False else container.resolve(OrderService)",
    ],
)
def test_reachable_short_circuit_container_resolution_is_evidence(
    tmp_path: Path,
    expression: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_graph(container):\n"
        f"    {expression}\n",
    )

    assert _check(tmp_path).violations == ()


@pytest.mark.parametrize(
    "source",
    [
        (
            "from contextlib import suppress\n"
            "from demo_service.core.orders.services.order import OrderService\n\n"
            "def test_graph(container):\n"
            "    with suppress(Exception):\n"
            "        container.resolve(OrderService)\n"
        ),
        (
            "from unittest.mock import patch\n"
            "from demo_service.core.orders.services.order import OrderService\n\n"
            "def test_graph(container):\n"
            "    with patch.object(container, 'resolve', return_value=object()):\n"
            "        container.resolve(OrderService)\n"
        ),
    ],
)
def test_suppressed_or_patched_container_resolution_is_not_evidence(
    tmp_path: Path,
    source: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(_test_path(tmp_path), source)

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


def test_resolution_after_patch_scope_is_real_evidence(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "from unittest.mock import patch\n"
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_graph(container):\n"
        "    with patch.object(container, 'resolve', return_value=object()):\n"
        "        pass\n"
        "    container.resolve(OrderService)\n",
    )

    assert _check(tmp_path).violations == ()


def test_reraised_resolution_failure_still_proves_container_resolution(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_graph(container):\n"
        "    try:\n"
        "        container.resolve(OrderService)\n"
        "    except Exception:\n"
        "        raise\n",
    )

    assert _check(tmp_path).violations == ()


def test_dead_raise_does_not_make_swallowing_handler_valid(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_graph(container):\n"
        "    try:\n"
        "        container.resolve(OrderService)\n"
        "    except Exception:\n"
        "        return\n"
        "        raise\n",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


@pytest.mark.parametrize(
    "dead_prefix",
    [
        "    try:\n        return\n    finally:\n        pass\n",
        (
            "    try:\n"
            "        return\n"
            "    except Exception:\n"
            "        pass\n"
            "    finally:\n"
            "        pass\n"
        ),
        "    if enabled:\n        return\n    else:\n        return\n",
        "    match value:\n        case _:\n            return\n",
        "    while True:\n        return\n",
    ],
)
def test_exhaustive_terminal_control_flow_makes_later_resolution_dead(
    tmp_path: Path,
    dead_prefix: str,
) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_graph(container, enabled=False, value=None):\n"
        f"{dead_prefix}"
        "    container.resolve(OrderService)\n",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


def test_unreachable_container_resolution_is_not_evidence(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write_root_fixture(
        tmp_path,
        "@pytest.fixture\ndef container():\n    return get_container()\n",
    )
    _write(
        _test_path(tmp_path),
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_graph(container):\n"
        "    return\n"
        "    container.resolve(OrderService)\n",
    )

    assert [item.symbol for item in _check(tmp_path).violations] == ["OrderService"]


def _write_project(project_root: Path) -> None:
    _write(
        project_root / "src/demo_service/core/orders/services/order.py",
        "from specx.core.foundation.pure_service import BasePureService\n\n"
        "class OrderService(BasePureService):\n"
        "    pass\n",
    )
    _write(_test_path(project_root), _test_source())


def _write_root_fixture(
    project_root: Path,
    fixture: str,
    *,
    import_typing: bool = False,
) -> None:
    typing_import = "import typing\n" if import_typing else ""
    _write(
        project_root / "tests/unit/conftest.py",
        f"import pytest\n{typing_import}"
        "from demo_service.ioc.container import get_container\n\n"
        f"{fixture}",
    )


def _test_path(project_root: Path) -> Path:
    return project_root / "tests/unit/core/orders/services/test_order.py"


def _test_source() -> str:
    return (
        "from demo_service.core.orders.services.order import OrderService\n\n"
        "def test_graph(container):\n"
        "    container.resolve(OrderService)\n"
    )


def _check(project_root: Path) -> SpecxArchitectureReport:
    return check_specx_architecture(
        SpecxArchitectureConfig(
            project_root=project_root,
            package_name="demo_service",
            disabled_rules=frozenset(
                rule
                for rule in SpecxRuleId
                if rule != SpecxRuleId.TESTS_CORE_BEHAVIOR_RESOLVES_FROM_CONTAINER
            ),
        )
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
