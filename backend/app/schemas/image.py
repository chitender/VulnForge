from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.models.image import ServiceType


class ImageCreate(BaseModel):
    registry_id: uuid.UUID
    repository: str
    tag: str
    service_type: ServiceType
    base_dockerfile_path: str
    app_dockerfile_path: str
    gitlab_project_id: str
    gitlab_default_branch: str = "main"


class ImageUpdate(BaseModel):
    tag: str | None = None
    base_dockerfile_path: str | None = None
    app_dockerfile_path: str | None = None
    gitlab_default_branch: str | None = None


class ImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    registry_id: uuid.UUID
    team_id: uuid.UUID
    repository: str
    tag: str
    last_digest: str | None
    service_type: ServiceType
    base_dockerfile_path: str
    app_dockerfile_path: str
    gitlab_project_id: str
    gitlab_default_branch: str
