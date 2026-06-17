from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.models.merge_request import MRState, MRTargetKind, MRType, PipelineStatus


class RaiseMRRequest(BaseModel):
    scan_id: str
    finding_ids: list[str]
    mr_type: MRType
    targets: list[MRTargetKind]
    source_branch_template: str
    target_branch: str
    gitlab_token: str  # write-only, used by Celery task
    template_vars: dict[str, str] = {}


class MRResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    image_id: uuid.UUID
    scan_id: uuid.UUID
    mr_type: MRType
    target_kind: MRTargetKind
    gitlab_project_id: str
    gitlab_mr_iid: int | None
    gitlab_mr_url: str | None
    source_branch: str | None
    target_branch: str
    state: MRState
    pipeline_status: PipelineStatus | None
    finding_ids: list[str]
    image_digest: str
    # gitlab_token intentionally absent — write-only
