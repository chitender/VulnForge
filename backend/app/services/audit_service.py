from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditService:
    async def log(
        self,
        db: AsyncSession,
        actor_id: str | None,
        action: str,
        entity_type: str,
        entity_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry = AuditLog(
            actor_id=uuid.UUID(actor_id) if actor_id else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_jsonb=metadata,
        )
        db.add(entry)
        await db.commit()
