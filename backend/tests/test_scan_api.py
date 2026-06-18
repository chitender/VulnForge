import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.scan import ScanStatus

TEST_USER = {
    "sub": "user-sub-123",
    "email": "dev@example.com",
    "realm_access": {"roles": ["editor"]},
    "patchpilot_teams": ["00000000-0000-0000-0000-000000000010"],
}
IMAGE_ID = str(uuid.uuid4())
SCAN_ID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def mock_auth():
    with patch("app.core.auth._decode_token", return_value=TEST_USER):
        yield


def _mock_scan(status: ScanStatus = ScanStatus.QUEUED) -> MagicMock:
    s = MagicMock()
    s.id = uuid.UUID(SCAN_ID)
    s.image_id = uuid.UUID(IMAGE_ID)
    s.status = status
    s.image_digest = None
    s.trivy_version = None
    s.db_version = None
    s.summary_jsonb = None
    s.error_text = None
    return s


def _mock_image() -> MagicMock:
    img = MagicMock()
    img.id = uuid.UUID(IMAGE_ID)
    img.team_id = uuid.UUID("00000000-0000-0000-0000-000000000010")
    return img


def test_trigger_scan_returns_202():
    with (
        patch("app.api.routers.scans.ImageService") as MockImgSvc,
        patch("app.api.routers.scans.ScanService") as MockScanSvc,
        patch("app.api.routers.scans.scan_image_task") as MockTask,
        patch("app.api.routers.scans._check_user_rate_limit", return_value=True),
        patch(
            "app.services.scan_service.get_or_create_user",
            new_callable=AsyncMock,
            return_value=uuid.uuid4(),
        ),
    ):
        MockImgSvc.return_value.get = AsyncMock(return_value=_mock_image())
        MockScanSvc.return_value.create = AsyncMock(return_value=_mock_scan(ScanStatus.QUEUED))

        resp = TestClient(app).post(
            f"/api/images/{IMAGE_ID}/scans",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 202
    assert resp.json()["status"] == "QUEUED"
    MockTask.apply_async.assert_called_once()


def test_trigger_scan_rate_limited():
    with (
        patch("app.api.routers.scans.ImageService") as MockImgSvc,
        patch("app.api.routers.scans._check_user_rate_limit", return_value=False),
    ):
        MockImgSvc.return_value.get = AsyncMock(return_value=_mock_image())
        resp = TestClient(app).post(
            f"/api/images/{IMAGE_ID}/scans",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 429


def test_trigger_scan_404_when_image_not_found():
    with (
        patch("app.api.routers.scans.ImageService") as MockImgSvc,
        patch("app.api.routers.scans._check_user_rate_limit", return_value=True),
    ):
        MockImgSvc.return_value.get = AsyncMock(return_value=None)
        resp = TestClient(app).post(
            f"/api/images/{IMAGE_ID}/scans",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 404


def test_get_scan_returns_200():
    with (
        patch("app.api.routers.scans.ScanService") as MockScanSvc,
        patch("app.api.routers.scans.ImageService") as MockImgSvc,
    ):
        MockScanSvc.return_value.get = AsyncMock(return_value=_mock_scan(ScanStatus.SUCCEEDED))
        MockImgSvc.return_value.get = AsyncMock(return_value=_mock_image())
        resp = TestClient(app).get(
            f"/api/scans/{SCAN_ID}",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUCCEEDED"


def test_get_scan_returns_404_for_other_team():
    """scan_id belonging to another team must return 404 (not 403) to avoid enumeration."""
    with (
        patch("app.api.routers.scans.ScanService") as MockScanSvc,
        patch("app.api.routers.scans.ImageService") as MockImgSvc,
    ):
        MockScanSvc.return_value.get = AsyncMock(return_value=_mock_scan(ScanStatus.SUCCEEDED))
        MockImgSvc.return_value.get = AsyncMock(return_value=None)  # not in user's teams
        resp = TestClient(app).get(
            f"/api/scans/{SCAN_ID}",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 404


def test_get_findings_returns_200():
    mock_finding = MagicMock()
    mock_finding.id = uuid.uuid4()
    mock_finding.scan_id = uuid.UUID(SCAN_ID)
    mock_finding.vuln_id = "CVE-2024-1234"
    mock_finding.pkg_name = "libssl3"
    mock_finding.installed_version = "3.0.2"
    mock_finding.fixed_version = "3.0.14"
    mock_finding.severity = "CRITICAL"
    mock_finding.target = "debian"
    mock_finding.title = "OpenSSL vuln"
    mock_finding.primary_url = None
    mock_finding.is_fixable = True
    mock_finding.status = "OPEN"

    with (
        patch("app.api.routers.scans.ScanService") as MockScanSvc,
        patch("app.api.routers.scans.ImageService") as MockImgSvc,
        patch("app.api.routers.scans.get_findings_for_scan", return_value=[mock_finding]),
    ):
        MockScanSvc.return_value.get = AsyncMock(return_value=_mock_scan(ScanStatus.SUCCEEDED))
        MockImgSvc.return_value.get = AsyncMock(return_value=_mock_image())
        resp = TestClient(app).get(
            f"/api/scans/{SCAN_ID}/findings",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
