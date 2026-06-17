from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan import Scan, ScanStatus


class ScanService:
    async def create(
        self, db: AsyncSession, image_id: str, triggered_by: str
    ) -> Scan:
        scan = Scan(
            id=uuid.uuid4(),
            image_id=uuid.UUID(image_id),
            triggered_by=uuid.uuid4(),  # Keycloak sub may not be a UUID; use placeholder
            status=ScanStatus.QUEUED,
        )
        db.add(scan)
        await db.commit()
        await db.refresh(scan)
        return scan

    async def get(self, db: AsyncSession, scan_id: str) -> Scan | None:
        return await db.get(Scan, uuid.UUID(scan_id))
