# PatchPilot Phase 1 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the monorepo, wire all Docker Compose services, create the full Postgres schema with envelope-encryption columns, implement the `CredentialStore` abstraction, and wire Keycloak OIDC end-to-end so every subsequent phase builds on a running, authenticated foundation.

**Architecture:** FastAPI (Python 3.12) + SQLAlchemy 2.0 async + Alembic for the backend; React 18 + Vite + `@react-oidc-context` for the frontend; Keycloak for OIDC; envelope encryption (`CredentialStore`) wraps per-record DEKs with a `MASTER_KEY` KEK. All services run via Docker Compose locally.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, asyncpg, Alembic, python-jose, cryptography, React 18, TypeScript, Vite, @react-oidc-context, TanStack Query v5, Tailwind CSS, shadcn/ui, PostgreSQL 16, Redis 7, Keycloak 24, Docker Compose

---

## Task 1: Monorepo scaffold + Python environment

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.python-version`
- Create: `backend/app/__init__.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/routers/__init__.py`
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/tasks/__init__.py`
- Create: `backend/app/workers/__init__.py`
- Create: `backend/app/workers/registry_adapters/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `.gitignore`
- Create: `.env.example`

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p backend/app/{core,models,schemas,api/routers,services,tasks,workers/registry_adapters}
mkdir -p backend/{tests,alembic/versions}
mkdir -p frontend/src/{auth,api,lib,components/{layout,registries,images,scans,mr},pages}
mkdir -p infra/{keycloak,helm/patchpilot/templates}
mkdir -p .github/workflows
touch backend/app/__init__.py
touch backend/app/{core,models,schemas,services,tasks,workers}/__init__.py
touch backend/app/api/__init__.py backend/app/api/routers/__init__.py
touch backend/app/workers/registry_adapters/__init__.py
touch backend/tests/__init__.py
```

- [ ] **Step 2: Create `backend/pyproject.toml`**

```toml
[project]
name = "patchpilot-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "python-jose[cryptography]>=3.3",
    "cryptography>=42",
    "celery[redis]>=5.4",
    "redis>=5",
    "structlog>=24",
    "opentelemetry-sdk>=1.25",
    "opentelemetry-instrumentation-fastapi>=0.46b0",
    "opentelemetry-instrumentation-celery>=0.46b0",
    "python-gitlab>=4.5",
    "dockerfile-parse>=2.0",
    "boto3>=1.34",
    "azure-identity>=1.17",
    "azure-containerregistry>=1.2",
    "google-auth>=2.29",
    "requests>=2.31",
    "pydantic-settings>=2.3",
    "httpx>=0.27",
    "prometheus-client>=0.20",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5",
    "testcontainers[postgres]>=4",
    "ruff>=0.4",
    "mypy>=1.10",
    "types-requests>=2.31",
]

[tool.ruff]
target-version = "py312"
line-length = 100
select = ["E", "F", "I", "UP"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true
```

- [ ] **Step 3: Create `backend/.python-version`**

```
3.12
```

- [ ] **Step 4: Create `.env.example`**

```bash
# Backend
DATABASE_URL=postgresql+asyncpg://patchpilot:patchpilot@localhost:5432/patchpilot
REDIS_URL=redis://localhost:6379/0
MASTER_KEY=  # generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Keycloak
KEYCLOAK_URL=http://localhost:8080
KEYCLOAK_REALM=patchpilot
KEYCLOAK_CLIENT_ID=patchpilot-backend

# Trivy
TRIVY_SERVER_URL=http://localhost:4954

# Frontend
VITE_KEYCLOAK_URL=http://localhost:8080
VITE_KEYCLOAK_REALM=patchpilot
VITE_KEYCLOAK_CLIENT_ID=patchpilot-frontend
VITE_API_URL=http://localhost:8000
```

- [ ] **Step 5: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
dist/
node_modules/
.env
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
```

- [ ] **Step 6: Install backend dependencies**

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: All packages install without error.

- [ ] **Step 7: Commit**

```bash
git add backend/.python-version backend/pyproject.toml .gitignore .env.example
git commit -m "feat: monorepo scaffold + Python env"
```

---

## Task 2: Docker Compose — all seven services

**Files:**
- Create: `infra/docker-compose.yml`
- Create: `infra/keycloak/realm-export.json`

- [ ] **Step 1: Write `infra/docker-compose.yml`**

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: patchpilot
      POSTGRES_PASSWORD: patchpilot
      POSTGRES_DB: patchpilot
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U patchpilot"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --save 60 1 --loglevel warning
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  trivy-server:
    image: aquasec/trivy:latest
    command: server --listen 0.0.0.0:4954 --cache-dir /trivy-cache
    ports:
      - "4954:4954"
    volumes:
      - trivy_cache:/trivy-cache
    environment:
      TRIVY_LISTEN: "0.0.0.0:4954"

  keycloak:
    image: quay.io/keycloak/keycloak:24.0
    command: start-dev --import-realm
    environment:
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: admin
      KC_HTTP_PORT: 8080
    ports:
      - "8080:8080"
    volumes:
      - ./keycloak:/opt/keycloak/data/import
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8080/realms/master || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 20

  backend:
    build:
      context: ../backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - ../.env
    environment:
      DATABASE_URL: postgresql+asyncpg://patchpilot:patchpilot@postgres:5432/patchpilot
      REDIS_URL: redis://redis:6379/0
      TRIVY_SERVER_URL: http://trivy-server:4954
      KEYCLOAK_URL: http://keycloak:8080
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ../backend:/app

  worker:
    build:
      context: ../backend
      dockerfile: Dockerfile.worker
    env_file:
      - ../.env
    environment:
      DATABASE_URL: postgresql+asyncpg://patchpilot:patchpilot@postgres:5432/patchpilot
      REDIS_URL: redis://redis:6379/0
      TRIVY_SERVER_URL: http://trivy-server:4954
      KEYCLOAK_URL: http://keycloak:8080
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ../backend:/app

  frontend:
    build:
      context: ../frontend
      dockerfile: Dockerfile
    ports:
      - "5173:5173"
    environment:
      VITE_KEYCLOAK_URL: http://localhost:8080
      VITE_KEYCLOAK_REALM: patchpilot
      VITE_KEYCLOAK_CLIENT_ID: patchpilot-frontend
      VITE_API_URL: http://localhost:8000
    volumes:
      - ../frontend:/app
      - /app/node_modules

volumes:
  postgres_data:
  redis_data:
  trivy_cache:
```

- [ ] **Step 2: Create minimal `infra/keycloak/realm-export.json`**

```json
{
  "realm": "patchpilot",
  "enabled": true,
  "clients": [
    {
      "clientId": "patchpilot-frontend",
      "enabled": true,
      "publicClient": true,
      "redirectUris": ["http://localhost:5173/*"],
      "webOrigins": ["http://localhost:5173"],
      "standardFlowEnabled": true,
      "attributes": { "pkce.code.challenge.method": "S256" }
    },
    {
      "clientId": "patchpilot-backend",
      "enabled": true,
      "bearerOnly": true
    }
  ],
  "roles": {
    "realm": [
      { "name": "admin" },
      { "name": "editor" },
      { "name": "viewer" }
    ]
  },
  "users": [
    {
      "username": "dev-admin",
      "enabled": true,
      "credentials": [{ "type": "password", "value": "admin123", "temporary": false }],
      "realmRoles": ["admin"]
    }
  ]
}
```

- [ ] **Step 3: Verify Compose starts cleanly**

```bash
cd infra && docker compose up -d
docker compose ps
```

Expected: All 7 containers show `healthy` or `running` within 60s.

- [ ] **Step 4: Commit**

```bash
git add infra/
git commit -m "feat: Docker Compose with all 7 services + Keycloak realm"
```

---

## Task 3: SQLAlchemy models + Alembic initial migration

**Files:**
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/db.py`
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/registry.py`
- Create: `backend/app/models/image.py`
- Create: `backend/app/models/scan.py`
- Create: `backend/app/models/finding.py`
- Create: `backend/app/models/merge_request.py`
- Create: `backend/app/models/audit_log.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/001_initial_schema.py`
- Create: `backend/tests/test_models.py`

- [ ] **Step 1: Write `backend/app/core/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://patchpilot:patchpilot@localhost:5432/patchpilot"
    REDIS_URL: str = "redis://localhost:6379/0"
    MASTER_KEY: str = ""
    KEYCLOAK_URL: str = "http://localhost:8080"
    KEYCLOAK_REALM: str = "patchpilot"
    KEYCLOAK_CLIENT_ID: str = "patchpilot-backend"
    TRIVY_SERVER_URL: str = "http://localhost:4954"

settings = Settings()
```

- [ ] **Step 2: Write `backend/app/core/db.py`**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Sync engine for Celery tasks (asyncpg not available in prefork workers)
sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
sync_engine = create_engine(sync_url, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(sync_engine)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

Fix the missing import in db.py:

```python
from sqlalchemy.orm import Session, sessionmaker  # add sessionmaker
```

- [ ] **Step 3: Write `backend/app/models/base.py`**

```python
import uuid
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class TeamScopedMixin(TimestampMixin):
    team_id = Column(UUID(as_uuid=True), nullable=False, index=True)
```

- [ ] **Step 4: Write `backend/app/models/user.py`**

```python
import uuid
from sqlalchemy import Column, String, Enum
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base, TimestampMixin
import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keycloak_sub = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=False)
    name = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.VIEWER)
```

- [ ] **Step 5: Write `backend/app/models/registry.py`**

```python
import uuid
import enum
from sqlalchemy import Column, String, Enum, LargeBinary, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import Base, TeamScopedMixin


class RegistryType(str, enum.Enum):
    ECR = "ECR"
    ACR = "ACR"
    DOCKERHUB = "DOCKERHUB"
    GAR = "GAR"
    GENERIC_OCI = "GENERIC_OCI"


class Registry(Base, TeamScopedMixin):
    __tablename__ = "registries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(Enum(RegistryType), nullable=False)
    registry_url = Column(String, nullable=False)
    region = Column(String, nullable=True)
    auth_ciphertext = Column(LargeBinary, nullable=False)
    auth_dek_enc = Column(LargeBinary, nullable=False)

    images = relationship("Image", back_populates="registry", lazy="select")
```

- [ ] **Step 6: Write `backend/app/models/image.py`**

```python
import uuid
import enum
from sqlalchemy import Column, String, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import Base, TeamScopedMixin


class ServiceType(str, enum.Enum):
    UI = "UI"
    BACKEND = "BACKEND"


class Image(Base, TeamScopedMixin):
    __tablename__ = "images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    registry_id = Column(UUID(as_uuid=True), ForeignKey("registries.id"), nullable=False)
    repository = Column(String, nullable=False)
    tag = Column(String, nullable=False)
    last_digest = Column(String, nullable=True)
    service_type = Column(Enum(ServiceType), nullable=False)
    base_dockerfile_path = Column(String, nullable=False)
    app_dockerfile_path = Column(String, nullable=False)
    gitlab_project_id = Column(String, nullable=False)
    gitlab_default_branch = Column(String, nullable=False, default="main")

    registry = relationship("Registry", back_populates="images")
    scans = relationship("Scan", back_populates="image", lazy="select")
```

- [ ] **Step 7: Write `backend/app/models/scan.py`**

```python
import uuid
import enum
from sqlalchemy import Column, String, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin


class ScanStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Scan(Base, TimestampMixin):
    __tablename__ = "scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_id = Column(UUID(as_uuid=True), ForeignKey("images.id"), nullable=False)
    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(Enum(ScanStatus), nullable=False, default=ScanStatus.QUEUED)
    trivy_version = Column(String, nullable=True)
    db_version = Column(String, nullable=True)
    image_digest = Column(String, nullable=True)
    started_at = Column(String, nullable=True)
    finished_at = Column(String, nullable=True)
    summary_jsonb = Column(JSONB, nullable=True)
    raw_report_jsonb = Column(JSONB, nullable=True)
    error_text = Column(Text, nullable=True)

    image = relationship("Image", back_populates="scans")
    findings = relationship("Finding", back_populates="scan", lazy="select")
```

- [ ] **Step 8: Write `backend/app/models/finding.py`**

```python
import uuid
import enum
from sqlalchemy import Column, String, Enum, ForeignKey, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin


class Severity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class FindingStatus(str, enum.Enum):
    OPEN = "OPEN"
    SELECTED = "SELECTED"
    MR_RAISED = "MR_RAISED"
    IGNORED = "IGNORED"
    RESOLVED = "RESOLVED"


class Finding(Base, TimestampMixin):
    __tablename__ = "findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id = Column(UUID(as_uuid=True), ForeignKey("scans.id"), nullable=False)
    vuln_id = Column(String, nullable=False)
    pkg_name = Column(String, nullable=False)
    installed_version = Column(String, nullable=False)
    fixed_version = Column(String, nullable=True)
    severity = Column(Enum(Severity), nullable=False)
    target = Column(String, nullable=True)
    title = Column(Text, nullable=True)
    primary_url = Column(String, nullable=True)
    is_fixable = Column(Boolean, nullable=False, default=False)
    status = Column(Enum(FindingStatus), nullable=False, default=FindingStatus.OPEN)

    scan = relationship("Scan", back_populates="findings")
```

- [ ] **Step 9: Write `backend/app/models/merge_request.py`**

```python
import uuid
import enum
from sqlalchemy import Column, String, Enum, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin


class MRType(str, enum.Enum):
    FEATURE = "FEATURE"
    HOTFIX = "HOTFIX"


class MRTargetKind(str, enum.Enum):
    BASE_DOCKERFILE = "BASE_DOCKERFILE"
    APP_DOCKERFILE = "APP_DOCKERFILE"


class MRState(str, enum.Enum):
    OPENED = "OPENED"
    MERGED = "MERGED"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


class PipelineStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class MergeRequest(Base, TimestampMixin):
    __tablename__ = "merge_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_id = Column(UUID(as_uuid=True), ForeignKey("images.id"), nullable=False)
    scan_id = Column(UUID(as_uuid=True), ForeignKey("scans.id"), nullable=False)
    mr_type = Column(Enum(MRType), nullable=False)
    target_kind = Column(Enum(MRTargetKind), nullable=False)
    gitlab_project_id = Column(String, nullable=False)
    gitlab_mr_iid = Column(Integer, nullable=True)
    gitlab_mr_url = Column(String, nullable=True)
    gitlab_pipeline_id = Column(Integer, nullable=True)
    pipeline_status = Column(Enum(PipelineStatus), nullable=True, default=PipelineStatus.UNKNOWN)
    source_branch = Column(String, nullable=True)
    target_branch = Column(String, nullable=False)
    state = Column(Enum(MRState), nullable=False, default=MRState.OPENED)
    finding_ids = Column(JSONB, nullable=False, default=list)
    image_digest = Column(String, nullable=False)
```

- [ ] **Step 10: Write `backend/app/models/audit_log.py`**

```python
import uuid
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy import DateTime
from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=True)
    metadata_jsonb = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 11: Set up Alembic**

```bash
cd backend
alembic init alembic
```

Replace `backend/alembic/env.py` with:

```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from app.core.config import settings
from app.models.base import Base
from app.models import user, registry, image, scan, finding, merge_request, audit_log  # noqa

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("+asyncpg", ""))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 12: Write `backend/tests/conftest.py`**

```python
import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from testcontainers.postgres import PostgresContainer
from app.models.base import Base


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest_asyncio.fixture(scope="session")
async def db_engine(postgres_container):
    url = postgres_container.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
```

- [ ] **Step 13: Write `backend/tests/test_models.py`**

```python
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_all_tables_created(db):
    result = await db.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    )
    tables = {row[0] for row in result.fetchall()}
    assert "users" in tables
    assert "registries" in tables
    assert "images" in tables
    assert "scans" in tables
    assert "findings" in tables
    assert "merge_requests" in tables
    assert "audit_log" in tables


@pytest.mark.asyncio
async def test_registries_has_envelope_columns(db):
    result = await db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='registries' AND column_name IN ('auth_ciphertext','auth_dek_enc')"
        )
    )
    cols = {row[0] for row in result.fetchall()}
    assert cols == {"auth_ciphertext", "auth_dek_enc"}
```

- [ ] **Step 14: Run tests to verify they pass**

```bash
cd backend && source .venv/bin/activate
pytest tests/test_models.py -v
```

Expected output:
```
PASSED tests/test_models.py::test_all_tables_created
PASSED tests/test_models.py::test_registries_has_envelope_columns
```

- [ ] **Step 15: Generate and apply Alembic migration**

```bash
cd backend
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade  -> <rev>, initial_schema`

- [ ] **Step 16: Commit**

```bash
git add backend/app/core/ backend/app/models/ backend/alembic/ backend/tests/
git commit -m "feat: SQLAlchemy models + Alembic initial migration with envelope-encryption columns"
```

---

## Task 4: CredentialStore — envelope encryption abstraction

**Files:**
- Create: `backend/app/core/credentials.py`
- Create: `backend/tests/test_credentials.py`

- [ ] **Step 1: Write failing test `backend/tests/test_credentials.py`**

```python
import pytest
from cryptography.fernet import Fernet
from app.core.credentials import CredentialStore, LocalKEKProvider


MASTER_KEY = Fernet.generate_key().decode()


def make_store() -> CredentialStore:
    return CredentialStore(LocalKEKProvider(MASTER_KEY))


def test_encrypt_returns_two_byte_blobs():
    store = make_store()
    plaintext = {"username": "user", "password": "s3cr3t"}
    ciphertext, dek_enc = store.encrypt(plaintext)
    assert isinstance(ciphertext, bytes) and len(ciphertext) > 0
    assert isinstance(dek_enc, bytes) and len(dek_enc) > 0


def test_decrypt_roundtrip():
    store = make_store()
    plaintext = {"token": "ghp_abc123", "region": "us-east-1"}
    ciphertext, dek_enc = store.encrypt(plaintext)
    result = store.decrypt(ciphertext, dek_enc)
    assert result == plaintext


def test_each_encrypt_produces_unique_dek():
    store = make_store()
    plaintext = {"username": "user"}
    _, dek1 = store.encrypt(plaintext)
    _, dek2 = store.encrypt(plaintext)
    assert dek1 != dek2


def test_wrong_kek_raises():
    store1 = make_store()
    store2 = CredentialStore(LocalKEKProvider(Fernet.generate_key().decode()))
    ciphertext, dek_enc = store1.encrypt({"x": "y"})
    with pytest.raises(Exception):
        store2.decrypt(ciphertext, dek_enc)


def test_plaintext_not_in_ciphertext():
    store = make_store()
    secret = "super_secret_password_12345"
    ciphertext, _ = store.encrypt({"password": secret})
    assert secret.encode() not in ciphertext
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_credentials.py -v
```

Expected: `ImportError: cannot import name 'CredentialStore'`

- [ ] **Step 3: Write `backend/app/core/credentials.py`**

```python
import json
from cryptography.fernet import Fernet, InvalidToken


class LocalKEKProvider:
    def __init__(self, master_key: str):
        self._fernet = Fernet(master_key.encode() if isinstance(master_key, str) else master_key)

    def encrypt_dek(self, dek: bytes) -> bytes:
        return self._fernet.encrypt(dek)

    def decrypt_dek(self, dek_enc: bytes) -> bytes:
        return self._fernet.decrypt(dek_enc)


class CredentialStore:
    def __init__(self, kek_provider: LocalKEKProvider | None = None):
        if kek_provider is None:
            from app.core.config import settings
            kek_provider = LocalKEKProvider(settings.MASTER_KEY)
        self._kek = kek_provider

    def encrypt(self, plaintext: dict) -> tuple[bytes, bytes]:
        dek = Fernet.generate_key()
        ciphertext = Fernet(dek).encrypt(json.dumps(plaintext).encode())
        dek_enc = self._kek.encrypt_dek(dek)
        return ciphertext, dek_enc

    def decrypt(self, ciphertext: bytes, dek_enc: bytes) -> dict:
        dek = self._kek.decrypt_dek(dek_enc)
        plaintext = Fernet(dek).decrypt(ciphertext)
        return json.loads(plaintext)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_credentials.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/credentials.py backend/tests/test_credentials.py
git commit -m "feat: CredentialStore envelope encryption (DEK per record, MASTER_KEY KEK)"
```

---

## Task 5: FastAPI app + Keycloak JWT middleware

**Files:**
- Create: `backend/app/core/auth.py`
- Create: `backend/app/core/logging.py`
- Create: `backend/app/api/deps.py`
- Create: `backend/app/main.py`
- Create: `backend/Dockerfile`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing test `backend/tests/test_auth.py`**

```python
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from jose import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import time


def make_test_token(sub: str = "user-123", roles: list[str] = None) -> tuple[str, object]:
    """Returns (token, private_key) signed with a fresh RSA key."""
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    payload = {
        "sub": sub,
        "email": "test@example.com",
        "name": "Test User",
        "realm_access": {"roles": roles or ["viewer"]},
        "patchpilot_teams": [],
        "aud": "patchpilot-backend",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token, private_key


def test_protected_endpoint_rejects_no_token(client):
    resp = client.get("/api/me")
    assert resp.status_code == 403


def test_me_endpoint_returns_user_info(client, valid_token_headers):
    resp = client.get("/api/me", headers=valid_token_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert "sub" in data
```

- [ ] **Step 2: Write `backend/app/core/auth.py`**

```python
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings

bearer_scheme = HTTPBearer()


@lru_cache(maxsize=1)
def _get_jwks() -> dict:
    url = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _decode_token(token: str) -> dict:
    jwks = _get_jwks()
    try:
        return jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=settings.KEYCLOAK_CLIENT_ID,
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> dict:
    return _decode_token(credentials.credentials)


CurrentUser = Annotated[dict, Depends(get_current_user)]
```

- [ ] **Step 3: Write `backend/app/core/logging.py`**

```python
import logging
import structlog

_SECRET_FIELDS = {"token", "password", "secret", "key", "dek", "ciphertext", "auth"}


def _redact_secrets(_, __, event_dict: dict) -> dict:
    for field in list(event_dict.keys()):
        if any(s in field.lower() for s in _SECRET_FIELDS):
            event_dict[field] = "[REDACTED]"
    return event_dict


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_secrets,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
    )
```

- [ ] **Step 4: Write `backend/app/api/deps.py`**

```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.auth import get_current_user

DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[dict, Depends(get_current_user)]
```

- [ ] **Step 5: Write `backend/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.logging import configure_logging
from app.core.auth import CurrentUser

configure_logging()

app = FastAPI(title="PatchPilot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/me")
async def me(user: CurrentUser) -> dict:
    return {
        "sub": user["sub"],
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "roles": user.get("realm_access", {}).get("roles", []),
        "teams": user.get("patchpilot_teams", []),
    }


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 6: Write `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN wget -qO /usr/local/bin/trivy \
    https://github.com/aquasecurity/trivy/releases/latest/download/trivy_Linux-64bit.tar.gz \
    && true
# Actual install via apt:
RUN apt-get update && apt-get install -y gpg && \
    wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | gpg --dearmor > /usr/share/keyrings/trivy.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb generic main" > /etc/apt/sources.list.d/trivy.list && \
    apt-get update && apt-get install -y trivy && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

- [ ] **Step 7: Write `backend/Dockerfile.worker`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gpg wget && \
    wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | gpg --dearmor > /usr/share/keyrings/trivy.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb generic main" > /etc/apt/sources.list.d/trivy.list && \
    apt-get update && apt-get install -y trivy && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

CMD ["celery", "-A", "app.core.celery_app.celery_app", "worker", \
     "--pool=prefork", "--concurrency=2", \
     "--loglevel=info", "--max-tasks-per-child=50"]
```

- [ ] **Step 8: Verify FastAPI starts**

```bash
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload
```

Expected: `Application startup complete.` Visit `http://localhost:8000/healthz` → `{"status": "ok"}`

- [ ] **Step 9: Commit**

```bash
git add backend/app/core/auth.py backend/app/core/logging.py \
        backend/app/api/deps.py backend/app/main.py \
        backend/Dockerfile backend/Dockerfile.worker
git commit -m "feat: FastAPI app + Keycloak JWT middleware + structlog"
```

---

## Task 6: Frontend scaffold + Keycloak OIDC wiring

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/auth/AuthProvider.tsx`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "patchpilot-frontend",
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "lint": "eslint src --ext ts,tsx"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.23.1",
    "@react-oidc-context": "^3.1.0",
    "oidc-client-ts": "^3.0.1",
    "@tanstack/react-query": "^5.45.0",
    "axios": "^1.7.2",
    "react-hook-form": "^7.52.0",
    "zod": "^3.23.8",
    "@hookform/resolvers": "^3.6.0",
    "recharts": "^2.12.7",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.3.0",
    "lucide-react": "^0.400.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.3",
    "vite": "^5.3.1",
    "tailwindcss": "^3.4.4",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.39",
    "vitest": "^1.6.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.6",
    "eslint": "^8.57.0",
    "@typescript-eslint/eslint-plugin": "^7.14.1"
  }
}
```

- [ ] **Step 2: Create `frontend/vite.config.ts`**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

- [ ] **Step 3: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create `frontend/tailwind.config.ts`**

```typescript
import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: '#0f172a',
        surface: '#1e293b',
        border: '#334155',
      },
    },
  },
  plugins: [],
} satisfies Config
```

- [ ] **Step 5: Create `frontend/postcss.config.js`**

```javascript
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
}
```

- [ ] **Step 6: Create `frontend/index.html`**

```html
<!doctype html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>PatchPilot</title>
  </head>
  <body class="bg-slate-900 text-slate-100">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Create `frontend/src/auth/AuthProvider.tsx`**

```typescript
import { AuthProvider as OidcAuthProvider } from '@react-oidc-context'
import type { ReactNode } from 'react'

const oidcConfig = {
  authority: `${import.meta.env.VITE_KEYCLOAK_URL}/realms/${import.meta.env.VITE_KEYCLOAK_REALM}`,
  client_id: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
  redirect_uri: window.location.origin,
  post_logout_redirect_uri: window.location.origin,
  scope: 'openid profile email',
  automaticSilentRenew: true,
}

export function AuthProvider({ children }: { children: ReactNode }) {
  return <OidcAuthProvider {...oidcConfig}>{children}</OidcAuthProvider>
}
```

- [ ] **Step 8: Create `frontend/src/lib/api.ts`**

```typescript
import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '',
})

export function setAuthToken(token: string) {
  api.defaults.headers.common['Authorization'] = `Bearer ${token}`
}

export function clearAuthToken() {
  delete api.defaults.headers.common['Authorization']
}
```

- [ ] **Step 9: Create `frontend/src/main.tsx`**

```typescript
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './auth/AuthProvider'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </AuthProvider>
  </StrictMode>,
)
```

- [ ] **Step 10: Create `frontend/src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 11: Create `frontend/src/App.tsx`**

```typescript
import { useAuth } from '@react-oidc-context'
import { useEffect } from 'react'
import { setAuthToken, clearAuthToken } from './lib/api'

export default function App() {
  const auth = useAuth()

  useEffect(() => {
    if (auth.user?.access_token) {
      setAuthToken(auth.user.access_token)
    } else {
      clearAuthToken()
    }
  }, [auth.user])

  if (auth.isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-900">
        <p className="text-slate-400">Loading…</p>
      </div>
    )
  }

  if (!auth.isAuthenticated) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-slate-900 gap-4">
        <h1 className="text-2xl font-bold text-slate-100">PatchPilot</h1>
        <button
          onClick={() => auth.signinRedirect()}
          className="rounded bg-blue-600 px-6 py-2 text-white hover:bg-blue-700"
        >
          Sign in with Keycloak
        </button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 p-8">
      <p className="text-slate-400">Signed in as {auth.user?.profile.email}</p>
      <p className="text-green-400 mt-2">✓ Foundation complete — routing coming in Phase 5</p>
    </div>
  )
}
```

- [ ] **Step 12: Create `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 13: Create `frontend/nginx.conf`**

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

- [ ] **Step 14: Install deps and verify frontend starts**

```bash
cd frontend && npm install && npm run dev
```

Expected: Vite dev server at `http://localhost:5173` shows "Sign in with Keycloak" button.

- [ ] **Step 15: Commit**

```bash
git add frontend/
git commit -m "feat: React 18 + Vite + Keycloak OIDC wiring + Tailwind dark theme"
```

---

**Phase 1 complete.** At this point:
- All 7 Docker Compose services run
- Postgres schema exists with envelope-encryption columns
- `CredentialStore` passes all tests
- FastAPI starts and validates Keycloak JWTs
- Frontend loads and redirects to Keycloak login
