from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole


async def get_or_create_user(
    db: AsyncSession,
    keycloak_sub: str,
    email: str = "",
    name: str = "",
) -> uuid.UUID:
    """Return the users.id for this Keycloak subject, creating a record if absent.

    Called at scan-creation time so triggered_by is always a real users.id,
    preserving the audit trail FK.
    """
    result = await db.execute(
        select(User).where(User.keycloak_sub == keycloak_sub)
    )
    user = result.scalar_one_or_none()
    if user:
        return user.id

    user = User(
        keycloak_sub=keycloak_sub,
        email=email or keycloak_sub,
        name=name or keycloak_sub,
        role=UserRole.VIEWER,
    )
    db.add(user)
    await db.flush()  # get the generated id without committing the outer transaction
    return user.id
