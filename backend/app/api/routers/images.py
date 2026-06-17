from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, CurrentUser
from app.schemas.image import ImageCreate, ImageResponse, ImageUpdate
from app.services.image_service import ImageService

router = APIRouter(prefix="/api/images", tags=["images"])
log = structlog.get_logger()


def _team_ids(user: dict) -> list[str]:
    return user.get("patchpilot_teams", [])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ImageResponse)
async def create_image(body: ImageCreate, user: CurrentUser, db: DB) -> Any:
    teams = _team_ids(user)
    if not teams:
        raise HTTPException(400, "User has no team membership")
    svc = ImageService()
    img = await svc.create(
        db=db,
        owner_id=user["sub"],
        team_id=teams[0],
        registry_id=str(body.registry_id),
        repository=body.repository,
        tag=body.tag,
        service_type=body.service_type,
        base_dockerfile_path=body.base_dockerfile_path,
        app_dockerfile_path=body.app_dockerfile_path,
        gitlab_project_id=body.gitlab_project_id,
        gitlab_default_branch=body.gitlab_default_branch,
    )
    log.info("image_created", image_id=str(img.id), repository=body.repository)
    return img


@router.get("", response_model=list[ImageResponse])
async def list_images(user: CurrentUser, db: DB) -> Any:
    svc = ImageService()
    rows: list = []
    for team_id in _team_ids(user):
        rows.extend(await svc.list(db=db, team_id=team_id))
    return rows


@router.get("/{image_id}", response_model=ImageResponse)
async def get_image(image_id: str, user: CurrentUser, db: DB) -> Any:
    svc = ImageService()
    for team_id in _team_ids(user):
        img = await svc.get(db=db, image_id=image_id, team_id=team_id)
        if img:
            return img
    raise HTTPException(status_code=404, detail="Image not found")


@router.put("/{image_id}", response_model=ImageResponse)
async def update_image(image_id: str, body: ImageUpdate, user: CurrentUser, db: DB) -> Any:
    svc = ImageService()
    for team_id in _team_ids(user):
        img = await svc.update(
            db=db, image_id=image_id, team_id=team_id,
            **body.model_dump(exclude_none=True)
        )
        if img:
            return img
    raise HTTPException(status_code=404, detail="Image not found")


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(image_id: str, user: CurrentUser, db: DB) -> None:
    svc = ImageService()
    for team_id in _team_ids(user):
        if await svc.delete(db=db, image_id=image_id, team_id=team_id):
            return
    raise HTTPException(status_code=404, detail="Image not found")
