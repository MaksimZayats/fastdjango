import logging
from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated, Any

from annotated_types import Len
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from throttled import rate_limiter

from core.user.services.jwt import JWTService
from core.user.services.refresh_session import (
    ExpiredRefreshTokenError,
    InvalidRefreshTokenError,
    RefreshSessionService,
    RefreshTokenError,
)
from core.user.services.user import UserService
from delivery.http.auth.jwt import AuthenticatedRequest, JWTAuthFactory
from delivery.http.services.request import RequestInfoService
from delivery.http.services.throttler import IPThrottlerFactory, UserThrottlerFactory
from infrastructure.delivery.controllers import Controller, TransactionController

logger = logging.getLogger(__name__)


class IssueTokenRequestSchema(BaseModel):
    username: str
    password: str


class RefreshTokenRequestSchema(BaseModel):
    refresh_token: str


class TokenResponseSchema(BaseModel):
    access_token: str
    refresh_token: str


@dataclass(kw_only=True)
class UserTokenController(TransactionController):
    _jwt_auth_factory: JWTAuthFactory
    _jwt_service: JWTService
    _request_info_service: RequestInfoService

    _ip_throttler_factory: IPThrottlerFactory
    _user_throttler_factory: UserThrottlerFactory

    _refresh_token_service: RefreshSessionService
    _user_service: UserService

    def __post_init__(self) -> None:
        self._jwt_auth = self._jwt_auth_factory()
        super().__post_init__()

    def register(self, registry: APIRouter) -> None:
        registry.add_api_route(
            path="/v1/users/me/token",
            endpoint=self.issue_user_token,
            methods=["POST"],
            dependencies=[
                Depends(self._ip_throttler_factory(quota=rate_limiter.per_min(10))),
            ],
            response_model=TokenResponseSchema,
        )

        registry.add_api_route(
            path="/v1/users/me/token/refresh",
            endpoint=self.refresh_user_token,
            methods=["POST"],
            dependencies=[
                Depends(self._ip_throttler_factory(quota=rate_limiter.per_min(10))),
            ],
            response_model=TokenResponseSchema,
        )

        registry.add_api_route(
            path="/v1/users/me/token/revoke",
            endpoint=self.revoke_refresh_token,
            methods=["POST"],
            dependencies=[
                Depends(self._jwt_auth),
                Depends(self._ip_throttler_factory(quota=rate_limiter.per_min(10))),
                Depends(self._user_throttler_factory(quota=rate_limiter.per_min(10))),
            ],
        )

    def issue_user_token(
        self,
        request: Request,
        body: IssueTokenRequestSchema,
    ) -> TokenResponseSchema:
        user = self._user_service.get_user_by_username_and_password(
            username=body.username,
            password=body.password,
        )

        if user is None:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="Invalid username or password",
            )

        access_token = self._jwt_service.issue_access_token(user_id=user.pk)
        refresh_session = self._refresh_token_service.create_refresh_session(
            user=user,
            user_agent=self._request_info_service.get_user_agent(request=request),
            ip_address=self._request_info_service.get_user_ip(request=request),
        )

        return TokenResponseSchema(
            access_token=access_token,
            refresh_token=refresh_session.refresh_token,
        )

    def refresh_user_token(
        self,
        body: RefreshTokenRequestSchema,
    ) -> TokenResponseSchema:
        rotated_session = self._refresh_token_service.rotate_refresh_token(
            refresh_token=body.refresh_token,
        )

        access_token = self._jwt_service.issue_access_token(
            user_id=rotated_session.session.user.pk,
        )

        return TokenResponseSchema(
            access_token=access_token,
            refresh_token=rotated_session.refresh_token,
        )

    def revoke_refresh_token(
        self,
        request: AuthenticatedRequest,
        body: RefreshTokenRequestSchema,
    ) -> None:
        self._refresh_token_service.revoke_refresh_token(
            refresh_token=body.refresh_token,
            user=request.state.user,
        )

    def handle_exception(self, exception: Exception) -> Any:
        if isinstance(exception, InvalidRefreshTokenError):
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="Invalid refresh token",
            ) from exception

        if isinstance(exception, ExpiredRefreshTokenError):
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="Refresh token expired or revoked",
            ) from exception

        if isinstance(exception, RefreshTokenError):
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="Refresh token error",
            ) from exception

        return super().handle_exception(exception)


class CreateUserRequestSchema(BaseModel):
    email: EmailStr
    username: Annotated[str, Len(max_length=150)]
    first_name: Annotated[str, Len(max_length=150)]
    last_name: Annotated[str, Len(max_length=150)]
    password: Annotated[str, Len(max_length=128)]


class UserSchema(BaseModel):
    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    is_staff: bool
    is_superuser: bool


@dataclass(kw_only=True)
class UserController(Controller):
    _jwt_auth_factory: JWTAuthFactory
    _user_service: UserService

    def __post_init__(self) -> None:
        self._jwt_auth = self._jwt_auth_factory()
        self._staff_jwt_auth = self._jwt_auth_factory(require_staff=True)
        super().__post_init__()

    def register(self, registry: APIRouter) -> None:
        registry.add_api_route(
            path="/v1/users/",
            endpoint=self.create_user,
            methods=["POST"],
            response_model=UserSchema,
        )

        registry.add_api_route(
            path="/v1/users/me",
            endpoint=self.get_current_user,
            methods=["GET"],
            dependencies=[Depends(self._jwt_auth)],
            response_model=UserSchema,
        )

        registry.add_api_route(
            path="/v1/users/{user_id}",
            endpoint=self.get_user_by_id,
            methods=["GET"],
            dependencies=[Depends(self._staff_jwt_auth)],
            response_model=UserSchema,
        )

    def create_user(self, request_body: CreateUserRequestSchema) -> UserSchema:
        is_valid_password = self._user_service.is_valid_password(
            password=request_body.password,
            username=request_body.username,
            email=str(request_body.email),
            first_name=request_body.first_name,
            last_name=request_body.last_name,
        )

        if not is_valid_password:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Password does not meet the strength requirements",
            )

        existing_user = self._user_service.get_user_by_username_or_email(
            username=request_body.username,
            email=str(request_body.email),
        )

        if existing_user is not None:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="A user with the given username or email already exists",
            )

        user = self._user_service.create_user(
            username=request_body.username,
            email=str(request_body.email),
            first_name=request_body.first_name,
            last_name=request_body.last_name,
            password=request_body.password,
        )

        return UserSchema.model_validate(user, from_attributes=True)

    def get_current_user(self, request: AuthenticatedRequest) -> UserSchema:
        return UserSchema.model_validate(request.state.user, from_attributes=True)

    def get_user_by_id(
        self,
        user_id: int,
    ) -> UserSchema:
        user = self._user_service.get_user_by_id(user_id=user_id)
        if user is None:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="User not found",
            )

        return UserSchema.model_validate(user, from_attributes=True)
