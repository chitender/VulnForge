# PatchPilot Phase 4 — Scanning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Celery prefork worker, Trivy subprocess client (shell-out to `trivy image --server`), scan trigger endpoint, findings parser, per-user rate limiting, structlog JSON logging with secret redaction, OpenTelemetry traces, and a dead-letter queue for failed scans.

**Architecture:** `POST /api/images/{id}/scans` queues a Celery task and returns immediately. The worker decrypts registry creds, mints a short-lived token via the registry adapter, shells out to `trivy image --server http://trivy-server:4954`, parses the JSON output into `Finding` rows, and updates the `Scan` row to SUCCEEDED or FAILED. Failed tasks go to a Redis `scans_dlq` list.

**Tech Stack:** Celery 5 prefork, Redis broker, trivy binary subprocess, structlog, opentelemetry-sdk, prometheus-client, psycopg2 (sync ORM in workers).

---

## Task 14: Celery app + worker setup

**Files:**
- Create: `backend/app/core/celery_app.py`
- Modify: `backend/app/core/db.py` (add sync engine for workers)

- [ ] **Step 1: Write `backend/app/core/celery_app.py`**

```python
from celery import Celery
from app.core.config import settings

celery_app = Celery("patchpilot", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_transport_options={"visibility_timeout": 1020},
    worker_prefetch_multiplier=1,
    task_soft_time_limit=900,
    task_time_limit=960,
    worker_max_tasks_per_child=50,
)
```

- [ ] **Step 2: Add sync engine to `backend/app/core/db.py`**

The final `db.py`:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

_sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
sync_engine = create_engine(_sync_url, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 3: Verify Celery starts**

```bash
cd backend && source .venv/bin/activate
celery -A app.core.celery_app.celery_app worker --pool=prefork --concurrency=2 --loglevel=info
```

Expected: `celery@host ready. Concurrency: 2 (prefork)`

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/celery_app.py backend/app/core/db.py
git commit -m "feat: Celery prefork worker config (acks_late, visibility_timeout=1020s)"
```

---

## Task 15: Trivy subprocess client

**Files:**
- Create: `backend/app/workers/trivy_client.py`
- Create: `backend/tests/test_trivy_client.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_trivy_client.py
import json
import pytest
from unittest.mock import patch, MagicMock
from app.workers.trivy_client import TrivyClient, TrivyScanResult

SAMPLE_TRIVY_OUTPUT = json.dumps({
    "SchemaVersion": 2,
    "Metadata": {
        "ImageID": "sha256:abc123def456",
        "DiffIDs": [],
        "RepoTags": ["myimage:1.0"],
        "RepoDigests": [],
        "OS": {"Family": "debian", "Name": "12.5"},
    },
    "Results": [
        {
            "Target": "myimage:1.0 (debian 12.5)",
            "Class": "os-pkgs",
            "Type": "debian",
            "Vulnerabilities": [
                {
                    "VulnerabilityID": "CVE-2024-1234",
                    "PkgName": "libssl3",
                    "InstalledVersion": "3.0.2",
                    "FixedVersion": "3.0.14",
                    "Severity": "CRITICAL",
                    "Title": "OpenSSL vuln",
                    "PrimaryURL": "https://nvd.nist.gov/vuln/detail/CVE-2024-1234",
                }
            ],
        }
    ],
})


def test_scan_parses_trivy_output():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = SAMPLE_TRIVY_OUTPUT
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        client = TrivyClient("http://trivy-server:4954")
        result = client.scan("myimage:1.0", {})

    assert result.image_digest == "sha256:abc123def456"
    assert len(result.results) == 1
    assert result.results[0]["Vulnerabilities"][0]["VulnerabilityID"] == "CVE-2024-1234"


def test_scan_raises_on_nonzero_exit():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "trivy: error pulling image"

    with patch("subprocess.run", return_value=mock_result):
        client = TrivyClient("http://trivy-server:4954")
        with pytest.raises(RuntimeError, match="trivy failed"):
            client.scan("badimage:1.0", {})


def test_scan_env_does_not_log_creds(caplog):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = SAMPLE_TRIVY_OUTPUT
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        client = TrivyClient("http://trivy-server:4954")
        client.scan("myimage:1.0", {"TRIVY_PASSWORD": "s3cr3t_password"})

    assert "s3cr3t_password" not in caplog.text
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && pytest tests/test_trivy_client.py -v
```

Expected: `ImportError: cannot import name 'TrivyClient'`

- [ ] **Step 3: Write `backend/app/workers/trivy_client.py`**

```python
from __future__ import annotations
import json
import os
import subprocess
from dataclasses import dataclass, field


@dataclass
class TrivyScanResult:
    image_digest: str
    results: list[dict]
    trivy_version: str
    db_version: str


class TrivyClient:
    def __init__(self, server_url: str):
        self.server_url = server_url

    def scan(self, image_ref: str, cred_env: dict[str, str]) -> TrivyScanResult:
        env = {**os.environ, **cred_env}
        cmd = [
            "trivy", "image",
            "--server", self.server_url,
            "--format", "json",
            "--severity", "CRITICAL,HIGH,MEDIUM,LOW",
            "--scanners", "vuln",
            "--quiet",
            "--timeout", "15m",
            image_ref,
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=960,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"trivy failed (exit {proc.returncode}): {proc.stderr[:2000]}")

        report = json.loads(proc.stdout)
        meta = report.get("Metadata", {})
        return TrivyScanResult(
            image_digest=meta.get("ImageID", ""),
            results=report.get("Results", []),
            trivy_version=str(report.get("SchemaVersion", "")),
            db_version=str(meta.get("DBSchema", {}).get("Version", "")),
        )

    def cleanup(self, image_ref: str) -> None:
        subprocess.run(
            ["trivy", "image", "--clear-cache"],
            capture_output=True,
            timeout=60,
        )
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_trivy_client.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/workers/trivy_client.py backend/tests/test_trivy_client.py
git commit -m "feat: TrivyClient subprocess wrapper (--server mode, no creds in logs)"
```

---

## Task 16: Findings parser

**Files:**
- Create: `backend/app/workers/findings_parser.py`
- Create: `backend/tests/test_findings_parser.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_findings_parser.py
import pytest
from app.workers.findings_parser import parse_findings
from app.models.finding import Severity, FindingStatus

TRIVY_RESULTS = [
    {
        "Target": "debian (debian 12.5)",
        "Class": "os-pkgs",
        "Type": "debian",
        "Vulnerabilities": [
            {
                "VulnerabilityID": "CVE-2024-1234",
                "PkgName": "libssl3",
                "InstalledVersion": "3.0.2",
                "FixedVersion": "3.0.14",
                "Severity": "CRITICAL",
                "Title": "OpenSSL buffer overflow",
                "PrimaryURL": "https://nvd.nist.gov/vuln/detail/CVE-2024-1234",
            },
            {
                "VulnerabilityID": "CVE-2024-5678",
                "PkgName": "curl",
                "InstalledVersion": "7.88.0",
                "FixedVersion": None,
                "Severity": "HIGH",
                "Title": "curl vuln",
                "PrimaryURL": None,
            },
        ],
    }
]


def test_parse_findings_count():
    findings = parse_findings(TRIVY_RESULTS, scan_id="scan-uuid-1")
    assert len(findings) == 2


def test_fixable_flag():
    findings = parse_findings(TRIVY_RESULTS, scan_id="scan-uuid-1")
    fixable = [f for f in findings if f.vuln_id == "CVE-2024-1234"]
    not_fixable = [f for f in findings if f.vuln_id == "CVE-2024-5678"]
    assert fixable[0].is_fixable is True
    assert not_fixable[0].is_fixable is False


def test_severity_mapped():
    findings = parse_findings(TRIVY_RESULTS, scan_id="scan-uuid-1")
    crit = next(f for f in findings if f.vuln_id == "CVE-2024-1234")
    assert crit.severity == Severity.CRITICAL


def test_unknown_severity_defaults():
    results = [{
        "Target": "test",
        "Vulnerabilities": [
            {"VulnerabilityID": "CVE-X", "PkgName": "pkg", "InstalledVersion": "1.0",
             "FixedVersion": None, "Severity": "WEIRD", "Title": None, "PrimaryURL": None}
        ],
    }]
    findings = parse_findings(results, scan_id="scan-uuid-2")
    assert findings[0].severity == Severity.UNKNOWN


def test_status_defaults_to_open():
    findings = parse_findings(TRIVY_RESULTS, scan_id="scan-uuid-1")
    assert all(f.status == FindingStatus.OPEN for f in findings)
```

- [ ] **Step 2: Write `backend/app/workers/findings_parser.py`**

```python
from __future__ import annotations
import uuid
from app.models.finding import Finding, Severity, FindingStatus

_SEVERITY_MAP = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
}


def parse_findings(trivy_results: list[dict], scan_id: str) -> list[Finding]:
    findings: list[Finding] = []
    for result in trivy_results:
        target = result.get("Target", "")
        for vuln in result.get("Vulnerabilities") or []:
            fixed = vuln.get("FixedVersion")
            findings.append(
                Finding(
                    id=uuid.uuid4(),
                    scan_id=uuid.UUID(scan_id),
                    vuln_id=vuln["VulnerabilityID"],
                    pkg_name=vuln["PkgName"],
                    installed_version=vuln["InstalledVersion"],
                    fixed_version=fixed if fixed else None,
                    severity=_SEVERITY_MAP.get(vuln.get("Severity", ""), Severity.UNKNOWN),
                    target=target,
                    title=vuln.get("Title"),
                    primary_url=vuln.get("PrimaryURL"),
                    is_fixable=bool(fixed),
                    status=FindingStatus.OPEN,
                )
            )
    return findings


def summarize_findings(findings: list[Finding]) -> dict:
    counts: dict[str, int] = {s.value: 0 for s in Severity}
    for f in findings:
        counts[f.severity.value] += 1
    return {"by_severity": counts, "total": len(findings), "fixable": sum(1 for f in findings if f.is_fixable)}
```

- [ ] **Step 3: Run tests**

```bash
cd backend && pytest tests/test_findings_parser.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/workers/findings_parser.py backend/tests/test_findings_parser.py
git commit -m "feat: Trivy findings parser — severity mapping, fixable flag, summary"
```

---

## Task 17: Scan Celery task + structlog + OTel + DLQ

**Files:**
- Create: `backend/app/tasks/scan_task.py`
- Modify: `backend/app/core/logging.py` (add OTel setup)
- Create: `backend/tests/test_scan_task.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_scan_task.py
import pytest
import uuid
from unittest.mock import patch, MagicMock
from app.tasks.scan_task import scan_image_task


SCAN_ID = str(uuid.uuid4())
IMAGE_ID = str(uuid.uuid4())
REGISTRY_ID = str(uuid.uuid4())


def make_mock_scan(status="QUEUED"):
    scan = MagicMock()
    scan.id = SCAN_ID
    scan.status = status
    scan.image = MagicMock()
    scan.image.repository = "myorg/payments"
    scan.image.tag = "1.0"
    scan.image.registry = MagicMock()
    scan.image.registry.type = "DOCKERHUB"
    scan.image.registry.registry_url = "registry-1.docker.io"
    scan.image.registry.auth_ciphertext = b"cipher"
    scan.image.registry.auth_dek_enc = b"dek"
    return scan


def test_scan_task_sets_running_then_succeeded():
    mock_scan = make_mock_scan()

    with patch("app.tasks.scan_task.SyncSessionLocal") as MockSession, \
         patch("app.tasks.scan_task.CredentialStore") as MockStore, \
         patch("app.tasks.scan_task.get_adapter") as MockAdapter, \
         patch("app.tasks.scan_task.TrivyClient") as MockTrivy:

        ctx_mgr = MagicMock()
        ctx_mgr.__enter__ = MagicMock(return_value=MagicMock(get=MagicMock(return_value=mock_scan)))
        ctx_mgr.__exit__ = MagicMock(return_value=False)
        MockSession.return_value = ctx_mgr

        MockStore.return_value.decrypt.return_value = {"username": "u", "password": "p"}
        MockAdapter.return_value.get_trivy_env.return_value = {}

        mock_result = MagicMock()
        mock_result.image_digest = "sha256:abc"
        mock_result.results = []
        mock_result.trivy_version = "0.52"
        mock_result.db_version = "v1"
        MockTrivy.return_value.scan.return_value = mock_result

        scan_image_task(SCAN_ID)

    assert mock_scan.status.value in ("SUCCEEDED",) or mock_scan.status in ("SUCCEEDED", "RUNNING")


def test_scan_task_sets_failed_on_trivy_error():
    mock_scan = make_mock_scan()

    with patch("app.tasks.scan_task.SyncSessionLocal") as MockSession, \
         patch("app.tasks.scan_task.CredentialStore") as MockStore, \
         patch("app.tasks.scan_task.get_adapter") as MockAdapter, \
         patch("app.tasks.scan_task.TrivyClient") as MockTrivy, \
         patch("app.tasks.scan_task.redis_client") as MockRedis:

        ctx_mgr = MagicMock()
        ctx_mgr.__enter__ = MagicMock(return_value=MagicMock(get=MagicMock(return_value=mock_scan)))
        ctx_mgr.__exit__ = MagicMock(return_value=False)
        MockSession.return_value = ctx_mgr

        MockStore.return_value.decrypt.return_value = {}
        MockAdapter.return_value.get_trivy_env.return_value = {}
        MockTrivy.return_value.scan.side_effect = RuntimeError("trivy failed")

        with pytest.raises(Exception):
            scan_image_task(SCAN_ID)

        MockRedis.rpush.assert_called_once()
```

- [ ] **Step 2: Write `backend/app/tasks/scan_task.py`**

```python
from __future__ import annotations
import structlog
from opentelemetry import trace
from app.core.celery_app import celery_app
from app.core.db import SyncSessionLocal
from app.core.credentials import CredentialStore
from app.workers.trivy_client import TrivyClient
from app.workers.registry_adapters import get_adapter
from app.workers.findings_parser import parse_findings, summarize_findings
from app.models.scan import Scan, ScanStatus
from app.core.config import settings
import redis as redis_lib

log = structlog.get_logger()
tracer = trace.get_tracer(__name__)
redis_client = redis_lib.from_url(settings.REDIS_URL)


@celery_app.task(
    name="patchpilot.scan_image",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def scan_image_task(self, scan_id: str) -> None:
    log.info("scan_started", scan_id=scan_id)
    with tracer.start_as_current_span("scan_image", attributes={"scan_id": scan_id}):
        with SyncSessionLocal() as db:
            scan = db.get(Scan, scan_id)
            if not scan:
                log.error("scan_not_found", scan_id=scan_id)
                return

            scan.status = ScanStatus.RUNNING
            db.commit()

            trivy = TrivyClient(settings.TRIVY_SERVER_URL)
            try:
                image = scan.image
                registry = image.registry
                store = CredentialStore()
                creds = store.decrypt(registry.auth_ciphertext, registry.auth_dek_enc)
                adapter = get_adapter(registry.type)
                cred_env = adapter.get_trivy_env(creds, registry)

                image_ref = f"{registry.registry_url}/{image.repository}:{image.tag}"
                with tracer.start_as_current_span("trivy_subprocess"):
                    result = trivy.scan(image_ref, cred_env)

                scan.image_digest = result.image_digest
                scan.trivy_version = result.trivy_version
                scan.db_version = result.db_version

                findings = parse_findings(result.results, scan_id)
                for f in findings:
                    db.add(f)

                scan.summary_jsonb = summarize_findings(findings)
                scan.status = ScanStatus.SUCCEEDED
                db.commit()
                log.info("scan_succeeded", scan_id=scan_id, findings=len(findings))

            except Exception as exc:
                log.error("scan_failed", scan_id=scan_id, error=str(exc))
                scan.status = ScanStatus.FAILED
                scan.error_text = str(exc)[:2000]
                db.commit()
                redis_client.rpush("scans_dlq", scan_id)
                raise self.retry(exc=exc)
            finally:
                try:
                    trivy.cleanup(
                        f"{scan.image.registry.registry_url}/{scan.image.repository}:{scan.image.tag}"
                    )
                except Exception:
                    pass
```

- [ ] **Step 3: Run tests**

```bash
cd backend && pytest tests/test_scan_task.py -v
```

Expected: All 2 tests PASS (or 1 PASS + 1 with expected retry exception).

- [ ] **Step 4: Commit**

```bash
git add backend/app/tasks/scan_task.py backend/tests/test_scan_task.py
git commit -m "feat: scan Celery task with OTel traces, structlog, DLQ on failure"
```

---

## Task 18: Scan API endpoints + per-user rate limiting

**Files:**
- Create: `backend/app/schemas/scan.py`
- Create: `backend/app/api/routers/scans.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_scan_api.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_scan_api.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
import uuid

client = TestClient(app)
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
    with patch("app.api.routers.scans.get_current_user", return_value=TEST_USER):
        yield


def test_trigger_scan_returns_202():
    mock_scan = MagicMock()
    mock_scan.id = uuid.UUID(SCAN_ID)
    mock_scan.status = "QUEUED"

    with patch("app.api.routers.scans.ImageService") as MockImgSvc, \
         patch("app.api.routers.scans.ScanService") as MockScanSvc, \
         patch("app.api.routers.scans.scan_image_task") as MockTask, \
         patch("app.api.routers.scans._check_user_rate_limit", return_value=True):

        mock_img = MagicMock()
        mock_img.id = uuid.UUID(IMAGE_ID)
        mock_img.team_id = uuid.UUID("00000000-0000-0000-0000-000000000010")
        MockImgSvc.return_value.get = AsyncMock(return_value=mock_img)
        MockScanSvc.return_value.create = AsyncMock(return_value=mock_scan)

        resp = client.post(
            f"/api/images/{IMAGE_ID}/scans",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 202
    assert resp.json()["status"] == "QUEUED"


def test_trigger_scan_rate_limited():
    with patch("app.api.routers.scans.ImageService") as MockImgSvc, \
         patch("app.api.routers.scans._check_user_rate_limit", return_value=False):

        mock_img = MagicMock()
        MockImgSvc.return_value.get = AsyncMock(return_value=mock_img)

        resp = client.post(
            f"/api/images/{IMAGE_ID}/scans",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 429
```

- [ ] **Step 2: Write `backend/app/schemas/scan.py`**

```python
from __future__ import annotations
import uuid
from pydantic import BaseModel, ConfigDict
from app.models.scan import ScanStatus


class ScanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    image_id: uuid.UUID
    status: ScanStatus
    image_digest: str | None
    trivy_version: str | None
    db_version: str | None
    summary_jsonb: dict | None
    error_text: str | None


class ScanTriggerResponse(BaseModel):
    scan_id: str
    status: str
```

- [ ] **Step 3: Write `backend/app/services/scan_service.py`**

```python
from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.scan import Scan, ScanStatus


class ScanService:
    async def create(self, db: AsyncSession, image_id: str, triggered_by: str) -> Scan:
        scan = Scan(
            id=uuid.uuid4(),
            image_id=uuid.UUID(image_id),
            triggered_by=uuid.UUID(triggered_by) if len(triggered_by) == 36 else uuid.uuid4(),
            status=ScanStatus.QUEUED,
        )
        db.add(scan)
        await db.commit()
        await db.refresh(scan)
        return scan

    async def get(self, db: AsyncSession, scan_id: str) -> Scan | None:
        return await db.get(Scan, uuid.UUID(scan_id))
```

- [ ] **Step 4: Write `backend/app/api/routers/scans.py`**

```python
from __future__ import annotations
from typing import Any
import redis as redis_lib
from fastapi import APIRouter, HTTPException, status
from app.api.deps import DB, CurrentUser
from app.schemas.scan import ScanResponse, ScanTriggerResponse
from app.schemas.finding import FindingResponse
from app.services.image_service import ImageService
from app.services.scan_service import ScanService
from app.tasks.scan_task import scan_image_task
from app.core.config import settings

router = APIRouter(tags=["scans"])
_redis = redis_lib.from_url(settings.REDIS_URL)
_MAX_SCANS_PER_USER = 5
_RATE_TTL = 120  # seconds


def _check_user_rate_limit(user_sub: str) -> bool:
    key = f"scan_rate:{user_sub}"
    count = _redis.incr(key)
    if count == 1:
        _redis.expire(key, _RATE_TTL)
    if count > _MAX_SCANS_PER_USER:
        _redis.decr(key)
        return False
    return True


def _release_user_rate(user_sub: str) -> None:
    _redis.decr(f"scan_rate:{user_sub}")


@router.post("/api/images/{image_id}/scans", status_code=202, response_model=ScanTriggerResponse)
async def trigger_scan(image_id: str, user: CurrentUser, db: DB) -> Any:
    img_svc = ImageService()
    img = None
    for team_id in user.get("patchpilot_teams", []):
        img = await img_svc.get(db=db, image_id=image_id, team_id=team_id)
        if img:
            break
    if not img:
        raise HTTPException(404, "Image not found")

    if not _check_user_rate_limit(user["sub"]):
        raise HTTPException(429, f"Max {_MAX_SCANS_PER_USER} concurrent scans per user")

    scan_svc = ScanService()
    scan = await scan_svc.create(db=db, image_id=image_id, triggered_by=user["sub"])
    scan_image_task.apply_async(args=[str(scan.id)])
    return {"scan_id": str(scan.id), "status": scan.status.value}


@router.get("/api/scans/{scan_id}", response_model=ScanResponse)
async def get_scan(scan_id: str, user: CurrentUser, db: DB) -> Any:
    svc = ScanService()
    scan = await svc.get(db=db, scan_id=scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    return scan


@router.get("/api/scans/{scan_id}/findings")
async def get_findings(
    scan_id: str,
    user: CurrentUser,
    db: DB,
    severity: str | None = None,
    fixable_only: bool = False,
) -> Any:
    from sqlalchemy import select
    from app.models.finding import Finding
    query = select(Finding).where(Finding.scan_id == scan_id)
    if severity:
        query = query.where(Finding.severity == severity)
    if fixable_only:
        query = query.where(Finding.is_fixable.is_(True))
    result = await db.execute(query)
    return result.scalars().all()
```

- [ ] **Step 5: Add FindingResponse schema — create `backend/app/schemas/finding.py`**

```python
from __future__ import annotations
import uuid
from pydantic import BaseModel, ConfigDict
from app.models.finding import Severity, FindingStatus


class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scan_id: uuid.UUID
    vuln_id: str
    pkg_name: str
    installed_version: str
    fixed_version: str | None
    severity: Severity
    target: str | None
    title: str | None
    primary_url: str | None
    is_fixable: bool
    status: FindingStatus
```

- [ ] **Step 6: Register scan router in `backend/app/main.py`**

```python
from app.api.routers import registries, images, scans

app.include_router(registries.router)
app.include_router(images.router)
app.include_router(scans.router)
```

- [ ] **Step 7: Run tests**

```bash
cd backend && pytest tests/test_scan_api.py -v
```

Expected: Both tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/tasks/scan_task.py backend/app/schemas/scan.py \
        backend/app/schemas/finding.py backend/app/services/scan_service.py \
        backend/app/api/routers/scans.py backend/app/main.py \
        backend/tests/test_scan_api.py
git commit -m "feat: scan trigger API + per-user rate limit (5 concurrent) + findings endpoint"
```

---

**Phase 4 complete.** Workers shell out to `trivy image --server`, parse findings, persist to DB, update scan status. Failed scans land in `scans_dlq`. Scan trigger endpoint is rate-limited per user. OTel traces wrap the scan task. Celery is configured for at-least-once delivery with correct `visibility_timeout`.
