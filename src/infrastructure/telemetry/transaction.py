import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import logfire
from django.db import transaction
from logfire import LogfireSpan


@contextmanager
def traced_atomic(
    span_name: str = "database transaction",
    **span_attributes: Any,
) -> Generator[LogfireSpan]:
    """Context manager that wraps Django's transaction.atomic() with a Logfire span.

    Usage:
        with traced_atomic("create user and profile", user_id=user.pk):
            User.objects.create(...)
            Profile.objects.create(...)
    """
    with logfire.span(span_name, **span_attributes) as span:
        start = time.perf_counter()
        try:
            with transaction.atomic():
                yield span

            span.set_attribute("db.transaction.outcome", "commit")
            span.set_attribute(
                "db.transaction.duration_ms",
                (time.perf_counter() - start) * 1000,
            )
        except Exception as exc:
            span.record_exception(exc)
            span.set_attribute("db.transaction.outcome", "rollback")
            span.set_attribute(
                "db.transaction.duration_ms",
                (time.perf_counter() - start) * 1000,
            )
            raise
