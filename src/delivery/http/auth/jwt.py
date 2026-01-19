from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Protocol, cast

from asgiref.sync import sync_to_async
from fastapi import HTTPException
from fastapi.requests import Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.user.models import User
from core.user.services.jwt import JWTService
from core.user.services.user import UserService


class AuthenticatedRequestState(Protocol):
    jwt_payload: dict[str, Any]
    user: User


class AuthenticatedRequest(Request):
    state: AuthenticatedRequestState  # type: ignore[bad-override, assignment]


@dataclass(kw_only=True)
class JWTAuthFactory:
    """Factory for creating JWT auth instances with optional permission checks.

    Example:
        factory = container.resolve(JWTAuthFactory)
        basic_auth = factory()  # No permission checks
        staff_auth = factory(require_staff=True)  # Requires is_staff=True
        admin_auth = factory(require_superuser=True)  # Requires is_superuser=True
    """

    _jwt_service: JWTService
    _user_service: UserService

    def __call__(
        self,
        *,
        require_staff: bool = False,
        require_superuser: bool = False,
    ) -> JWTAuth:
        """Create a JWT auth instance.

        Args:
            require_staff: If True, require user.is_staff to be True.
            require_superuser: If True, require user.is_superuser to be True.

        Returns:
            A JWTAuth instance configured with the specified permission checks.
        """
        if require_staff or require_superuser:
            return JWTAuthWithPermissions(
                jwt_service=self._jwt_service,
                user_service=self._user_service,
                require_staff=require_staff,
                require_superuser=require_superuser,
            )

        return JWTAuth(jwt_service=self._jwt_service, user_service=self._user_service)


class JWTAuth(HTTPBearer):
    def __init__(
        self,
        jwt_service: JWTService,
        user_service: UserService,
    ) -> None:
        super().__init__()
        self._jwt_service = jwt_service
        self._user_service = user_service

    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials | None:
        credentials = await super().__call__(request)
        if credentials is None:
            return None

        request = cast(AuthenticatedRequest, request)

        payload = self._get_token_payload(token=credentials.credentials)
        request.state.jwt_payload = payload

        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="Token payload missing 'sub' field",
            )

        user = await sync_to_async(
            self._user_service.get_active_user_by_id,
            thread_sensitive=False,
        )(user_id=user_id)

        if user is None:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="User not found",
            )

        request.state.user = user

        return credentials

    def _get_token_payload(self, token: str) -> dict[str, Any]:
        try:
            return self._jwt_service.decode_token(token=token)
        except self._jwt_service.EXPIRED_SIGNATURE_ERROR as e:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="Token has expired",
            ) from e
        except self._jwt_service.INVALID_TOKEN_ERROR as e:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="Invalid token",
            ) from e


class JWTAuthWithPermissions(JWTAuth):
    """JWT auth with optional is_staff/is_superuser checks."""

    def __init__(
        self,
        jwt_service: JWTService,
        user_service: UserService,
        *,
        require_staff: bool = False,
        require_superuser: bool = False,
    ) -> None:
        super().__init__(jwt_service=jwt_service, user_service=user_service)
        self._require_staff = require_staff
        self._require_superuser = require_superuser

    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials | None:
        credentials = await super().__call__(request)

        request = cast(AuthenticatedRequest, request)
        user = request.state.user

        if self._require_staff and not getattr(user, "is_staff", False):
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="Staff access required",
            )

        if self._require_superuser and not getattr(user, "is_superuser", False):
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="Superuser access required",
            )

        return credentials
