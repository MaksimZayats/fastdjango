import logging
from dataclasses import dataclass

import logfire
from logfire import ScrubbingOptions
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class LogfireSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOGFIRE_")

    enabled: bool = False
    token: SecretStr | None = None

    @property
    def is_enabled(self) -> bool:
        return self.enabled and self.token is not None


@dataclass(kw_only=True)
class LogfireConfigurator:
    _logfire_settings: LogfireSettings

    def configure(
        self,
        service_name: str,
        service_version: str,
        environment: str,
    ) -> None:
        if not self._logfire_settings.is_enabled:
            logger.debug("Logfire is disabled; skipping configuration")
            return

        logfire.configure(
            service_name=service_name,
            service_version=service_version,
            environment=environment,
            token=self._logfire_settings.token.get_secret_value(),  # type: ignore[union-attr, possibly-missing-attribute]
            scrubbing=ScrubbingOptions(
                extra_patterns=[
                    "access_token",
                    "refresh_token",
                ],
            ),
        )

        logger.info("Logfire has been configured for service: %s", service_name)
        logfire.info("Logfire has been configured for service")
