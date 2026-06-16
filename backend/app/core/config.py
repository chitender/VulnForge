from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://patchpilot:patchpilot@localhost:5432/patchpilot"
    REDIS_URL: str = "redis://localhost:6379/0"
    MASTER_KEY: str = ""
    KEYCLOAK_URL: str = "http://localhost:8080"
    KEYCLOAK_REALM: str = "patchpilot"
    KEYCLOAK_CLIENT_ID: str = "patchpilot-backend"
    TRIVY_SERVER_URL: str = "http://localhost:4954"

    @field_validator("MASTER_KEY")
    @classmethod
    def master_key_must_not_be_empty(cls, v: str) -> str:
        if not v:
            raise ValueError(
                "MASTER_KEY must be set. Generate one with: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        return v


settings = Settings()
