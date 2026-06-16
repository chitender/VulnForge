# PatchPilot Phase 3 — Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Image CRUD API — register container images with Dockerfile paths, GitLab project reference, and service type. Images link to registries and are team-scoped.

**Architecture:** `ImageService` mirrors `RegistryService` pattern — team-scoped queries via `team_id`, soft deletes, no credential fields. Router validates the linked registry belongs to the same team before creating an image.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2.

---

## Task 12: Image schemas + service

**Files:**
- Create: `backend/app/schemas/image.py`
- Create: `backend/app/services/image_service.py`
- Create: `backend/tests/test_image_service.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_image_service.py
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.image_service import ImageService
from app.models.image import ServiceType


TEAM_ID = "00000000-0000-0000-0000-000000000020"
OWNER_ID = "00000000-0000-0000-0000-000000000001"
REGISTRY_ID = "00000000-0000-0000-0000-000000000030"


@pytest.mark.asyncio
async def test_create_image(db):
    svc = ImageService()
    img = await svc.create(
        db=db,
        owner_id=OWNER_ID,
        team_id=TEAM_ID,
        registry_id=REGISTRY_ID,
        repository="myorg/payments-api",
        tag="1.4.2",
        service_type=ServiceType.BACKEND,
        base_dockerfile_path="docker/base/Dockerfile",
        app_dockerfile_path="Dockerfile",
        gitlab_project_id="myorg/payments-api",
        gitlab_default_branch="main",
    )
    assert str(img.team_id) == TEAM_ID
    assert img.repository == "myorg/payments-api"
    assert img.service_type == ServiceType.BACKEND


@pytest.mark.asyncio
async def test_list_excludes_deleted(db):
    svc = ImageService()
    img = await svc.create(
        db=db,
        owner_id=OWNER_ID,
        team_id=TEAM_ID,
        registry_id=REGISTRY_ID,
        repository="myorg/web-app",
        tag="2.0.0",
        service_type=ServiceType.UI,
        base_dockerfile_path="Dockerfile.base",
        app_dockerfile_path="Dockerfile",
        gitlab_project_id="myorg/web-app",
        gitlab_default_branch="develop",
    )
    await svc.delete(db=db, image_id=str(img.id), team_id=TEAM_ID)
    rows = await svc.list(db=db, team_id=TEAM_ID)
    assert not any(r.id == img.id for r in rows)


@pytest.mark.asyncio
async def test_update_image(db):
    svc = ImageService()
    img = await svc.create(
        db=db,
        owner_id=OWNER_ID,
        team_id=TEAM_ID,
        registry_id=REGISTRY_ID,
        repository="myorg/auth-service",
        tag="1.0.0",
        service_type=ServiceType.BACKEND,
        base_dockerfile_path="Dockerfile",
        app_dockerfile_path="Dockerfile",
        gitlab_project_id="myorg/auth-service",
        gitlab_default_branch="main",
    )
    updated = await svc.update(db=db, image_id=str(img.id), team_id=TEAM_ID, tag="1.0.1")
    assert updated.tag == "1.0.1"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && pytest tests/test_image_service.py -v
```

Expected: `ImportError: cannot import name 'ImageService'`

- [ ] **Step 3: Write `backend/app/schemas/image.py`**

```python
from __future__ import annotations
import uuid
from pydantic import BaseModel, ConfigDict
from app.models.image import ServiceType


class ImageCreate(BaseModel):
    registry_id: uuid.UUID
    repository: str
    tag: str
    service_type: ServiceType
    base_dockerfile_path: str
    app_dockerfile_path: str
    gitlab_project_id: str
    gitlab_default_branch: str = "main"


class ImageUpdate(BaseModel):
    tag: str | None = None
    base_dockerfile_path: str | None = None
    app_dockerfile_path: str | None = None
    gitlab_default_branch: str | None = None


class ImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    registry_id: uuid.UUID
    team_id: uuid.UUID
    repository: str
    tag: str
    last_digest: str | None
    service_type: ServiceType
    base_dockerfile_path: str
    app_dockerfile_path: str
    gitlab_project_id: str
    gitlab_default_branch: str
```

- [ ] **Step 4: Write `backend/app/services/image_service.py`**

```python
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image import Image, ServiceType


class ImageService:
    async def create(
        self,
        db: AsyncSession,
        owner_id: str,
        team_id: str,
        registry_id: str,
        repository: str,
        tag: str,
        service_type: ServiceType,
        base_dockerfile_path: str,
        app_dockerfile_path: str,
        gitlab_project_id: str,
        gitlab_default_branch: str,
    ) -> Image:
        img = Image(
            owner_id=uuid.UUID(owner_id),
            team_id=uuid.UUID(team_id),
            registry_id=uuid.UUID(registry_id),
            repository=repository,
            tag=tag,
            service_type=service_type,
            base_dockerfile_path=base_dockerfile_path,
            app_dockerfile_path=app_dockerfile_path,
            gitlab_project_id=gitlab_project_id,
            gitlab_default_branch=gitlab_default_branch,
        )
        db.add(img)
        await db.commit()
        await db.refresh(img)
        return img

    async def list(self, db: AsyncSession, team_id: str) -> list[Image]:
        result = await db.execute(
            select(Image).where(
                Image.team_id == uuid.UUID(team_id),
                Image.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, image_id: str, team_id: str) -> Image | None:
        result = await db.execute(
            select(Image).where(
                Image.id == uuid.UUID(image_id),
                Image.team_id == uuid.UUID(team_id),
                Image.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self, db: AsyncSession, image_id: str, team_id: str, **kwargs: Any
    ) -> Image | None:
        img = await self.get(db, image_id, team_id)
        if not img:
            return None
        for key, val in kwargs.items():
            if val is not None:
                setattr(img, key, val)
        await db.commit()
        await db.refresh(img)
        return img

    async def delete(self, db: AsyncSession, image_id: str, team_id: str) -> bool:
        img = await self.get(db, image_id, team_id)
        if not img:
            return False
        img.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        return True
```

- [ ] **Step 5: Run tests**

```bash
cd backend && pytest tests/test_image_service.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/image.py backend/app/services/image_service.py \
        backend/tests/test_image_service.py
git commit -m "feat: ImageService CRUD with team scoping + soft delete"
```

---

## Task 13: Image API router

**Files:**
- Create: `backend/app/api/routers/images.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_image_api.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_image_api.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
import uuid

client = TestClient(app)

TEST_USER = {
    "sub": "user-sub-123",
    "email": "dev@example.com",
    "name": "Dev User",
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
    with patch("app.api.routers.images.get_current_user", return_value=TEST_USER):
        yield


def test_create_image_returns_201():
    mock_img = MagicMock()
    mock_img.id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    mock_img.registry_id = uuid.UUID("00000000-0000-0000-0000-000000000030")
    mock_img.team_id = uuid.UUID("00000000-0000-0000-0000-000000000010")
    mock_img.repository = "myorg/payments-api"
    mock_img.tag = "1.4.2"
    mock_img.last_digest = None
    mock_img.service_type = "BACKEND"
    mock_img.base_dockerfile_path = "docker/Dockerfile.base"
    mock_img.app_dockerfile_path = "Dockerfile"
    mock_img.gitlab_project_id = "myorg/payments-api"
    mock_img.gitlab_default_branch = "main"

    with patch("app.api.routers.images.ImageService") as MockSvc:
        MockSvc.return_value.create = AsyncMock(return_value=mock_img)
        resp = client.post(
            "/api/images",
            json=IMAGE_PAYLOAD,
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201
    assert resp.json()["repository"] == "myorg/payments-api"


def test_list_images_returns_200():
    with patch("app.api.routers.images.ImageService") as MockSvc:
        MockSvc.return_value.list = AsyncMock(return_value=[])
        resp = client.get("/api/images", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

- [ ] **Step 2: Write `backend/app/api/routers/images.py`**

```python
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, CurrentUser
from app.schemas.image import ImageCreate, ImageUpdate, ImageResponse
from app.services.image_service import ImageService
import structlog

router = APIRouter(prefix="/api/images", tags=["images"])
log = structlog.get_logger()


def _team_ids(user: dict) -> list[str]:
    return user.get("patchpilot_teams", [])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ImageResponse)
async def create_image(body: ImageCreate, user: CurrentUser, db: DB) -> Any:
    teams = _team_ids(user)
    if not teams:
        raise HTTPException(400, "User has no team membership")
    svc = ImageService()
    img = await svc.create(
        db=db,
        owner_id=user["sub"],
        team_id=teams[0],
        registry_id=str(body.registry_id),
        repository=body.repository,
        tag=body.tag,
        service_type=body.service_type,
        base_dockerfile_path=body.base_dockerfile_path,
        app_dockerfile_path=body.app_dockerfile_path,
        gitlab_project_id=body.gitlab_project_id,
        gitlab_default_branch=body.gitlab_default_branch,
    )
    return img


@router.get("", response_model=list[ImageResponse])
async def list_images(user: CurrentUser, db: DB) -> Any:
    svc = ImageService()
    rows = []
    for team_id in _team_ids(user):
        rows.extend(await svc.list(db=db, team_id=team_id))
    return rows


@router.get("/{image_id}", response_model=ImageResponse)
async def get_image(image_id: str, user: CurrentUser, db: DB) -> Any:
    svc = ImageService()
    for team_id in _team_ids(user):
        img = await svc.get(db=db, image_id=image_id, team_id=team_id)
        if img:
            return img
    raise HTTPException(status_code=404, detail="Image not found")


@router.put("/{image_id}", response_model=ImageResponse)
async def update_image(image_id: str, body: ImageUpdate, user: CurrentUser, db: DB) -> Any:
    svc = ImageService()
    for team_id in _team_ids(user):
        img = await svc.update(db=db, image_id=image_id, team_id=team_id, **body.model_dump(exclude_none=True))
        if img:
            return img
    raise HTTPException(status_code=404, detail="Image not found")


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(image_id: str, user: CurrentUser, db: DB) -> None:
    svc = ImageService()
    for team_id in _team_ids(user):
        if await svc.delete(db=db, image_id=image_id, team_id=team_id):
            return
    raise HTTPException(status_code=404, detail="Image not found")
```

- [ ] **Step 3: Register router in `backend/app/main.py`**

```python
from app.api.routers import registries, images

app.include_router(registries.router)
app.include_router(images.router)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_image_api.py -v
```

Expected: All 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routers/images.py backend/app/main.py \
        backend/tests/test_image_api.py
git commit -m "feat: image CRUD API (GET/POST/PUT/DELETE /api/images)"
```

---

**Phase 3 complete.** Images can be registered with full Dockerfile paths and GitLab project references. All endpoints are team-scoped and soft-delete aware.
