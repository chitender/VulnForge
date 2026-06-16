from typing import Any

import google.auth.transport.requests
from google.oauth2 import service_account

from app.workers.registry_adapters.base import BaseRegistryAdapter


class GARAdapter(BaseRegistryAdapter):
    def get_trivy_env(self, creds: dict[str, Any], registry: Any) -> dict[str, str]:
        token = self._get_token(creds)
        return {
            "TRIVY_USERNAME": "oauth2accesstoken",
            "TRIVY_PASSWORD": token,
        }

    def _get_token(self, creds: dict[str, Any]) -> str:
        sa_creds = service_account.Credentials.from_service_account_info(
            creds["service_account_json"],
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        request = google.auth.transport.requests.Request()
        sa_creds.refresh(request)
        return sa_creds.token  # type: ignore[return-value]

    def validate(self, creds: dict[str, Any], registry: Any) -> None:
        try:
            self._get_token(creds)
        except Exception as exc:
            raise ValueError(f"GAR credentials invalid: {exc}") from exc
