import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.merge_request import MRState, MRTargetKind, MRType, PipelineStatus

TEST_USER = {
    "sub": "user-sub-123",
    "email": "dev@example.com",
    "realm_access": {"roles": ["editor"]},
    "patchpilot_teams": ["00000000-0000-0000-0000-000000000010"],
}
SCAN_ID = str(uuid.uuid4())
MR_ID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def mock_auth():
    with patch("app.core.auth._decode_token", return_value=TEST_USER):
        yield


def _mock_mr() -> MagicMock:
    mr = MagicMock()
    mr.id = uuid.UUID(MR_ID)
    mr.image_id = uuid.uuid4()
    mr.scan_id = uuid.UUID(SCAN_ID)
    mr.mr_type = MRType.HOTFIX
    mr.target_kind = MRTargetKind.APP_DOCKERFILE
    mr.gitlab_project_id = "myorg/payments"
    mr.gitlab_mr_iid = 42
    mr.gitlab_mr_url = "https://gitlab.example.com/mr/42"
    mr.source_branch = "hotfix/payments-sec"
    mr.target_branch = "main"
    mr.state = MRState.OPENED
    mr.pipeline_status = PipelineStatus.UNKNOWN
    mr.finding_ids = []
    mr.image_digest = "sha256:abc"
    return mr


def test_raise_mr_returns_202():
    with patch("app.api.routers.merge_requests.ScanService") as MockScanSvc, \
         patch("app.api.routers.merge_requests.ImageService") as MockImgSvc, \
         patch("app.api.routers.merge_requests.dispatch_mr_task", return_value=True), \
         patch("app.api.routers.merge_requests.AuditService") as MockAudit:

        mock_scan = MagicMock()
        mock_scan.image_id = uuid.uuid4()
        mock_scan.image_digest = "sha256:abc"
        MockScanSvc.return_value.get = AsyncMock(return_value=mock_scan)
        mock_img = MagicMock()
        mock_img.repository = "myorg/payments"
        mock_img.tag = "1.0"
        mock_img.gitlab_project_id = "myorg/payments"
        mock_img.team_id = uuid.UUID("00000000-0000-0000-0000-000000000010")
        MockImgSvc.return_value.get = AsyncMock(return_value=mock_img)
        MockAudit.return_value.log = AsyncMock()

        resp = TestClient(app).post(
            "/api/merge-requests",
            json={
                "scan_id": SCAN_ID,
                "finding_ids": [str(uuid.uuid4())],
                "mr_type": "HOTFIX",
                "targets": ["APP_DOCKERFILE"],
                "source_branch_template": "hotfix/{image}-sec",
                "target_branch": "main",
                "gitlab_token": "glpat-fake",
                "template_vars": {},
            },
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["dispatched"][0]["queued"] is True


def test_list_mrs_returns_200():
    with patch("app.api.routers.merge_requests.ImageService") as MockImgSvc, \
         patch("app.api.routers.merge_requests.MRService") as MockMRSvc:
        MockImgSvc.return_value.list = AsyncMock(return_value=[MagicMock(id=uuid.uuid4())])
        MockMRSvc.return_value.list = AsyncMock(return_value=[_mock_mr()])
        resp = TestClient(app).get(
            "/api/merge-requests",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_sync_mr_returns_200():
    with patch("app.api.routers.merge_requests.MRService") as MockMRSvc, \
         patch("app.api.routers.merge_requests.ImageService") as MockImgSvc:
        mock_mr = _mock_mr()
        MockMRSvc.return_value.get = AsyncMock(return_value=mock_mr)
        MockMRSvc.return_value.update_pipeline_status = AsyncMock(return_value=mock_mr)
        mock_img = MagicMock()
        mock_img.team_id = uuid.UUID("00000000-0000-0000-0000-000000000010")
        MockImgSvc.return_value.get = AsyncMock(return_value=mock_img)
        resp = TestClient(app).post(
            f"/api/merge-requests/{MR_ID}/sync",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
