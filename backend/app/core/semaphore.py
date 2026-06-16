from __future__ import annotations

import redis as redis_lib

from app.core.config import settings

_DEFAULT_TTL = 1020  # matches CELERY_TASK_TIME_LIMIT + 60s


class RegistrySemaphore:
    def __init__(
        self,
        redis_client: redis_lib.Redis | None = None,
        max_per_registry: int = 10,
    ):
        self._redis = redis_client or redis_lib.from_url(settings.REDIS_URL)
        self._max = max_per_registry

    def _key(self, registry_id: str) -> str:
        return f"registry_sem:{registry_id}"

    def acquire(self, registry_id: str) -> bool:
        key = self._key(registry_id)
        current = self._redis.incr(key)
        self._redis.expire(key, _DEFAULT_TTL)
        if current > self._max:
            self._redis.decr(key)
            return False
        return True

    def release(self, registry_id: str) -> None:
        self._redis.decr(self._key(registry_id))
