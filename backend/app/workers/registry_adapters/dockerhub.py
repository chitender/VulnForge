from typing import Any

from app.workers.registry_adapters.base import BaseRegistryAdapter


class DockerHubAdapter(BaseRegistryAdapter):
    def get_trivy_env(self, creds: dict[str, Any], registry: Any) -> dict[str, str]:
        return {
            "TRIVY_USERNAME": creds["username"],
            "TRIVY_PASSWORD": creds["password"],
        }

    def validate(self, creds: dict[str, Any], registry: Any) -> None:
        resp = self._request_with_backoff(
            "GET",
            "https://auth.docker.io/token"
            "?service=registry.docker.io&scope=repository:library/alpine:pull",
            auth=(creds["username"], creds["password"]),
        )
        if resp.status_code == 401:
            raise ValueError("Docker Hub credentials invalid")
        resp.raise_for_status()
