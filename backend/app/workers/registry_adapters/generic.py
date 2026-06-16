from typing import Any

from app.workers.registry_adapters.base import BaseRegistryAdapter


class GenericOCIAdapter(BaseRegistryAdapter):
    def get_trivy_env(self, creds: dict[str, Any], registry: Any) -> dict[str, str]:
        return {
            "TRIVY_USERNAME": creds["username"],
            "TRIVY_PASSWORD": creds["password"],
        }

    def validate(self, creds: dict[str, Any], registry: Any) -> None:
        url = f"https://{registry.registry_url}/v2/"
        resp = self._request_with_backoff(
            "GET", url, auth=(creds["username"], creds["password"])
        )
        if resp.status_code in (401, 403):
            raise ValueError(f"Registry credentials invalid for {registry.registry_url}")
        if resp.status_code != 200:
            raise ValueError(f"Registry unreachable: {resp.status_code}")
