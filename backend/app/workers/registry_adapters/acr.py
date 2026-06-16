from typing import Any

from azure.containerregistry import ContainerRegistryClient
from azure.identity import ClientSecretCredential

from app.workers.registry_adapters.base import BaseRegistryAdapter


class ACRAdapter(BaseRegistryAdapter):
    def get_trivy_env(self, creds: dict[str, Any], registry: Any) -> dict[str, str]:
        return {
            "TRIVY_USERNAME": creds["client_id"],
            "TRIVY_PASSWORD": creds["client_secret"],
        }

    def validate(self, creds: dict[str, Any], registry: Any) -> None:
        try:
            credential = ClientSecretCredential(
                tenant_id=creds["tenant_id"],
                client_id=creds["client_id"],
                client_secret=creds["client_secret"],
            )
            client = ContainerRegistryClient(
                endpoint=f"https://{registry.registry_url}",
                credential=credential,
            )
            next(client.list_repository_names(), None)
        except Exception as exc:
            raise ValueError(f"ACR credentials invalid: {exc}") from exc
