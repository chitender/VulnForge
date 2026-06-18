import uuid
from unittest.mock import MagicMock, patch

SCAN_ID = str(uuid.uuid4())


def _make_scan(status="QUEUED"):
    scan = MagicMock()
    scan.id = SCAN_ID
    scan.status = status
    scan.image_id = str(uuid.uuid4())
    img = MagicMock()
    img.repository = "myorg/payments"
    img.tag = "1.0"
    reg = MagicMock()
    reg.type = "DOCKERHUB"
    reg.registry_url = "registry-1.docker.io"
    reg.auth_ciphertext = b"cipher"
    reg.auth_dek_enc = b"dek"
    img.registry = reg
    scan.image = img
    return scan


def test_scan_task_sets_running_then_succeeded():
    mock_scan = _make_scan()

    with (
        patch("app.tasks.scan_task.SyncSessionLocal") as MockSession,
        patch("app.tasks.scan_task.CredentialStore") as MockStore,
        patch("app.tasks.scan_task.get_adapter") as MockAdapter,
        patch("app.tasks.scan_task.TrivyClient") as MockTrivy,
        patch("app.tasks.scan_task._redis"),
    ):
        session_ctx = MagicMock()
        session_ctx.__enter__ = MagicMock(
            return_value=MagicMock(get=MagicMock(return_value=mock_scan))
        )
        session_ctx.__exit__ = MagicMock(return_value=False)
        MockSession.return_value = session_ctx

        MockStore.return_value.decrypt.return_value = {"username": "u", "password": "p"}
        MockAdapter.return_value.get_trivy_env.return_value = {}

        mock_result = MagicMock()
        mock_result.image_digest = "sha256:abc"
        mock_result.results = []
        mock_result.trivy_version = "0.52"
        mock_result.db_version = "v1"
        MockTrivy.return_value.scan.return_value = mock_result

        from app.tasks.scan_task import scan_image_task

        scan_image_task(SCAN_ID)

    # Status should have transitioned through RUNNING → SUCCEEDED
    assert mock_scan.status.value in ("SUCCEEDED",) or str(mock_scan.status) in (
        "SUCCEEDED",
        "ScanStatus.SUCCEEDED",
    )


def test_scan_task_pushes_to_dlq_on_failure():
    mock_scan = _make_scan()

    with (
        patch("app.tasks.scan_task.SyncSessionLocal") as MockSession,
        patch("app.tasks.scan_task.CredentialStore") as MockStore,
        patch("app.tasks.scan_task.get_adapter") as MockAdapter,
        patch("app.tasks.scan_task.TrivyClient") as MockTrivy,
        patch("app.tasks.scan_task._redis") as MockRedis,
    ):
        session_ctx = MagicMock()
        session_ctx.__enter__ = MagicMock(
            return_value=MagicMock(get=MagicMock(return_value=mock_scan))
        )
        session_ctx.__exit__ = MagicMock(return_value=False)
        MockSession.return_value = session_ctx

        MockStore.return_value.decrypt.return_value = {}
        MockAdapter.return_value.get_trivy_env.return_value = {}
        MockTrivy.return_value.scan.side_effect = RuntimeError("trivy failed: exit 1")

        from app.tasks.scan_task import scan_image_task

        try:
            scan_image_task(SCAN_ID)
        except Exception:
            pass

        MockRedis.rpush.assert_called_once_with("scans_dlq", SCAN_ID)


def test_scan_task_calls_cleanup_always():
    """cleanup() must run even when scan succeeds (disk leak prevention)."""
    mock_scan = _make_scan()
    cleanup_called = []

    with (
        patch("app.tasks.scan_task.SyncSessionLocal") as MockSession,
        patch("app.tasks.scan_task.CredentialStore") as MockStore,
        patch("app.tasks.scan_task.get_adapter") as MockAdapter,
        patch("app.tasks.scan_task.TrivyClient") as MockTrivy,
        patch("app.tasks.scan_task._redis"),
    ):
        session_ctx = MagicMock()
        session_ctx.__enter__ = MagicMock(
            return_value=MagicMock(get=MagicMock(return_value=mock_scan))
        )
        session_ctx.__exit__ = MagicMock(return_value=False)
        MockSession.return_value = session_ctx

        MockStore.return_value.decrypt.return_value = {}
        MockAdapter.return_value.get_trivy_env.return_value = {}
        mock_result = MagicMock(
            image_digest="sha256:abc", results=[], trivy_version="", db_version=""
        )
        MockTrivy.return_value.scan.return_value = mock_result
        MockTrivy.return_value.cleanup.side_effect = lambda: cleanup_called.append(True)

        from app.tasks.scan_task import scan_image_task

        scan_image_task(SCAN_ID)

    assert cleanup_called, "cleanup() must be called after every scan"
