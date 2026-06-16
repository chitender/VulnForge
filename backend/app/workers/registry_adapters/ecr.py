from typing import Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from app.workers.registry_adapters.base import BaseRegistryAdapter


class ECRAdapter(BaseRegistryAdapter):
    def get_trivy_env(self, creds: dict[str, Any], registry: Any) -> dict[str, str]:
        return {
            "AWS_ACCESS_KEY_ID": creds.get("aws_access_key_id", ""),
            "AWS_SECRET_ACCESS_KEY": creds.get("aws_secret_access_key", ""),
            "AWS_DEFAULT_REGION": registry.region or "us-east-1",
        }

    def _get_ecr_token(self, creds: dict[str, Any], region: str | None) -> str:
        session = boto3.Session(
            aws_access_key_id=creds.get("aws_access_key_id"),
            aws_secret_access_key=creds.get("aws_secret_access_key"),
            region_name=region or "us-east-1",
        )
        ecr = session.client("ecr")
        resp = ecr.get_authorization_token()
        return resp["authorizationData"][0]["authorizationToken"]

    def validate(self, creds: dict[str, Any], registry: Any) -> None:
        try:
            self._get_ecr_token(creds, registry.region)
        except (ClientError, NoCredentialsError) as exc:
            raise ValueError(f"ECR credentials invalid: {exc}") from exc
