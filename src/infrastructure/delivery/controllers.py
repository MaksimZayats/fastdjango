from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from infrastructure.telemetry.transaction import traced_atomic

_CONTROLLER_METHODS_EXCLUDE = ("register", "handle_exception")


@dataclass(kw_only=True)
class Controller(ABC):
    def __post_init__(self) -> None:
        self._wrap_methods()

    @abstractmethod
    def register(self, registry: Any) -> None: ...

    def handle_exception(self, exception: Exception) -> Any:
        raise exception

    def _wrap_methods(self) -> None:
        for attr_name in dir(self):
            attr = getattr(self, attr_name)

            if (
                callable(attr)
                and not hasattr(Controller, attr_name)
                and not attr_name.startswith("_")
                and attr_name not in _CONTROLLER_METHODS_EXCLUDE
            ):
                setattr(self, attr_name, self._wrap_route(attr))

    def _wrap_route(self, method: Callable[..., Any]) -> Callable[..., Any]:
        return self._add_exception_handler(method)

    def _add_exception_handler(self, method: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(method)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return method(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                return self.handle_exception(e)

        return wrapper


@dataclass(kw_only=True)
class TransactionController(Controller, ABC):
    def _wrap_route(self, method: Callable[..., Any]) -> Callable[..., Any]:
        method = self._add_transaction(method)
        return super()._wrap_route(method)

    def _add_transaction(self, method: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(method)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with traced_atomic(
                "controller transaction",
                controller=type(self).__name__,
                method=method.__name__,  # type: ignore[unresolved-attribute]
            ):
                return method(*args, **kwargs)

        return wrapper
