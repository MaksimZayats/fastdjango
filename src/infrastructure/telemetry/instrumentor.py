from dataclasses import dataclass

import logfire
from fastapi import FastAPI
from logfire.integrations.psycopg import CommenterOptions
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from infrastructure.telemetry.configurator import LogfireSettings


class InstrumentorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INSTRUMENTOR_")

    fastapi_excluded_urls: list[str] = Field(
        default_factory=lambda: [".*/v1/health"],
    )


@dataclass(kw_only=True)
class OpenTelemetryInstrumentor:
    _instrumentor_settings: InstrumentorSettings
    _logfire_settings: LogfireSettings

    def instrument_libraries(self) -> None:
        if not self._logfire_settings.is_enabled:
            return

        logfire.instrument_django(is_sql_commentor_enabled=True)
        logfire.instrument_celery(propagate_trace_context=True)
        logfire.instrument_requests()
        logfire.instrument_psycopg(
            enable_commenter=True,
            commenter_options=CommenterOptions(
                db_driver=True,
                dbapi_level=True,
            ),
        )
        logfire.instrument_httpx()
        logfire.instrument_redis()
        logfire.instrument_pydantic()

    def instrument_fastapi(self, app: FastAPI) -> None:
        if not self._logfire_settings.is_enabled:
            return

        logfire.instrument_fastapi(
            app,
            excluded_urls=self._instrumentor_settings.fastapi_excluded_urls,
        )
