from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.models.finding import FindingStatus, Severity


class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scan_id: uuid.UUID
    vuln_id: str
    pkg_name: str
    installed_version: str
    fixed_version: str | None
    severity: Severity
    target: str | None
    title: str | None
    primary_url: str | None
    is_fixable: bool
    status: FindingStatus
