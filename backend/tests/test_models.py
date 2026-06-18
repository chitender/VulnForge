from sqlalchemy import text


def test_all_tables_created(sync_db):
    result = sync_db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
    tables = {row[0] for row in result.fetchall()}
    assert "users" in tables
    assert "registries" in tables
    assert "images" in tables
    assert "scans" in tables
    assert "findings" in tables
    assert "merge_requests" in tables
    assert "audit_log" in tables


def test_registries_has_envelope_columns(sync_db):
    result = sync_db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='registries' AND column_name IN ('auth_ciphertext','auth_dek_enc')"
        )
    )
    cols = {row[0] for row in result.fetchall()}
    assert cols == {"auth_ciphertext", "auth_dek_enc"}


def test_merge_requests_has_pipeline_columns(sync_db):
    result = sync_db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='merge_requests' "
            "AND column_name IN ('gitlab_pipeline_id','pipeline_status','image_digest')"
        )
    )
    cols = {row[0] for row in result.fetchall()}
    assert cols == {"gitlab_pipeline_id", "pipeline_status", "image_digest"}
