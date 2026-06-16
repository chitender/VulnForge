from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from typing import Any

import requests


class BaseRegistryAdapter(ABC):
    @abstractmethod
    def get_trivy_env(self, creds: dict[str, Any], registry: Any) -> dict[str, str]:
        """Return env vars to inject into the trivy subprocess for this registry."""

    @abstractmethod
    def validate(self, creds: dict[str, Any], registry: Any) -> None:
        """Raise ValueError if creds are invalid or registry unreachable."""

    def _request_with_backoff(
        self,
        method: str,
        url: str,
        max_retries: int = 5,
        **kwargs: Any,
    ) -> requests.Response:
        base_delay = 2.0
        cap = 60.0
        for attempt in range(max_retries):
            resp = requests.request(method, url, timeout=15, **kwargs)
            if resp.status_code == 429:
                delay = min(base_delay * (2**attempt) + random.uniform(0, 1), cap)
                time.sleep(delay)
                continue
            return resp
        raise RuntimeError(f"Registry throttled after {max_retries} retries: {url}")
