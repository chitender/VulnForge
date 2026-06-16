from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.credentials import CredentialStore
from app.models.registry import Registry, RegistryType


class RegistryService:
    def __init__(self, credential_store: CredentialStore | None = None):
        self._store = credential_store or CredentialStore()

    async def create(
        self,
        db: AsyncSession,
        owner_id: str,
        team_id: str,
        name: str,
        registry_type: RegistryType,
        registry_url: str,
        region: str | None,
        creds: dict[str, Any],
    ) -> Registry:
        ciphertext, dek_enc = self._store.encrypt(creds)
        reg = Registry(
            owner_id=uuid.UUID(owner_id),
            team_id=uuid.UUID(team_id),
            name=name,
            type=registry_type,
            registry_url=registry_url,
            region=region,
            auth_ciphertext=ciphertext,
            auth_dek_enc=dek_enc,
        )
        db.add(reg)
        await db.commit()
        await db.refresh(reg)
        return reg

    async def list(self, db: AsyncSession, team_id: str) -> list[Registry]:
        result = await db.execute(
            select(Registry).where(
                Registry.team_id == uuid.UUID(team_id),
                Registry.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, registry_id: str, team_id: str) -> Registry | None:
        result = await db.execute(
            select(Registry).where(
                Registry.id == uuid.UUID(registry_id),
                Registry.team_id == uuid.UUID(team_id),
                Registry.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def delete(self, db: AsyncSession, registry_id: str, team_id: str) -> bool:
        reg = await self.get(db, registry_id, team_id)
        if not reg:
            return False
        reg.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        return True

    def decrypt_creds(self, reg: Registry) -> dict[str, Any]:
        return self._store.decrypt(reg.auth_ciphertext, reg.auth_dek_enc)
