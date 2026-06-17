from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.team_scope import team_scoped_query
from app.models.image import Image, ServiceType


class ImageService:
    async def create(
        self,
        db: AsyncSession,
        owner_id: str,
        team_id: str,
        registry_id: str,
        repository: str,
        tag: str,
        service_type: ServiceType,
        base_dockerfile_path: str,
        app_dockerfile_path: str,
        gitlab_project_id: str,
        gitlab_default_branch: str,
    ) -> Image:
        img = Image(
            owner_id=uuid.UUID(owner_id),
            team_id=uuid.UUID(team_id),
            registry_id=uuid.UUID(registry_id),
            repository=repository,
            tag=tag,
            service_type=service_type,
            base_dockerfile_path=base_dockerfile_path,
            app_dockerfile_path=app_dockerfile_path,
            gitlab_project_id=gitlab_project_id,
            gitlab_default_branch=gitlab_default_branch,
        )
        db.add(img)
        await db.commit()
        await db.refresh(img)
        return img

    async def list(self, db: AsyncSession, team_id: str) -> list[Image]:
        q = team_scoped_query(select(Image), Image, [team_id])
        result = await db.execute(q)
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, image_id: str, team_id: str) -> Image | None:
        q = team_scoped_query(select(Image), Image, [team_id]).where(
            Image.id == uuid.UUID(image_id)
        )
        result = await db.execute(q)
        return result.scalar_one_or_none()

    async def update(
        self, db: AsyncSession, image_id: str, team_id: str, **kwargs: Any
    ) -> Image | None:
        img = await self.get(db, image_id, team_id)
        if not img:
            return None
        for key, val in kwargs.items():
            if val is not None:
                setattr(img, key, val)
        await db.commit()
        await db.refresh(img)
        return img

    async def delete(self, db: AsyncSession, image_id: str, team_id: str) -> bool:
        img = await self.get(db, image_id, team_id)
        if not img:
            return False
        img.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        return True
