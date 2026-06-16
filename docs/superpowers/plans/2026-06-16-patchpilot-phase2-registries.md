# PatchPilot Phase 2 — Registries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Full registry CRUD API with per-record envelope encryption, five registry-type credential adapters (ECR / ACR / GAR / Docker Hub / Generic OCI), exponential backoff on throttle responses, per-registry Redis concurrency semaphore, and a `/validate` endpoint that tests real credentials without storing them in plaintext.

**Architecture:** `RegistryService` owns all DB writes and encrypts creds via `CredentialStore` before insert. Adapters live in `workers/registry_adapters/` and expose `get_trivy_env(creds, registry)` for scan tasks and `validate(creds, registry)` for the validate endpoint. Credentials are write-only in every Pydantic response schema.

**Tech Stack:** FastAPI, SQLAlchemy async, `CredentialStore` (Phase 1), boto3 (ECR), azure-identity + azure-containerregistry (ACR), google-auth (GAR), requests (Docker Hub / Generic). Redis semaphore via `redis-py`.

---

## Task 7: Registry schemas + CRUD service

**Files:**
- Create: `backend/app/schemas/registry.py`
- Create: `backend/app/services/registry_service.py`
- Create: `backend/tests/test_registry_service.py`

- [ ] **Step 1: Write failing test `backend/tests/test_registry_service.py`**

```python
import pytest
from cryptography.fernet import Fernet
from unittest.mock import patch
from app.services.registry_service import RegistryService
from app.models.registry import RegistryType
from app.core.credentials import CredentialStore, LocalKEKProvider

MASTER_KEY = Fernet.generate_key().decode()


@pytest.fixture
def store():
    return CredentialStore(LocalKEKProvider(MASTER_KEY))


@pytest.fixture
def service(store):
    return RegistryService(credential_store=store)


@pytest.mark.asyncio
async def test_create_registry_encrypts_creds(db, service):
    registry = await service.create(
        db=db,
        owner_id="00000000-0000-0000-0000-000000000001",
        team_id="00000000-0000-0000-0000-000000000002",
        name="My ECR",
        registry_type=RegistryType.ECR,
        registry_url="123456789.dkr.ecr.us-east-1.amazonaws.com",
        region="us-east-1",
        creds={"aws_access_key_id": "AKIA...", "aws_secret_access_key": "secret"},
    )
    assert registry.auth_ciphertext is not None
    assert registry.auth_dek_enc is not None
    # Plaintext must NOT be in the ciphertext bytes
    assert b"AKIA" not in registry.auth_ciphertext
    assert b"secret" not in registry.auth_ciphertext


@pytest.mark.asyncio
async def test_list_registries_excludes_deleted(db, service):
    await service.create(
        db=db,
        owner_id="00000000-0000-0000-0000-000000000001",
        team_id="00000000-0000-0000-0000-000000000002",
        name="Active",
        registry_type=RegistryType.DOCKERHUB,
        registry_url="registry-1.docker.io",
        region=None,
        creds={"username": "user", "password": "pass"},
    )
    rows = await service.list(db=db, team_id="00000000-0000-0000-0000-000000000002")
    assert any(r.name == "Active" for r in rows)


@pytest.mark.asyncio
async def test_delete_soft_deletes(db, service):
    reg = await service.create(
        db=db,
        owner_id="00000000-0000-0000-0000-000000000001",
        team_id="00000000-0000-0000-0000-000000000003",
        name="ToDelete",
        registry_type=RegistryType.GENERIC_OCI,
        registry_url="myregistry.example.com",
        region=None,
        creds={"username": "u", "password": "p"},
    )
    await service.delete(db=db, registry_id=str(reg.id), team_id="00000000-0000-0000-0000-000000000003")
    rows = await service.list(db=db, team_id="00000000-0000-0000-0000-000000000003")
    assert not any(r.id == reg.id for r in rows)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && pytest tests/test_registry_service.py -v
```

Expected: `ImportError: cannot import name 'RegistryService'`

- [ ] **Step 3: Write `backend/app/schemas/registry.py`**

```python
from __future__ import annotations
import uuid
from typing import Any
from pydantic import BaseModel, Field, ConfigDict
from app.models.registry import RegistryType


class RegistryCreate(BaseModel):
    name: str
    type: RegistryType
    registry_url: str
    region: str | None = None
    credentials: dict[str, Any] = Field(
        ..., description="Type-specific creds. Write-only — never returned."
    )


class RegistryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: RegistryType
    registry_url: str
    region: str | None
    team_id: uuid.UUID
    # credentials intentionally absent
```

- [ ] **Step 4: Write `backend/app/services/registry_service.py`**

```python
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.credentials import CredentialStore
from app.models.registry import Registry, RegistryType


class RegistryService:
    def __init__(self, credential_store: CredentialStore | None = None):
        self._store = credential_store or CredentialStore()

    async def create(
        self,
        db: AsyncSession,
        owner_id: str,
        team_id: str,
        name: str,
        registry_type: RegistryType,
        registry_url: str,
        region: str | None,
        creds: dict[str, Any],
    ) -> Registry:
        ciphertext, dek_enc = self._store.encrypt(creds)
        reg = Registry(
            owner_id=uuid.UUID(owner_id),
            team_id=uuid.UUID(team_id),
            name=name,
            type=registry_type,
            registry_url=registry_url,
            region=region,
            auth_ciphertext=ciphertext,
            auth_dek_enc=dek_enc,
        )
        db.add(reg)
        await db.commit()
        await db.refresh(reg)
        return reg

    async def list(self, db: AsyncSession, team_id: str) -> list[Registry]:
        result = await db.execute(
            select(Registry).where(
                Registry.team_id == uuid.UUID(team_id),
                Registry.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, registry_id: str, team_id: str) -> Registry | None:
        result = await db.execute(
            select(Registry).where(
                Registry.id == uuid.UUID(registry_id),
                Registry.team_id == uuid.UUID(team_id),
                Registry.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def delete(self, db: AsyncSession, registry_id: str, team_id: str) -> bool:
        reg = await self.get(db, registry_id, team_id)
        if not reg:
            return False
        reg.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        return True

    def decrypt_creds(self, reg: Registry) -> dict[str, Any]:
        return self._store.decrypt(reg.auth_ciphertext, reg.auth_dek_enc)
```

- [ ] **Step 5: Run tests**

```bash
cd backend && pytest tests/test_registry_service.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/registry.py backend/app/services/registry_service.py \
        backend/tests/test_registry_service.py
git commit -m "feat: RegistryService with envelope encryption, soft-delete, team scoping"
```

---

## Task 8: Registry adapters — base + Docker Hub + Generic OCI

**Files:**
- Create: `backend/app/workers/registry_adapters/base.py`
- Create: `backend/app/workers/registry_adapters/dockerhub.py`
- Create: `backend/app/workers/registry_adapters/generic.py`
- Modify: `backend/app/workers/registry_adapters/__init__.py`
- Create: `backend/tests/test_adapters.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_adapters.py
import pytest
from app.workers.registry_adapters import get_adapter
from app.models.registry import RegistryType, Registry
import uuid


def make_registry(rtype: RegistryType, url: str = "registry.example.com") -> Registry:
    reg = Registry.__new__(Registry)
    reg.id = uuid.uuid4()
    reg.type = rtype
    reg.registry_url = url
    reg.region = None
    return reg


def test_dockerhub_trivy_env():
    adapter = get_adapter(RegistryType.DOCKERHUB)
    creds = {"username": "myuser", "password": "mypass"}
    env = adapter.get_trivy_env(creds, make_registry(RegistryType.DOCKERHUB))
    assert env["TRIVY_USERNAME"] == "myuser"
    assert env["TRIVY_PASSWORD"] == "mypass"


def test_generic_oci_trivy_env():
    adapter = get_adapter(RegistryType.GENERIC_OCI)
    creds = {"username": "u", "password": "p"}
    env = adapter.get_trivy_env(creds, make_registry(RegistryType.GENERIC_OCI))
    assert env["TRIVY_USERNAME"] == "u"
    assert env["TRIVY_PASSWORD"] == "p"


def test_get_adapter_raises_for_unknown():
    with pytest.raises(ValueError, match="No adapter"):
        get_adapter("UNKNOWN_TYPE")  # type: ignore
```

- [ ] **Step 2: Write `backend/app/workers/registry_adapters/base.py`**

```python
from __future__ import annotations
import time
import random
from abc import ABC, abstractmethod
from typing import Any
import requests


class BaseRegistryAdapter(ABC):
    @abstractmethod
    def get_trivy_env(self, creds: dict[str, Any], registry: Any) -> dict[str, str]:
        """Return env vars to pass to the trivy subprocess for this registry type."""

    @abstractmethod
    def validate(self, creds: dict[str, Any], registry: Any) -> None:
        """Raise ValueError if creds are invalid or registry unreachable."""

    def _request_with_backoff(
        self,
        method: str,
        url: str,
        max_retries: int = 5,
        **kwargs: Any,
    ) -> requests.Response:
        base_delay = 2.0
        cap = 60.0
        for attempt in range(max_retries):
            resp = requests.request(method, url, timeout=15, **kwargs)
            if resp.status_code == 429:
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), cap)
                time.sleep(delay)
                continue
            return resp
        raise RuntimeError(f"Registry throttled after {max_retries} retries: {url}")
```

- [ ] **Step 3: Write `backend/app/workers/registry_adapters/dockerhub.py`**

```python
from typing import Any
from app.workers.registry_adapters.base import BaseRegistryAdapter


class DockerHubAdapter(BaseRegistryAdapter):
    def get_trivy_env(self, creds: dict[str, Any], registry: Any) -> dict[str, str]:
        return {
            "TRIVY_USERNAME": creds["username"],
            "TRIVY_PASSWORD": creds["password"],
        }

    def validate(self, creds: dict[str, Any], registry: Any) -> None:
        resp = self._request_with_backoff(
            "GET",
            "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/alpine:pull",
            auth=(creds["username"], creds["password"]),
        )
        if resp.status_code == 401:
            raise ValueError("Docker Hub credentials invalid")
        resp.raise_for_status()
```

- [ ] **Step 4: Write `backend/app/workers/registry_adapters/generic.py`**

```python
from typing import Any
import requests
from app.workers.registry_adapters.base import BaseRegistryAdapter


class GenericOCIAdapter(BaseRegistryAdapter):
    def get_trivy_env(self, creds: dict[str, Any], registry: Any) -> dict[str, str]:
        return {
            "TRIVY_USERNAME": creds["username"],
            "TRIVY_PASSWORD": creds["password"],
        }

    def validate(self, creds: dict[str, Any], registry: Any) -> None:
        url = f"https://{registry.registry_url}/v2/"
        resp = self._request_with_backoff(
            "GET", url, auth=(creds["username"], creds["password"])
        )
        if resp.status_code in (401, 403):
            raise ValueError(f"Registry credentials invalid for {registry.registry_url}")
        if resp.status_code not in (200, 401):
            raise ValueError(f"Registry unreachable: {resp.status_code}")
```

- [ ] **Step 5: Write `backend/app/workers/registry_adapters/__init__.py`**

```python
from app.models.registry import RegistryType
from app.workers.registry_adapters.base import BaseRegistryAdapter
from app.workers.registry_adapters.dockerhub import DockerHubAdapter
from app.workers.registry_adapters.generic import GenericOCIAdapter

_ADAPTERS: dict[RegistryType, BaseRegistryAdapter] = {
    RegistryType.DOCKERHUB: DockerHubAdapter(),
    RegistryType.GENERIC_OCI: GenericOCIAdapter(),
}


def get_adapter(registry_type: RegistryType) -> BaseRegistryAdapter:
    adapter = _ADAPTERS.get(registry_type)
    if adapter is None:
        raise ValueError(f"No adapter registered for registry type: {registry_type}")
    return adapter
```

- [ ] **Step 6: Run tests**

```bash
cd backend && pytest tests/test_adapters.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/workers/registry_adapters/ backend/tests/test_adapters.py
git commit -m "feat: registry adapter base + DockerHub + Generic OCI with backoff"
```

---

## Task 9: ECR, ACR, GAR adapters

**Files:**
- Create: `backend/app/workers/registry_adapters/ecr.py`
- Create: `backend/app/workers/registry_adapters/acr.py`
- Create: `backend/app/workers/registry_adapters/gar.py`
- Modify: `backend/app/workers/registry_adapters/__init__.py`

- [ ] **Step 1: Write `backend/app/workers/registry_adapters/ecr.py`**

```python
from typing import Any
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from app.workers.registry_adapters.base import BaseRegistryAdapter


class ECRAdapter(BaseRegistryAdapter):
    def get_trivy_env(self, creds: dict[str, Any], registry: Any) -> dict[str, str]:
        token = self._get_ecr_token(creds, registry.region)
        return {
            "AWS_ACCESS_KEY_ID": creds.get("aws_access_key_id", ""),
            "AWS_SECRET_ACCESS_KEY": creds.get("aws_secret_access_key", ""),
            "AWS_DEFAULT_REGION": registry.region or "us-east-1",
        }

    def _get_ecr_token(self, creds: dict[str, Any], region: str | None) -> str:
        session = boto3.Session(
            aws_access_key_id=creds.get("aws_access_key_id"),
            aws_secret_access_key=creds.get("aws_secret_access_key"),
            region_name=region or "us-east-1",
        )
        ecr = session.client("ecr")
        resp = ecr.get_authorization_token()
        return resp["authorizationData"][0]["authorizationToken"]

    def validate(self, creds: dict[str, Any], registry: Any) -> None:
        try:
            self._get_ecr_token(creds, registry.region)
        except (ClientError, NoCredentialsError) as exc:
            raise ValueError(f"ECR credentials invalid: {exc}") from exc
```

- [ ] **Step 2: Write `backend/app/workers/registry_adapters/acr.py`**

```python
from typing import Any
from azure.identity import ClientSecretCredential
from azure.containerregistry import ContainerRegistryClient
from app.workers.registry_adapters.base import BaseRegistryAdapter


class ACRAdapter(BaseRegistryAdapter):
    def get_trivy_env(self, creds: dict[str, Any], registry: Any) -> dict[str, str]:
        return {
            "TRIVY_USERNAME": creds["client_id"],
            "TRIVY_PASSWORD": creds["client_secret"],
        }

    def validate(self, creds: dict[str, Any], registry: Any) -> None:
        try:
            credential = ClientSecretCredential(
                tenant_id=creds["tenant_id"],
                client_id=creds["client_id"],
                client_secret=creds["client_secret"],
            )
            client = ContainerRegistryClient(
                endpoint=f"https://{registry.registry_url}",
                credential=credential,
            )
            next(client.list_repository_names(), None)
        except Exception as exc:
            raise ValueError(f"ACR credentials invalid: {exc}") from exc
```

- [ ] **Step 3: Write `backend/app/workers/registry_adapters/gar.py`**

```python
from typing import Any
import google.auth
import google.auth.transport.requests
from google.oauth2 import service_account
from app.workers.registry_adapters.base import BaseRegistryAdapter


class GARAdapter(BaseRegistryAdapter):
    def get_trivy_env(self, creds: dict[str, Any], registry: Any) -> dict[str, str]:
        token = self._get_token(creds)
        return {
            "TRIVY_USERNAME": "oauth2accesstoken",
            "TRIVY_PASSWORD": token,
        }

    def _get_token(self, creds: dict[str, Any]) -> str:
        sa_creds = service_account.Credentials.from_service_account_info(
            creds["service_account_json"],
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        request = google.auth.transport.requests.Request()
        sa_creds.refresh(request)
        return sa_creds.token

    def validate(self, creds: dict[str, Any], registry: Any) -> None:
        try:
            self._get_token(creds)
        except Exception as exc:
            raise ValueError(f"GAR credentials invalid: {exc}") from exc
```

- [ ] **Step 4: Register all adapters in `backend/app/workers/registry_adapters/__init__.py`**

```python
from app.models.registry import RegistryType
from app.workers.registry_adapters.base import BaseRegistryAdapter
from app.workers.registry_adapters.dockerhub import DockerHubAdapter
from app.workers.registry_adapters.generic import GenericOCIAdapter
from app.workers.registry_adapters.ecr import ECRAdapter
from app.workers.registry_adapters.acr import ACRAdapter
from app.workers.registry_adapters.gar import GARAdapter

_ADAPTERS: dict[RegistryType, BaseRegistryAdapter] = {
    RegistryType.DOCKERHUB: DockerHubAdapter(),
    RegistryType.GENERIC_OCI: GenericOCIAdapter(),
    RegistryType.ECR: ECRAdapter(),
    RegistryType.ACR: ACRAdapter(),
    RegistryType.GAR: GARAdapter(),
}


def get_adapter(registry_type: RegistryType) -> BaseRegistryAdapter:
    adapter = _ADAPTERS.get(registry_type)
    if adapter is None:
        raise ValueError(f"No adapter registered for registry type: {registry_type}")
    return adapter
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/workers/registry_adapters/
git commit -m "feat: ECR + ACR + GAR registry adapters"
```

---

## Task 10: Registry API router + /validate endpoint

**Files:**
- Create: `backend/app/api/routers/registries.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_registry_api.py`

- [ ] **Step 1: Write failing test `backend/tests/test_registry_api.py`**

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

client = TestClient(app, raise_server_exceptions=True)


def auth_headers():
    # In test, override get_current_user to return a test user
    return {}  # patched below


@pytest.fixture(autouse=True)
def mock_auth():
    test_user = {
        "sub": "user-sub-123",
        "email": "dev@example.com",
        "name": "Dev User",
        "realm_access": {"roles": ["editor"]},
        "patchpilot_teams": ["00000000-0000-0000-0000-000000000010"],
    }
    with patch("app.core.auth.get_current_user", return_value=test_user):
        with patch("app.api.deps.get_current_user", return_value=test_user):
            yield test_user


def test_create_registry_returns_201(mock_auth):
    with patch("app.api.routers.registries.RegistryService") as MockSvc:
        mock_reg = MagicMock()
        mock_reg.id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        mock_reg.name = "My ECR"
        mock_reg.type = "ECR"
        mock_reg.registry_url = "123.dkr.ecr.us-east-1.amazonaws.com"
        mock_reg.region = "us-east-1"
        mock_reg.team_id = "00000000-0000-0000-0000-000000000010"
        MockSvc.return_value.create = MagicMock(return_value=mock_reg)

        resp = client.post(
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
    assert "credentials" not in data
    assert data["name"] == "My ECR"


def test_credentials_never_in_response(mock_auth):
    with patch("app.api.routers.registries.RegistryService") as MockSvc:
        mock_reg = MagicMock()
        mock_reg.id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        mock_reg.name = "DockerHub"
        mock_reg.type = "DOCKERHUB"
        mock_reg.registry_url = "registry-1.docker.io"
        mock_reg.region = None
        mock_reg.team_id = "00000000-0000-0000-0000-000000000010"
        MockSvc.return_value.list = MagicMock(return_value=[mock_reg])

        resp = client.get("/api/registries", headers={"Authorization": "Bearer fake"})

    assert resp.status_code == 200
    for reg in resp.json():
        assert "credentials" not in reg
        assert "auth_ciphertext" not in reg
        assert "auth_dek_enc" not in reg
```

- [ ] **Step 2: Write `backend/app/api/routers/registries.py`**

```python
from __future__ import annotations
import uuid
from typing import Any
from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, CurrentUser
from app.schemas.registry import RegistryCreate, RegistryResponse
from app.services.registry_service import RegistryService
from app.workers.registry_adapters import get_adapter
import structlog

router = APIRouter(prefix="/api/registries", tags=["registries"])
log = structlog.get_logger()


def _team_ids(user: dict) -> list[str]:
    return user.get("patchpilot_teams", [])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RegistryResponse)
async def create_registry(body: RegistryCreate, user: CurrentUser, db: DB) -> Any:
    teams = _team_ids(user)
    if not teams:
        raise HTTPException(400, "User has no team membership")
    svc = RegistryService()
    reg = await svc.create(
        db=db,
        owner_id=user["sub"],
        team_id=teams[0],
        name=body.name,
        registry_type=body.type,
        registry_url=body.registry_url,
        region=body.region,
        creds=body.credentials,
    )
    log.info("registry_created", registry_id=str(reg.id), type=body.type)
    return reg


@router.get("", response_model=list[RegistryResponse])
async def list_registries(user: CurrentUser, db: DB) -> Any:
    svc = RegistryService()
    rows = []
    for team_id in _team_ids(user):
        rows.extend(await svc.list(db=db, team_id=team_id))
    return rows


@router.delete("/{registry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_registry(registry_id: str, user: CurrentUser, db: DB) -> None:
    svc = RegistryService()
    for team_id in _team_ids(user):
        deleted = await svc.delete(db=db, registry_id=registry_id, team_id=team_id)
        if deleted:
            return
    raise HTTPException(status_code=404, detail="Registry not found")


@router.post("/{registry_id}/validate", status_code=status.HTTP_200_OK)
async def validate_registry(registry_id: str, user: CurrentUser, db: DB) -> dict:
    svc = RegistryService()
    reg = None
    for team_id in _team_ids(user):
        reg = await svc.get(db=db, registry_id=registry_id, team_id=team_id)
        if reg:
            break
    if not reg:
        raise HTTPException(status_code=404, detail="Registry not found")

    creds = svc.decrypt_creds(reg)
    adapter = get_adapter(reg.type)
    try:
        adapter.validate(creds, reg)
        return {"status": "ok"}
    except ValueError as exc:
        return {"status": "failed", "detail": str(exc)}
    except Exception as exc:
        log.error("validate_error", registry_id=registry_id, error=str(exc))
        return {"status": "failed", "detail": "Connection error"}
```

- [ ] **Step 3: Register router in `backend/app/main.py`**

```python
# Add to existing main.py imports:
from app.api.routers import registries

# Add after app creation:
app.include_router(registries.router)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_registry_api.py -v
```

Expected: All 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routers/registries.py backend/app/main.py \
        backend/tests/test_registry_api.py
git commit -m "feat: registry CRUD API + /validate endpoint — creds never in response"
```

---

## Task 11: Per-registry Redis concurrency semaphore

**Files:**
- Create: `backend/app/core/semaphore.py`
- Create: `backend/tests/test_semaphore.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_semaphore.py
import pytest
from unittest.mock import MagicMock, patch
from app.core.semaphore import RegistrySemaphore


def test_acquire_returns_true_when_under_cap():
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 3
    sem = RegistrySemaphore(redis_client=mock_redis, max_per_registry=10)
    assert sem.acquire("reg-id-1") is True


def test_acquire_returns_false_when_at_cap():
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 11
    sem = RegistrySemaphore(redis_client=mock_redis, max_per_registry=10)
    assert sem.acquire("reg-id-1") is False
    mock_redis.decr.assert_called_once()


def test_release_decrements_counter():
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 1
    sem = RegistrySemaphore(redis_client=mock_redis, max_per_registry=10)
    sem.acquire("reg-id-2")
    sem.release("reg-id-2")
    mock_redis.decr.assert_called_once()
```

- [ ] **Step 2: Write `backend/app/core/semaphore.py`**

```python
from __future__ import annotations
import redis as redis_lib
from app.core.config import settings

_DEFAULT_TTL = 1020  # same as task time limit


class RegistrySemaphore:
    def __init__(
        self,
        redis_client: redis_lib.Redis | None = None,
        max_per_registry: int = 10,
    ):
        self._redis = redis_client or redis_lib.from_url(settings.REDIS_URL)
        self._max = max_per_registry

    def _key(self, registry_id: str) -> str:
        return f"registry_sem:{registry_id}"

    def acquire(self, registry_id: str) -> bool:
        key = self._key(registry_id)
        current = self._redis.incr(key)
        self._redis.expire(key, _DEFAULT_TTL)
        if current > self._max:
            self._redis.decr(key)
            return False
        return True

    def release(self, registry_id: str) -> None:
        self._redis.decr(self._key(registry_id))
```

- [ ] **Step 3: Run tests**

```bash
cd backend && pytest tests/test_semaphore.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/semaphore.py backend/tests/test_semaphore.py
git commit -m "feat: per-registry Redis concurrency semaphore (max 10/registry)"
```

---

**Phase 2 complete.** Registry CRUD API is live, all five registry types have adapters, credentials are envelope-encrypted per record and never returned in responses, the `/validate` endpoint tests real creds, and the Redis semaphore caps per-registry concurrent pulls.
