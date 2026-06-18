from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merge_request import MergeRequest, MRState


class MRService:
    async def list(self, db: AsyncSession, team_image_ids: list[str]) -> list[MergeRequest]:
        if not team_image_ids:
            return []
        result = await db.execute(
            select(MergeRequest).where(
                MergeRequest.image_id.in_([uuid.UUID(i) for i in team_image_ids])
            )
        )
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, mr_id: str) -> MergeRequest | None:
        return await db.get(MergeRequest, uuid.UUID(mr_id))

    async def update_pipeline_status(
        self,
        db: AsyncSession,
        mr_id: str,
        pipeline_status: str,
        pipeline_id: int | None,
        state: str | None = None,
    ) -> MergeRequest | None:
        mr = await self.get(db, mr_id)
        if not mr:
            return None
        from app.models.merge_request import PipelineStatus

        try:
            mr.pipeline_status = PipelineStatus(pipeline_status)
        except ValueError:
            mr.pipeline_status = PipelineStatus.UNKNOWN
        if pipeline_id is not None:
            mr.gitlab_pipeline_id = pipeline_id
        if state:
            try:
                mr.state = MRState(state.upper())
            except ValueError:
                pass
        await db.commit()
        return mr
