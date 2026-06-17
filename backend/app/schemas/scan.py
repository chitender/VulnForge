from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.models.scan import ScanStatus


class ScanTriggerResponse(BaseModel):
    scan_id: str
    status: str


class ScanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    image_id: uuid.UUID
    status: ScanStatus
    image_digest: str | None
    trivy_version: str | None
    db_version: str | None
    summary_jsonb: dict | None
    error_text: str | None
