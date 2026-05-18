import json
from typing import Any

from redis.asyncio import Redis


class CacheService:
    """Small JSON cache abstraction over Redis.

    This service is intentionally narrow. Future agent memory, queues, rate
    limiting, and workflow state should build on separate focused services.
    """

    def __init__(self, *, redis: Redis, key_prefix: str) -> None:
        self._redis = redis
        self._key_prefix = key_prefix.rstrip(":")

    def key(self, namespace: str, identifier: str) -> str:
        return f"{self._key_prefix}:{namespace}:{identifier}"

    async def get_json(self, key: str) -> Any | None:
        value = await self._redis.get(key)
        if value is None:
            return None
        return json.loads(value)

    async def set_json(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        await self._redis.set(key, json.dumps(value), ex=ttl_seconds)

    async def delete(self, key: str) -> int:
        return int(await self._redis.delete(key))
