import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from starlette import status
from starlette.requests import Request
from throttled.asyncio import Quota, RateLimiterType, Throttled

from delivery.http.auth.jwt import AuthenticatedRequest
from delivery.http.services.request import RequestInfoService
from infrastructure.throttler.throttler import AsyncThrottlerFactory

logger = logging.getLogger(__name__)


@dataclass(kw_only=True)
class BaseThrottler(ABC):
    _throttler: Throttled
    _cost: int = 1

    async def __call__(self, request: Request) -> None:
        key = self._build_key(request=request)
        result = await self._throttler.limit(key=key, cost=self._cost)
        if result.limited:
            logger.debug("Request with key %s was throttled", key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
            )

        logger.debug("Request with key %s was not throttled", key)

    @abstractmethod
    def _build_key(self, request: Any) -> str: ...


@dataclass(kw_only=True)
class IPThrottler(BaseThrottler):
    _request_info_service: RequestInfoService

    def _build_key(self, request: Request) -> str:
        user_ip = self._request_info_service.get_user_ip(request=request)
        path = request.url.path
        method = request.method

        return f"throttler:{method}:{path}:{user_ip}".lower()


@dataclass(kw_only=True)
class UserThrottler(BaseThrottler):
    def _build_key(self, request: AuthenticatedRequest) -> str:
        user_id = request.state.user.pk
        path = request.url.path
        method = request.method

        return f"throttler:{method}:{path}:{user_id}".lower()


@dataclass(kw_only=True)
class IPThrottlerFactory:
    _throttler_factory: AsyncThrottlerFactory
    _request_info_service: RequestInfoService

    def __call__(
        self,
        quota: Quota,
        using: RateLimiterType = RateLimiterType.TOKEN_BUCKET,
        cost: int = 1,
    ) -> Callable[[Request], Awaitable[None]]:
        throttler = self._throttler_factory(
            quota=quota,
            using=using,
        )

        return IPThrottler(
            _throttler=throttler,
            _request_info_service=self._request_info_service,
            _cost=cost,
        ).__call__


@dataclass(kw_only=True)
class UserThrottlerFactory:
    _throttler_factory: AsyncThrottlerFactory

    def __call__(
        self,
        quota: Quota,
        using: RateLimiterType = RateLimiterType.TOKEN_BUCKET,
        cost: int = 1,
    ) -> Callable[[Request], Awaitable[None]]:
        throttler = self._throttler_factory(
            quota=quota,
            using=using,
        )

        return UserThrottler(
            _throttler=throttler,
            _cost=cost,
        ).__call__
