from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class JWTServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JWT_")

    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15

    @property
    def access_token_expire(self) -> timedelta:
        return timedelta(minutes=self.access_token_expire_minutes)


@dataclass(kw_only=True)
class JWTService:
    EXPIRED_SIGNATURE_ERROR = jwt.ExpiredSignatureError
    INVALID_TOKEN_ERROR = jwt.InvalidTokenError

    _settings: JWTServiceSettings

    def issue_access_token(
        self,
        user_id: Any,
        **payload_kwargs: Any,
    ) -> str:
        iat = datetime.now(tz=UTC)
        payload = {
            "sub": str(user_id),
            "exp": iat + self._settings.access_token_expire,
            "iat": iat,
            "typ": "at+jwt",
            **payload_kwargs,
        }

        return jwt.encode(
            payload=payload,
            key=self._settings.secret_key.get_secret_value(),
            algorithm=self._settings.algorithm,
        )

    def decode_token(self, token: str) -> dict[str, Any]:
        return jwt.decode(
            jwt=token,
            key=self._settings.secret_key.get_secret_value(),
            algorithms=[self._settings.algorithm],
        )
