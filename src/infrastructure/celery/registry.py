from dataclasses import dataclass
from typing import Any

from celery import Celery, Task


class TaskNotFoundError(Exception):
    pass


@dataclass(kw_only=True)
class BaseTasksRegistry:
    _celery_app: Celery

    def _get_task_by_name(self, name: str) -> Task[..., Any]:
        try:
            return self._celery_app.tasks[name]
        except KeyError as e:
            msg = f"Task with name '{name}' not found in registry."
            raise TaskNotFoundError(msg) from e
