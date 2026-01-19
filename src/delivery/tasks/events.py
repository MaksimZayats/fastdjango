from dataclasses import dataclass
from typing import Any

from celery.signals import beat_init, worker_init

from configs.application import ApplicationSettings
from infrastructure.delivery.controllers import Controller
from infrastructure.telemetry.configurator import LogfireConfigurator


@dataclass(kw_only=True)
class CeleryEvents(Controller):
    _application_settings: ApplicationSettings
    _logfire_configurator: LogfireConfigurator

    def register(self, registry: None = None) -> None:  # noqa: ARG002
        worker_init.connect()(self.worker_init)
        beat_init.connect()(self.beat_init)

    def worker_init(self, *_args: Any, **_kwargs: Any) -> None:
        self._logfire_configurator.configure(
            service_name="celery-worker",
            service_version=self._application_settings.version,
            environment=self._application_settings.environment,
        )

    def beat_init(self, *_args: Any, **_kwargs: Any) -> None:
        self._logfire_configurator.configure(
            service_name="celery-beat",
            service_version=self._application_settings.version,
            environment=self._application_settings.environment,
        )
