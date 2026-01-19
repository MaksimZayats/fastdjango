import logging
from dataclasses import dataclass

import anyio
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class AnyIOSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANYIO_")

    thread_limiter_tokens: int = 40


@dataclass(kw_only=True)
class AnyIOConfigurator:
    _settings: AnyIOSettings

    def configure(self) -> None:
        limiter = anyio.to_thread.current_default_thread_limiter()  # type: ignore[unresolved-attribute]
        limiter.total_tokens = self._settings.thread_limiter_tokens

        logger.info(
            "Configured AnyIO with thread_limiter_tokens=%d",
            self._settings.thread_limiter_tokens,
        )
