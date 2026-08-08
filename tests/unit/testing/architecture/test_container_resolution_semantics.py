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
