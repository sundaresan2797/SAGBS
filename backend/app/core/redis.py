import json
import logging
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger("ems.redis")


class RedisService:
    """Reusable async Redis abstraction implementing cache-aside helpers.

    All methods fail open: if Redis is unavailable, methods log a warning and
    return a neutral value (None/False) instead of raising, so a Redis outage
    degrades caching/rate-limiting but never takes the app down.
    """

    def __init__(self, url: str):
        self._url = url
        self._client: redis.Redis | None = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self._url, decode_responses=True)
        return self._client

    async def ping(self) -> bool:
        try:
            return bool(await self.client.ping())
        except RedisError as exc:
            logger.warning("Redis ping failed: %s", exc)
            return False

    async def get(self, key: str) -> Any | None:
        try:
            raw = await self.client.get(key)
            return json.loads(raw) if raw is not None else None
        except RedisError as exc:
            logger.warning("Redis GET failed for key=%s: %s", key, exc)
            return None
        except (TypeError, ValueError):
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        try:
            payload = json.dumps(value, default=str)
            await self.client.set(key, payload, ex=ttl_seconds)
            return True
        except RedisError as exc:
            logger.warning("Redis SET failed for key=%s: %s", key, exc)
            return False

    async def delete(self, *keys: str) -> bool:
        if not keys:
            return True
        try:
            await self.client.delete(*keys)
            return True
        except RedisError as exc:
            logger.warning("Redis DELETE failed for keys=%s: %s", keys, exc)
            return False

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self.client.exists(key))
        except RedisError as exc:
            logger.warning("Redis EXISTS failed for key=%s: %s", key, exc)
            return False

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        try:
            return bool(await self.client.expire(key, ttl_seconds))
        except RedisError as exc:
            logger.warning("Redis EXPIRE failed for key=%s: %s", key, exc)
            return False

    async def delete_pattern(self, pattern: str) -> int:
        try:
            count = 0
            async for key in self.client.scan_iter(match=pattern, count=100):
                await self.client.delete(key)
                count += 1
            return count
        except RedisError as exc:
            logger.warning("Redis delete_pattern failed for pattern=%s: %s", pattern, exc)
            return 0

    async def incr(self, key: str, ttl_seconds: int | None = None) -> int | None:
        try:
            value = await self.client.incr(key)
            if value == 1 and ttl_seconds:
                await self.client.expire(key, ttl_seconds)
            return value
        except RedisError as exc:
            logger.warning("Redis INCR failed for key=%s: %s", key, exc)
            return None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def reset(self) -> None:
        """Close and drop the underlying client so the next call reconnects.

        Needed whenever the running event loop changes underneath this
        process-wide singleton (e.g. each test gets its own loop); a client
        created on a closed loop raises "Event loop is closed" on next use.
        """
        if self._client is not None:
            try:
                await self._client.aclose()
            except RuntimeError:
                pass
            self._client = None


redis_service = RedisService(settings.redis_url)


class CacheKeys:
    DASHBOARD_SUMMARY = "ems:dashboard:summary"
    DASHBOARD_ATTENDANCE = "ems:dashboard:attendance"
    DASHBOARD_LEAVE = "ems:dashboard:leave"
    DASHBOARD_DEPARTMENTS = "ems:dashboard:departments"
    DEPARTMENTS_LIST = "ems:departments"
    DESIGNATIONS_LIST = "ems:designations"
    EMPLOYEE_PROFILE = "ems:employee:{employee_id}"
    EMPLOYEES_LIST_PREFIX = "ems:employees:list:"
    LOGIN_RATE_LIMIT = "ems:ratelimit:login:{identifier}"
    PASSWORD_RESET_RATE_LIMIT = "ems:ratelimit:password_reset:{identifier}"

    @staticmethod
    def employee_profile(employee_id: int) -> str:
        return CacheKeys.EMPLOYEE_PROFILE.format(employee_id=employee_id)

    @staticmethod
    def employees_list(filters_hash: str) -> str:
        return f"{CacheKeys.EMPLOYEES_LIST_PREFIX}{filters_hash}"

    @staticmethod
    def login_rate_limit(identifier: str) -> str:
        return CacheKeys.LOGIN_RATE_LIMIT.format(identifier=identifier)

    @staticmethod
    def password_reset_rate_limit(identifier: str) -> str:
        return CacheKeys.PASSWORD_RESET_RATE_LIMIT.format(identifier=identifier)


class CacheTTL:
    DASHBOARD = 300
    DEPARTMENT_DESIGNATION = 1800
    EMPLOYEE_PROFILE = 300
    EMPLOYEES_LIST = 120
