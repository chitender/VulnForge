"""Enable Row-Level Security on team-scoped tables.

RLS is defence-in-depth on top of the SQLAlchemy team_scoped_query mixin.
A query that slips through without the mixin will be blocked at the DB layer.

Set patchpilot.team_ids before executing queries in a session:
    SET LOCAL patchpilot.team_ids = '<uuid1>,<uuid2>';

Revision ID: 002
Revises: 9f49298ff25b
Create Date: 2026-06-17
"""
from __future__ import annotations

from alembic import op

revision = "002"
down_revision = "9f49298ff25b"
branch_labels = None
depends_on = None

# Tables that carry team_id directly — RLS isolates rows by team.
# merge_requests references teams transitively via image_id, so RLS is enforced
# at the application layer rather than here.
_TEAM_SCOPED_TABLES = ("registries", "images")


def upgrade() -> None:
    # The superuser role used by migrations is exempt from RLS by default.
    # Application role (patchpilot_app) is NOT superuser and WILL be restricted.
    for table in _TEAM_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY team_isolation ON {table}
            AS PERMISSIVE FOR ALL
            USING (
                team_id = ANY(
                    string_to_array(
                        current_setting('patchpilot.team_ids', true),
                        ','
                    )::uuid[]
                )
            )
            """
        )

    # Unique partial index for MR idempotency (ON CONFLICT target)
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uix_mr_open
        ON merge_requests (gitlab_project_id, image_digest, target_branch, target_kind)
        WHERE state = 'OPENED'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uix_mr_open")
    for table in reversed(_TEAM_SCOPED_TABLES):
        op.execute(f"DROP POLICY IF EXISTS team_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
