"""
Centralised team scoping utility.

Every query against a team-scoped model MUST go through `team_scoped_query`
or a service that calls it. Direct `select(Model)` without this filter is an S1
data-leak risk.

Usage in services:
    from app.core.team_scope import team_scoped_query

    async def list(self, db, team_id: str) -> list[Registry]:
        q = team_scoped_query(select(Registry), Registry, [team_id])
        result = await db.execute(q)
        return list(result.scalars().all())
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select


def team_scoped_query(
    query: Select,
    model_class: type,
    team_ids: list[str],
) -> Select:
    """Apply team_id IN (...) and deleted_at IS NULL to any team-scoped query.

    Raises ValueError if team_ids is empty (caller bug, not a missing-data case).
    """
    if not team_ids:
        raise ValueError("team_ids must not be empty — refusing to build an unscoped query")
    uuids = [uuid.UUID(t) for t in team_ids]
    return query.where(
        model_class.team_id.in_(uuids),
        model_class.deleted_at.is_(None),
    )
