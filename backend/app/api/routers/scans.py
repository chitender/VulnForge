from __future__ import annotations

from typing import Any

import redis as redis_lib
import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.models.finding import Finding, FindingStatus, Severity
from app.schemas.finding import FindingResponse
from app.schemas.scan import ScanResponse, ScanTriggerResponse
from app.services.image_service import ImageService
from app.services.scan_service import ScanService
from app.tasks.scan_task import scan_image_task
from app.core.config import settings

router = APIRouter(tags=["scans"])
log = structlog.get_logger()

_redis = redis_lib.from_url(settings.REDIS_URL)
_MAX_CONCURRENT_SCANS_PER_USER = 5
_RATE_TTL = 120  # seconds


def _check_user_rate_limit(user_sub: str) -> bool:
    key = f"scan_rate:{user_sub}"
    count = _redis.incr(key)
    if count == 1:
        _redis.expire(key, _RATE_TTL)
    if count > _MAX_CONCURRENT_SCANS_PER_USER:
        _redis.decr(key)
        return False
    return True


async def _assert_scan_team_access(scan_id: str, user: dict, db: DB) -> None:
    """Raise 404 if the scan's image does not belong to any of the user's teams.

    Uses 404 (not 403) to avoid leaking the existence of scans for other teams.
    """
    scan = await ScanService().get(db=db, scan_id=scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    img_svc = ImageService()
    for team_id in user.get("patchpilot_teams", []):
        img = await img_svc.get(db=db, image_id=str(scan.image_id), team_id=team_id)
        if img:
            return
    raise HTTPException(404, "Scan not found")


async def get_findings_for_scan(
    db: DB,
    scan_id: str,
    severity: str | None = None,
    fixable_only: bool = False,
) -> list[Finding]:
    import uuid as _uuid
    q = select(Finding).where(Finding.scan_id == _uuid.UUID(scan_id))
    if severity:
        try:
            q = q.where(Finding.severity == Severity(severity.upper()))
        except ValueError:
            pass
    if fixable_only:
        q = q.where(Finding.is_fixable.is_(True))
    result = await db.execute(q)
    return list(result.scalars().all())


@router.post(
    "/api/images/{image_id}/scans",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ScanTriggerResponse,
)
async def trigger_scan(image_id: str, user: CurrentUser, db: DB) -> Any:
    img_svc = ImageService()
    img = None
    for team_id in user.get("patchpilot_teams", []):
        img = await img_svc.get(db=db, image_id=image_id, team_id=team_id)
        if img:
            break
    if not img:
        raise HTTPException(404, "Image not found")

    if not _check_user_rate_limit(user["sub"]):
        raise HTTPException(
            429, f"Max {_MAX_CONCURRENT_SCANS_PER_USER} concurrent scans per user"
        )

    scan_svc = ScanService()
    scan = await scan_svc.create(
        db=db,
        image_id=image_id,
        triggered_by=user["sub"],
        triggered_by_email=user.get("email", ""),
        triggered_by_name=user.get("name", ""),
    )
    scan_image_task.apply_async(args=[str(scan.id)])
    log.info("scan_queued", scan_id=str(scan.id), image_id=image_id)
    return {"scan_id": str(scan.id), "status": scan.status.value}


@router.get("/api/scans/{scan_id}", response_model=ScanResponse)
async def get_scan(scan_id: str, user: CurrentUser, db: DB) -> Any:
    await _assert_scan_team_access(scan_id, user, db)
    scan = await ScanService().get(db=db, scan_id=scan_id)
    return scan  # not None — _assert_scan_team_access already verified existence


@router.get("/api/scans/{scan_id}/findings", response_model=list[FindingResponse])
async def list_findings(
    scan_id: str,
    user: CurrentUser,
    db: DB,
    severity: str | None = None,
    fixable_only: bool = False,
) -> Any:
    await _assert_scan_team_access(scan_id, user, db)
    return await get_findings_for_scan(db, scan_id, severity, fixable_only)
