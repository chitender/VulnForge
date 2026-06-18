from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, CurrentUser
from app.schemas.registry import RegistryCreate, RegistryResponse
from app.services.registry_service import RegistryService
from app.workers.registry_adapters import get_adapter

router = APIRouter(prefix="/api/registries", tags=["registries"])
log = structlog.get_logger()


def _team_ids(user: dict) -> list[str]:
    return user.get("patchpilot_teams", [])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RegistryResponse)
async def create_registry(body: RegistryCreate, user: CurrentUser, db: DB) -> Any:
    teams = _team_ids(user)
    if not teams:
        raise HTTPException(400, "User has no team membership")
    svc = RegistryService()
    reg = await svc.create(
        db=db,
        owner_id=user["sub"],
        team_id=teams[0],
        name=body.name,
        registry_type=body.type,
        registry_url=body.registry_url,
        region=body.region,
        creds=body.credentials,
    )
    log.info("registry_created", registry_id=str(reg.id), type=body.type)
    return reg


@router.get("", response_model=list[RegistryResponse])
async def list_registries(user: CurrentUser, db: DB) -> Any:
    teams = _team_ids(user)
    if not teams:
        return []
    return await RegistryService().list(db=db, team_ids=teams)


@router.delete("/{registry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_registry(registry_id: str, user: CurrentUser, db: DB) -> None:
    svc = RegistryService()
    for team_id in _team_ids(user):
        if await svc.delete(db=db, registry_id=registry_id, team_id=team_id):
            return
    raise HTTPException(status_code=404, detail="Registry not found")


@router.post("/{registry_id}/validate", status_code=status.HTTP_200_OK)
async def validate_registry(registry_id: str, user: CurrentUser, db: DB) -> dict:
    svc = RegistryService()
    reg = None
    for team_id in _team_ids(user):
        reg = await svc.get(db=db, registry_id=registry_id, team_id=team_id)
        if reg:
            break
    if not reg:
        raise HTTPException(status_code=404, detail="Registry not found")

    creds = svc.decrypt_creds(reg)
    adapter = get_adapter(reg.type)
    try:
        adapter.validate(creds, reg)
        return {"status": "ok"}
    except ValueError as exc:
        return {"status": "failed", "detail": str(exc)}
    except Exception as exc:
        log.error("validate_error", registry_id=registry_id, error=str(exc))
        return {"status": "failed", "detail": "Connection error"}
