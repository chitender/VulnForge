import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

TEST_USER = {
    "sub": "user-sub-123",
    "email": "dev@example.com",
    "realm_access": {"roles": ["editor"]},
    "patchpilot_teams": ["00000000-0000-0000-0000-000000000010"],
}

IMAGE_PAYLOAD = {
    "registry_id": "00000000-0000-0000-0000-000000000030",
    "repository": "myorg/payments-api",
    "tag": "1.4.2",
    "service_type": "BACKEND",
    "base_dockerfile_path": "docker/Dockerfile.base",
    "app_dockerfile_path": "Dockerfile",
    "gitlab_project_id": "myorg/payments-api",
    "gitlab_default_branch": "main",
}


@pytest.fixture(autouse=True)
def mock_auth():
    with patch("app.core.auth._decode_token", return_value=TEST_USER):
        yield


def _mock_image(**overrides) -> MagicMock:
    img = MagicMock()
    img.id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    img.registry_id = uuid.UUID("00000000-0000-0000-0000-000000000030")
    img.team_id = uuid.UUID("00000000-0000-0000-0000-000000000010")
    img.repository = "myorg/payments-api"
    img.tag = "1.4.2"
    img.last_digest = None
    img.service_type = "BACKEND"
    img.base_dockerfile_path = "docker/Dockerfile.base"
    img.app_dockerfile_path = "Dockerfile"
    img.gitlab_project_id = "myorg/payments-api"
    img.gitlab_default_branch = "main"
    for k, v in overrides.items():
        setattr(img, k, v)
    return img


def test_create_image_returns_201():
    with patch("app.api.routers.images.ImageService") as MockSvc:
        MockSvc.return_value.create = AsyncMock(return_value=_mock_image())
        resp = TestClient(app).post(
            "/api/images",
            json=IMAGE_PAYLOAD,
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["repository"] == "myorg/payments-api"
    assert data["service_type"] == "BACKEND"


def test_list_images_returns_200():
    with patch("app.api.routers.images.ImageService") as MockSvc:
        MockSvc.return_value.list = AsyncMock(return_value=[_mock_image()])
        resp = TestClient(app).get("/api/images", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 1


def test_get_image_returns_200():
    with patch("app.api.routers.images.ImageService") as MockSvc:
        MockSvc.return_value.get = AsyncMock(return_value=_mock_image())
        resp = TestClient(app).get(
            "/api/images/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200


def test_get_image_returns_404_when_not_found():
    with patch("app.api.routers.images.ImageService") as MockSvc:
        MockSvc.return_value.get = AsyncMock(return_value=None)
        resp = TestClient(app).get(
            "/api/images/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 404


def test_update_image_returns_200():
    with patch("app.api.routers.images.ImageService") as MockSvc:
        MockSvc.return_value.update = AsyncMock(return_value=_mock_image(tag="1.4.3"))
        resp = TestClient(app).put(
            "/api/images/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            json={"tag": "1.4.3"},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    assert resp.json()["tag"] == "1.4.3"


def test_delete_image_returns_204():
    with patch("app.api.routers.images.ImageService") as MockSvc:
        MockSvc.return_value.delete = AsyncMock(return_value=True)
        resp = TestClient(app).delete(
            "/api/images/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 204
