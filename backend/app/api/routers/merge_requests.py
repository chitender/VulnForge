from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, CurrentUser
from app.schemas.merge_request import MRResponse, RaiseMRRequest
from app.services.audit_service import AuditService
from app.services.image_service import ImageService
from app.services.mr_service import MRService
from app.services.scan_service import ScanService
from app.tasks.mr_task import dispatch_mr_task

router = APIRouter(prefix="/api/merge-requests", tags=["merge-requests"])
log = structlog.get_logger()


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def raise_mr(body: RaiseMRRequest, user: CurrentUser, db: DB) -> Any:
    scan = await ScanService().get(db=db, scan_id=body.scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")

    # Verify image team membership
    img_svc = ImageService()
    img = None
    for team_id in user.get("patchpilot_teams", []):
        img = await img_svc.get(db=db, image_id=str(scan.image_id), team_id=team_id)
        if img:
            break
    if not img:
        raise HTTPException(403, "Image not in your team")

    template_vars = {
        **body.template_vars,
        "raised_by": user.get("email", user["sub"]),
        "image": img.repository.replace("/", "-"),
        "tag": img.tag,
    }

    dispatched = []
    for target_kind in body.targets:
        queued = dispatch_mr_task(
            scan_id=body.scan_id,
            finding_ids=body.finding_ids,
            mr_type=body.mr_type.value,
            target_kind=target_kind.value,
            source_branch_template=body.source_branch_template,
            target_branch=body.target_branch,
            template_vars=template_vars,
            gitlab_project_id=str(img.gitlab_project_id),
            gitlab_token=body.gitlab_token,
            image_digest=str(scan.image_digest or ""),
        )
        dispatched.append({"target_kind": target_kind.value, "queued": queued})

    await AuditService().log(
        db=db,
        actor_id=user["sub"],
        action="raise_mr",
        entity_type="scan",
        entity_id=body.scan_id,
        metadata={
            "targets": [t.value for t in body.targets],
            "finding_count": len(body.finding_ids),
        },
    )
    return {"dispatched": dispatched}


@router.get("", response_model=list[MRResponse])
async def list_mrs(user: CurrentUser, db: DB) -> Any:
    teams = user.get("patchpilot_teams", [])
    if not teams:
        return []
    imgs = await ImageService().list(db=db, team_ids=teams)
    image_ids = [str(img.id) for img in imgs]
    return await MRService().list(db=db, team_image_ids=image_ids)


@router.get("/{mr_id}", response_model=MRResponse)
async def get_mr(mr_id: str, user: CurrentUser, db: DB) -> Any:
    mr = await MRService().get(db=db, mr_id=mr_id)
    if not mr:
        raise HTTPException(404, "MR not found")
    # Verify team ownership via image
    img_svc = ImageService()
    for team_id in user.get("patchpilot_teams", []):
        img = await img_svc.get(db=db, image_id=str(mr.image_id), team_id=team_id)
        if img:
            return mr
    raise HTTPException(404, "MR not found")


@router.post("/{mr_id}/sync", response_model=MRResponse)
async def sync_mr(mr_id: str, user: CurrentUser, db: DB) -> Any:
    mr_svc = MRService()
    mr = await mr_svc.get(db=db, mr_id=mr_id)
    if not mr:
        raise HTTPException(404, "MR not found")

    # Verify ownership
    img_svc = ImageService()
    img = None
    for team_id in user.get("patchpilot_teams", []):
        img = await img_svc.get(db=db, image_id=str(mr.image_id), team_id=team_id)
        if img:
            break
    if not img:
        raise HTTPException(404, "MR not found")

    # Fetch latest GitLab state using the stored MR info
    # (gitlab_token not stored — sync uses stored pipeline_status until Phase 8 webhook)
    if not mr.gitlab_mr_iid:
        return mr

    # Without a stored token we can only return what we have.
    # Phase 8 will add a webhook that pushes updates automatically.
    log.info("mr_sync_no_token", mr_id=mr_id)
    return mr
