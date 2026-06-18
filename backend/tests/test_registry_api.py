import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

TEST_USER = {
    "sub": "user-sub-123",
    "email": "dev@example.com",
    "name": "Dev User",
    "realm_access": {"roles": ["editor"]},
    "patchpilot_teams": ["00000000-0000-0000-0000-000000000010"],
}


@pytest.fixture(autouse=True)
def mock_auth():
    with patch("app.core.auth._decode_token", return_value=TEST_USER):
        yield


def _client():
    return TestClient(app, raise_server_exceptions=True)


def _mock_registry(name: str = "My ECR", rtype: str = "ECR") -> MagicMock:
    reg = MagicMock()
    reg.id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    reg.name = name
    reg.type = rtype
    reg.registry_url = "123.dkr.ecr.us-east-1.amazonaws.com"
    reg.region = "us-east-1"
    reg.team_id = uuid.UUID("00000000-0000-0000-0000-000000000010")
    return reg


def test_create_registry_returns_201():
    with patch("app.api.routers.registries.RegistryService") as MockSvc:
        MockSvc.return_value.create = AsyncMock(return_value=_mock_registry())
        resp = _client().post(
            "/api/registries",
            json={
                "name": "My ECR",
                "type": "ECR",
                "registry_url": "123.dkr.ecr.us-east-1.amazonaws.com",
                "region": "us-east-1",
                "credentials": {"aws_access_key_id": "AKIA", "aws_secret_access_key": "secret"},
            },
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My ECR"


def test_credentials_never_in_response():
    with patch("app.api.routers.registries.RegistryService") as MockSvc:
        MockSvc.return_value.list = AsyncMock(
            return_value=[_mock_registry("DockerHub", "DOCKERHUB")]
        )
        resp = _client().get("/api/registries", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200
    for reg in resp.json():
        assert "credentials" not in reg
        assert "auth_ciphertext" not in reg
        assert "auth_dek_enc" not in reg


def test_validate_registry_ok():
    with patch("app.api.routers.registries.RegistryService") as MockSvc:
        mock_reg = _mock_registry()
        MockSvc.return_value.get = AsyncMock(return_value=mock_reg)
        MockSvc.return_value.decrypt_creds = MagicMock(
            return_value={"username": "u", "password": "p"}
        )
        with patch("app.api.routers.registries.get_adapter") as mock_get_adapter:
            mock_get_adapter.return_value.validate = MagicMock()
            resp = _client().post(
                "/api/registries/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/validate",
                headers={"Authorization": "Bearer fake"},
            )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_validate_registry_invalid_creds():
    with patch("app.api.routers.registries.RegistryService") as MockSvc:
        mock_reg = _mock_registry()
        MockSvc.return_value.get = AsyncMock(return_value=mock_reg)
        MockSvc.return_value.decrypt_creds = MagicMock(return_value={})
        with patch("app.api.routers.registries.get_adapter") as mock_get_adapter:
            mock_get_adapter.return_value.validate = MagicMock(
                side_effect=ValueError("Invalid credentials")
            )
            resp = _client().post(
                "/api/registries/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/validate",
                headers={"Authorization": "Bearer fake"},
            )
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"
    assert "Invalid credentials" in resp.json()["detail"]
