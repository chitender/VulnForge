import time
from unittest.mock import patch

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwt


def _make_rsa_key():
    return rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )


def _make_token(private_key, sub: str = "user-123", roles: list | None = None) -> str:
    payload = {
        "sub": sub,
        "email": "test@example.com",
        "name": "Test User",
        "realm_access": {"roles": roles or ["viewer"]},
        "patchpilot_teams": ["team-uuid-1"],
        "aud": "patchpilot-backend",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


@pytest.fixture
def client_with_mock_jwks():
    """TestClient with JWKS mocked to a known RSA key."""
    from app.core import auth as auth_module
    from app.main import app

    private_key = _make_rsa_key()
    public_key = private_key.public_key()

    # Build a minimal JWKS dict that python-jose can verify against
    from jose.backends import RSAKey
    from jose.utils import base64url_encode
    import struct

    # Export public key numbers for JWKS
    pub_numbers = public_key.public_numbers()
    e_bytes = pub_numbers.e.to_bytes((pub_numbers.e.bit_length() + 7) // 8, "big")
    n_bytes = pub_numbers.n.to_bytes((pub_numbers.n.bit_length() + 7) // 8, "big")

    fake_jwks = {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": "test-key",
                "n": base64url_encode(n_bytes).decode(),
                "e": base64url_encode(e_bytes).decode(),
            }
        ]
    }

    auth_module._get_jwks.cache_clear()
    with patch.object(auth_module, "_get_jwks", return_value=fake_jwks):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c, private_key


def test_protected_endpoint_rejects_no_token():
    from app.main import app
    with TestClient(app) as c:
        resp = c.get("/api/me")
    assert resp.status_code in (401, 403)  # HTTPBearer returns 403 pre-0.111, 401 after


def test_healthz_is_public():
    from app.main import app
    with TestClient(app) as c:
        resp = c.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_me_returns_user_info(client_with_mock_jwks):
    client, private_key = client_with_mock_jwks
    token = _make_token(private_key)
    resp = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert data["sub"] == "user-123"
    assert "viewer" in data["roles"]


def test_invalid_token_returns_401(client_with_mock_jwks):
    client, _ = client_with_mock_jwks
    resp = client.get("/api/me", headers={"Authorization": "Bearer not.a.real.token"})
    assert resp.status_code == 401
