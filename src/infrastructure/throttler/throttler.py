from dataclasses import dataclass

from throttled import BaseStore, Quota, RateLimiterType, RedisStore, Throttled
from throttled.asyncio import (
    BaseStore as AsyncBaseStore,
    Quota as AsyncQuota,
    RateLimiterType as AsyncRateLimiterType,
    RedisStore as AsyncRedisStore,
    Throttled as AsyncThrottled,
)

from infrastructure.redis.settings import RedisSettings


@dataclass(kw_only=True)
class ThrottlerStoreFactory:
    _redis_settings: RedisSettings

    def __call__(self) -> BaseStore:
        return RedisStore(server=self._redis_settings.url.get_secret_value())


@dataclass(kw_only=True)
class ThrottlerFactory:
    _store_factory: ThrottlerStoreFactory

    def __post_init__(self) -> None:
        self._store = self._store_factory()

    def __call__(
        self,
        quota: Quota,
        using: RateLimiterType = RateLimiterType.TOKEN_BUCKET,
    ) -> Throttled:
        return Throttled(
            using=using.value,
            quota=quota,
            store=self._store,  # type: ignore[invalid-argument-type]
        )


@dataclass(kw_only=True)
class AsyncThrottlerStoreFactory:
    _redis_settings: RedisSettings

    def __call__(self) -> AsyncBaseStore:
        return AsyncRedisStore(server=self._redis_settings.url.get_secret_value())


@dataclass(kw_only=True)
class AsyncThrottlerFactory:
    _store_factory: AsyncThrottlerStoreFactory

    def __post_init__(self) -> None:
        self._store = self._store_factory()

    def __call__(
        self,
        quota: AsyncQuota,
        using: AsyncRateLimiterType = AsyncRateLimiterType.TOKEN_BUCKET,
    ) -> AsyncThrottled:
        return AsyncThrottled(
            using=using.value,
            quota=quota,
            store=self._store,  # type: ignore[invalid-argument-type]
        )
