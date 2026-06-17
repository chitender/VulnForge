from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan import Scan, ScanStatus
from app.services.user_service import get_or_create_user


class ScanService:
    async def create(
        self,
        db: AsyncSession,
        image_id: str,
        triggered_by: str,
        triggered_by_email: str = "",
        triggered_by_name: str = "",
    ) -> Scan:
        user_id = await get_or_create_user(
            db, keycloak_sub=triggered_by,
            email=triggered_by_email,
            name=triggered_by_name,
        )
        scan = Scan(
            id=uuid.uuid4(),
            image_id=uuid.UUID(image_id),
            triggered_by=user_id,
            status=ScanStatus.QUEUED,
        )
        db.add(scan)
        await db.commit()
        await db.refresh(scan)
        return scan

    async def get(self, db: AsyncSession, scan_id: str) -> Scan | None:
        return await db.get(Scan, uuid.UUID(scan_id))
