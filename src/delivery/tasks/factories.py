from dataclasses import dataclass, field

from celery import Celery

from configs.application import ApplicationSettings
from delivery.tasks.registry import TaskName, TasksRegistry
from delivery.tasks.settings import CelerySettings
from delivery.tasks.tasks.ping import PingTaskController
from infrastructure.redis.settings import RedisSettings


@dataclass(kw_only=True)
class CeleryAppFactory:
    _application_settings: ApplicationSettings
    _celery_settings: CelerySettings
    _redis_settings: RedisSettings
    _instance: Celery | None = field(default=None, init=False)

    def __call__(self) -> Celery:
        if self._instance is not None:
            return self._instance

        celery_app = Celery(
            "main",
            broker=self._redis_settings.url.get_secret_value(),
            backend=self._redis_settings.url.get_secret_value(),
        )

        self._configure_app(celery_app=celery_app)
        self._configure_beat_schedule(celery_app=celery_app)

        self._instance = celery_app
        return self._instance

    def _configure_app(self, celery_app: Celery) -> None:
        celery_app.conf.update(
            timezone=self._application_settings.time_zone,
            enable_utc=True,
            **self._celery_settings.model_dump(),
        )

    def _configure_beat_schedule(self, celery_app: Celery) -> None:
        celery_app.conf.beat_schedule = {
            "ping-every-minute": {
                "task": TaskName.PING,
                "schedule": 60.0,
            },
        }


@dataclass(kw_only=True)
class TasksRegistryFactory:
    _celery_app_factory: CeleryAppFactory
    _ping_controller: PingTaskController
    _instance: TasksRegistry | None = field(default=None, init=False)

    def __call__(self) -> TasksRegistry:
        if self._instance is not None:
            return self._instance

        celery_app = self._celery_app_factory()
        registry = TasksRegistry(_celery_app=celery_app)
        self._ping_controller.register(celery_app)

        self._instance = registry
        return self._instance
