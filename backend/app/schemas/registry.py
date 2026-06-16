from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.url_validator import validate_registry_url
from app.models.registry import RegistryType


class RegistryCreate(BaseModel):
    name: str
    type: RegistryType
    registry_url: str
    region: str | None = None
    credentials: dict[str, Any] = Field(
        ..., description="Type-specific creds. Write-only — never returned."
    )

    @field_validator("registry_url")
    @classmethod
    def registry_url_no_ssrf(cls, v: str) -> str:
        return validate_registry_url(v)


class RegistryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: RegistryType
    registry_url: str
    region: str | None
    team_id: uuid.UUID
    # credentials intentionally absent — write-only
