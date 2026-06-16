# PatchPilot — Design Spec
**Date:** 2026-06-16  
**Status:** Approved  
**Author:** Chitender Kumar

---

## 1. Overview

PatchPilot is a web application that closes the loop from "scan a container image" to "open a patched Dockerfile MR on GitLab." Users register container registries and images, trigger Trivy vulnerability scans, review findings, and auto-generate GitLab Merge Requests that patch both base-image and application Dockerfiles.

### Core constraints
- No mock data or APIs — all integrations are real
- 100 container scans in parallel
- Credentials never returned in API responses or written to logs
- Idempotent MR creation (no duplicates)

---

## 2. Monorepo Layout

```
VulnForge/
├── frontend/               # React 18 + TypeScript + Vite
│   ├── src/
│   ├── Dockerfile
│   └── nginx.conf
├── backend/                # FastAPI + Celery (shared codebase)
│   ├── app/
│   │   ├── api/            # FastAPI routers
│   │   ├── core/           # Config, auth, db, encryption
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── services/       # Business logic
│   │   ├── tasks/          # Celery task definitions
│   │   └── workers/        # Registry adapters, Trivy client, GitLab client
│   ├── alembic/            # DB migrations
│   ├── Dockerfile
│   └── Dockerfile.worker
├── infra/
│   ├── docker-compose.yml  # Local dev (all services)
│   ├── docker-compose.override.yml
│   ├── helm/
│   │   └── patchpilot/     # Umbrella Helm chart
│   │       ├── Chart.yaml
│   │       ├── values.yaml
│   │       ├── values-staging.yaml
│   │       ├── values-prod.yaml
│   │       └── templates/
│   └── keycloak/           # Keycloak realm export for local dev
├── .github/
│   └── workflows/
│       ├── ci.yml          # Test + lint on PR
│       ├── build-push.yml  # Build images, push to ghcr.io
│       └── helm-release.yml # Package + release Helm chart
└── docs/
```

---

## 3. Services

| Container | Image | Role |
|---|---|---|
| `postgres` | postgres:16-alpine | Primary database |
| `redis` | redis:7-alpine | Celery broker + result backend |
| `trivy-server` | aquasec/trivy:latest | Vuln DB server, HTTP API on :4954 |
| `backend` | ghcr.io/org/patchpilot-backend | FastAPI on :8000 |
| `worker` | ghcr.io/org/patchpilot-worker | Celery prefork (concurrency=2/pod), scaled by KEDA |
| `keycloak` | quay.io/keycloak/keycloak:24 | OIDC identity provider |
| `frontend` | ghcr.io/org/patchpilot-frontend | Nginx serving built Vite app |

---

## 4. Tech Stack

### Backend
- **Python 3.12**, FastAPI, SQLAlchemy 2.0 (async), asyncpg, Alembic
- **Auth:** `python-jose[cryptography]` — validates Keycloak-issued JWT Bearer tokens
- **Secrets:** `cryptography.Fernet` — AES-128-CBC; key from `FERNET_KEY` env var
- **Jobs:** Celery 5, prefork pool, `--concurrency 2` per pod, Redis broker; KEDA autoscales pods on queue depth (max 50 pods = 100 parallel scans)
- **Scanner:** `trivy` binary (subprocess) with `--server http://trivy-server:4954`; workers pull/decompress images, trivy-server provides DB matching only
- **GitLab:** `python-gitlab 4.x`
- **Registry adapters:** boto3 (ECR), azure-identity + azure-containerregistry (ACR), google-auth (GAR), requests (Docker Hub / generic OCI)

### Frontend
- **React 18**, TypeScript, Vite
- **UI:** Tailwind CSS + shadcn/ui, dark theme (slate-900 base)
- **Data fetching:** TanStack Query v5 (polling for scan/MR status, 3s interval on active jobs)
- **Auth:** `@react-oidc-context` — handles Keycloak redirect, silent token renew
- **Routing:** React Router v6
- **Forms:** React Hook Form + Zod

### Infra / Deploy
- Docker Compose (local dev)
- Helm (Kubernetes deploy)
- GitHub Actions (CI/CD)
- GitHub Container Registry (ghcr.io) for Docker images
- GitHub Releases for Helm chart tarballs + chart index (gh-pages branch as Helm repo)

---

## 5. Authentication

**Flow:** Keycloak authorization code + PKCE → frontend gets `access_token` (JWT) → passes as `Authorization: Bearer <token>` on every API call → FastAPI middleware validates signature against Keycloak JWKS endpoint → extracts `sub`, `email`, `roles`.

**RBAC roles** (defined as Keycloak realm roles, propagated in JWT):
- `admin` — full access, can manage all teams' resources
- `editor` — can register registries/images, trigger scans, raise MRs within their team
- `viewer` — read-only

**Team scoping:** Each registry/image/scan/MR is owned by a `team_id`. Keycloak groups map to teams via a custom JWT claim `patchpilot_teams: [uuid, ...]`. Middleware enforces that users only see records belonging to their teams.

---

## 6. Credential Security

**Envelope encryption** — a single static master key is insufficient for a multi-team app holding registry creds and GitLab tokens for many teams. Compromise of one secret must not expose all.

Model:
- Each stored credential gets its own **DEK** (data encryption key, a fresh Fernet key).
- The DEK is encrypted by a **KEK** (key encryption key) and stored alongside the ciphertext.
- In production: KEK lives in AWS KMS / Azure Key Vault / HashiCorp Vault — never on disk.
- In local dev / v1 fallback: KEK from `MASTER_KEY` env var (32-byte URL-safe base64).

DB columns per credential row:
```
auth_ciphertext  BYTEA   -- Fernet(DEK).encrypt(plaintext_cred_json)
auth_dek_enc     BYTEA   -- KMS.encrypt(DEK)  OR  Fernet(KEK).encrypt(DEK)
```

Decryption path (Celery task only):
1. Fetch `auth_dek_enc` → call KMS `Decrypt` → recover DEK
2. `Fernet(DEK).decrypt(auth_ciphertext)` → plaintext cred dict
3. Use cred, discard — never assign to a variable that outlives the task scope

Rules:
- Pydantic response schemas **never include** credential fields (write-only on input, absent on output).
- Log filter redacts values of fields named `token`, `password`, `secret`, `key`, `dek`, `ciphertext`.
- DEK rotation: re-encrypt per-row DEK with new KEK — no bulk plaintext exposure.

---

## 7. Scanning Architecture (100 Parallel)

### ADR-A: Trivy execution model — shell-out (v1)

`trivy server` holds the vuln DB and does package-to-CVE matching only. It does **not** pull images or accept image references. The worker must:
1. Pull and decompress the image layers (CPU + disk bound)
2. Extract the package list
3. Send the package list to `trivy-server` for DB matching

This means workers **shell out** to the `trivy` binary with `--server` pointing at the DB server. Registry creds are injected as env vars into the subprocess environment — they are never sent to `trivy-server`.

```bash
# Subprocess command on each worker
TRIVY_USERNAME=<decrypted> TRIVY_PASSWORD=<decrypted> \
trivy image \
  --server http://trivy-server:4954 \
  --format json \
  --severity CRITICAL,HIGH,MEDIUM,LOW \
  --scanners vuln \
  --quiet \
  --timeout 15m \
  <registry>/<repo>:<tag>
```

For ECR/ACR/GAR the creds env vars differ (AWS_ACCESS_KEY_ID etc.) — the registry adapter mints a short-lived token and injects the appropriate env for that registry type. The subprocess env is constructed fresh per scan and not logged.

### ADR-B: Concurrency model — prefork + KEDA autoscaling

gevent requires I/O-bound work that yields the GIL. Image pull and layer decompression are CPU-bound native code — gevent cannot parallelize them and `max_tasks_per_child` is a prefork-only knob. gevent at concurrency=100 would serialize CPU work and OOM on 100 images in memory.

**Correct model: bounded prefork workers, horizontal pod autoscaling on queue depth.**

```
Per pod:  Celery prefork, concurrency=2  (2 CPUs → 2 parallel trivy subprocesses)
Fleet:    KEDA ScaledObject watches Redis queue depth
          minReplicas=2, maxReplicas=50 → 50 pods × 2 = 100 parallel scans
```

Worker Celery config:
```python
CELERYD_POOL = "prefork"
CELERYD_CONCURRENCY = 2
CELERY_TASK_SOFT_TIME_LIMIT = 900
CELERY_TASK_TIME_LIMIT = 960
CELERY_WORKER_MAX_TASKS_PER_CHILD = 50   # recycle workers, reclaim disk/mem
```

KEDA `ScaledObject` (Helm template):
```yaml
triggers:
  - type: redis
    metadata:
      address: redis:6379
      listName: celery
      listLength: "2"   # scale up if queue > 2 items per replica
```

**Data flow:**
```
User → POST /api/images/{id}/scans
     → Celery task queued in Redis
     → KEDA scales worker pods on queue depth
     → Worker pod (prefork, 2 concurrent)
          → Decrypt creds via envelope decryption
          → Mint short-lived registry token
          → subprocess: trivy image --server http://trivy-server:4954 ...
               (worker pulls image, sends pkg list to trivy-server for matching)
          → Parse stdout JSON → insert findings rows
          → Update scan.status → SUCCEEDED | FAILED
          → Delete temp image layers from worker disk
```

**trivy-server:** `trivy server --listen 0.0.0.0:4954 --cache-dir /trivy-cache`. Vuln DB on a PVC shared across the single server pod. Nightly refresh via Kubernetes CronJob: `trivy image --download-db-only --cache-dir /trivy-cache`.

**Rate limiting:** Max 5 concurrent scans per user enforced at task dispatch (Redis `INCR` + TTL counter). Org-wide fleet cap is 100 via KEDA maxReplicas × concurrency.

---

## 8. MR Engine

### Patch generation

**What Trivy actually gives us:** `fixed_version` for individual OS and language packages. It does **not** provide a "fixed base image tag." Regex-rewriting `FROM` lines also breaks on multi-stage builds and ARG-based tags.

**v1 scope — OS package pinning only (no base image tag bump):**
- **App Dockerfile:** locate the relevant `RUN apt-get install` / `apk add` / `yum install` line; inject `pkg=fixed_version` pins for each fixable package.
- **Language manifests:** if the Dockerfile `COPY`s a requirements.txt / package.json / go.mod that is also in the repo, update the pinned version there too.
- **Base Dockerfile:** same OS-package pinning approach as above.
- `FROM` line is **not auto-modified** in v1. The MR description instead includes a note: _"Base image tag bump not automated — consider upgrading to `<image>:latest-stable` manually."_

**Multi-stage Dockerfile handling:** parse all `FROM` lines; apply package pins only to the final stage's `RUN` blocks (the stage that produces the runtime image). Comment in MR description lists which stage was patched.

**Only** patches findings where `is_fixable=true` and `fixed_version` is not null. Never rewrites unrelated lines.

Each MR description includes: CVE table (id | package | installed→fixed | severity) + link to PatchPilot scan + list of patched file paths.

### Branch templates
User-defined at MR raise time via the drawer. Template variables:
- `{image}` — image repository slug (slashes replaced with `-`)
- `{tag}` — image tag
- `{date}` — ISO date `YYYY-MM-DD`
- `{version}` — free text field user fills in (e.g., release version)
- `{scan_id}` — short scan UUID prefix

Examples a user might type:
```
hotfix/backend/{version}-sec-{image}   →  hotfix/backend/1.4.2-sec-payments-api
feature/ui/patchpilot-{image}-{date}   →  feature/ui/patchpilot-web-app-2026-06-16
```

### Idempotency

The SELECT-then-INSERT pattern has a TOCTOU race: a double-click or Celery retry between the read and the write creates duplicate MRs.

**Fix: unique partial index + `ON CONFLICT`.**

```sql
CREATE UNIQUE INDEX uix_mr_open
ON merge_requests (gitlab_project_id, image_digest, target_branch, target_kind)
WHERE state = 'OPENED';
```

Insert path (Celery task):
```sql
INSERT INTO merge_requests (...) VALUES (...)
ON CONFLICT ON CONSTRAINT uix_mr_open
DO UPDATE SET
  finding_ids = EXCLUDED.finding_ids,
  updated_at  = now()
RETURNING id, gitlab_mr_iid, source_branch;
```

If the row already exists (conflict), the task recovers the existing `gitlab_mr_iid` and pushes a new commit to the existing source branch + updates the MR description. Atomically correct under concurrent retries.

Celery task idempotency key: `task_id = sha256(gitlab_project_id + image_digest + target_branch + target_kind)` — Celery deduplication via `task_id` prevents the same task from being enqueued twice from the UI.

### MR creation flow (per Dockerfile target)
1. Resolve target branch (user-supplied in drawer)
2. `gl.projects.get(id).branches.create({'branch': source_branch, 'ref': target_branch})`
3. Commit patched file(s) via GitLab Files API
4. `gl.projects.get(id).mergerequests.create({...})` with title, description, labels `['security', 'patchpilot', severity]`
5. Persist `merge_requests` row, mark findings `MR_RAISED`
6. Emit `audit_log` entry

Separate MRs for base vs app Dockerfile by default. "Single MR" mode available when both files are in the same repo (toggle in drawer).

### MR author identity

GitLab MRs are authored by whoever owns the registered GitLab token. In v1 this is the token the user registered for the project — it shows up in GitLab under that user's name. The MR description footer always includes: `_Raised by PatchPilot on behalf of <patchpilot_user_email>._` so audit trail is clear even if the GitLab author is a shared service account.

Recommended practice (documented in UI): register a dedicated `patchpilot-bot` GitLab account's token per project, scoped `api` on that project only.

### Loop closure — re-scan after merge

The vulnerability loop isn't closed until a post-merge scan confirms the CVEs are gone.

**v1: manual re-scan.** After an MR merges, the MR row is updated to `state=MERGED` (via `/api/merge-requests/{id}/sync` or a GitLab webhook). The Image Detail screen shows a "Re-scan recommended" banner when any MR for that image is in `MERGED` state with no subsequent scan. The user clicks "Scan Now" manually.

**v2 (Phase 8 stretch):** `POST /api/webhooks/gitlab` receives GitLab MR merge events, auto-triggers a scan, and resolves the findings if they no longer appear.

---

## 9. API Surface

```
# Auth (handled by Keycloak redirect — no login endpoint in FastAPI)
GET  /api/me                           current user info from JWT

# Registries
POST   /api/registries                 register (creds → Fernet-encrypted)
POST   /api/registries/{id}/validate   test credentials against registry
GET    /api/registries
DELETE /api/registries/{id}

# Images
POST   /api/images
GET    /api/images
GET    /api/images/{id}
PUT    /api/images/{id}
DELETE /api/images/{id}

# Scans
POST   /api/images/{id}/scans          trigger scan → returns {scan_id, status: "queued"}
GET    /api/scans/{id}                 status + summary
GET    /api/scans/{id}/findings        paginated, filter: severity, fixable, status

# Merge Requests
POST   /api/merge-requests             body: {scan_id, finding_ids[], mr_type, service_type,
                                              targets[], source_branch_template,
                                              target_branch, template_vars{}}
GET    /api/merge-requests
GET    /api/merge-requests/{id}
POST   /api/merge-requests/{id}/sync   re-fetch GitLab state

# Audit
GET    /api/audit-log                  admin only, paginated
```

All credential fields are `write_only=True` in Pydantic schemas. All responses validated against strict output schemas.

---

## 10. Frontend Screens

| Screen | Route | Key elements |
|---|---|---|
| Dashboard | `/` | Scan activity summary, recent MRs, severity trend chart |
| Registries | `/registries` | List + "Add Registry" wizard (type-specific cred form + validate button) |
| Images | `/images` | Table: repo, tag, service type, last scan date, scan status badge |
| Image Detail | `/images/:id` | Scan history list, "Scan Now" button, severity donut chart |
| Scan Results | `/scans/:id` | Findings table: CVE, pkg, installed→fixed, severity, fixable chip. Multi-select + sticky "Raise MR" bar |
| Raise MR Drawer | (overlay) | Branch template input, variable fill-ins, live branch preview, Dockerfile diff preview, CVE table, "Create MR(s)" |
| Merge Requests | `/merge-requests` | All MRs: GitLab state badge, link, CVEs addressed, image |
| Settings | `/settings` | Keycloak profile link, team members (admin) |

**Severity colors:** Critical=`red-500`, High=`orange-500`, Medium=`yellow-400`, Low=`blue-400`, Unknown=`slate-400`  
**Scan polling:** TanStack Query `refetchInterval: 3000` while `status === 'queued' | 'running'`

---

## 11. Database Schema

Exact schema from product spec (§4). Key additions:
- `registries.team_id UUID` — team ownership
- `images.team_id UUID`
- `scans.image_digest TEXT` — captured from Trivy report
- All tables: `created_at TIMESTAMPTZ DEFAULT now()`, soft deletes via `deleted_at`

Managed by **Alembic** with auto-generated revision files. Initial migration in Phase 1.

---

## 12. Deployment

### Dockerfiles
- `frontend/Dockerfile` — multi-stage: `node:20-alpine` build → `nginx:alpine` serve
- `backend/Dockerfile` — `python:3.12-slim`, installs deps, runs `uvicorn`
- `backend/Dockerfile.worker` — same base, runs `celery worker`

### Helm Chart (`infra/helm/patchpilot/`)
Single umbrella chart with the following sub-deployments:
- `backend` Deployment + Service + HPA (2–10 replicas)
- `worker` Deployment + KEDA `ScaledObject` (minReplicas=2, maxReplicas=50, trigger: Redis queue depth ≥ 2 items/replica)
- `frontend` Deployment + Service + Ingress
- `trivy-server` Deployment + Service + PVC for DB cache
- `redis` StatefulSet (or managed Redis ref)
- External: PostgreSQL and Keycloak referenced via values (not bundled)
- ConfigMap for non-secret env, ExternalSecret CRD refs for `FERNET_KEY`, registry secrets
- `values.yaml` (defaults), `values-staging.yaml`, `values-prod.yaml`

Helm chart versioned independently from app version. Stored as GitHub Release assets + served via `gh-pages` as a Helm repo (`index.yaml`).

### GitHub Actions Workflows

**`ci.yml`** — triggers on PR:
- Python lint (ruff) + type-check (mypy)
- Frontend lint (ESLint) + type-check (tsc)
- Backend unit tests (pytest)
- Frontend unit tests (vitest)

**`build-push.yml`** — triggers on push to `main` or version tag `v*`:
- Matrix build: `frontend`, `backend`, `worker`
- `docker/build-push-action` → push to `ghcr.io/<org>/patchpilot-<service>:<sha>` and `:latest`
- On tag: also push `:<version>` tag
- Attestation via `sigstore/cosign-action`

**`helm-release.yml`** — triggers on tag `helm/v*`:
- `helm package infra/helm/patchpilot/`
- Upload `.tgz` as GitHub Release asset
- Checkout `gh-pages` branch, run `helm repo index` with `--merge`, push updated `index.yaml`
- Users add the Helm repo: `helm repo add patchpilot https://<org>.github.io/VulnForge`

---

## 13. Build Phases

| Phase | Deliverable |
|---|---|
| 1 | Repo scaffold, Postgres schema + Alembic, Keycloak OIDC wired, Fernet secret abstraction, Docker Compose running all services |
| 2 | Registry CRUD API + Fernet encryption + per-type credential adapters (ECR/ACR/GAR/DockerHub/Generic) + `/validate` endpoint |
| 3 | Image CRUD API (Dockerfile paths, GitLab repo, service_type) |
| 4 | Celery worker + Trivy server integration + scan trigger + findings parsing + scan status polling |
| 5 | Findings table UI (sort/filter/select) + severity donut + Image Detail screen |
| 6 | Patch generators (base + app Dockerfile) + python-gitlab MR creation + idempotency + audit log |
| 7 | Raise MR drawer (template inputs, live preview, diff preview) + MRs dashboard |
| 8 | RBAC enforcement, envelope encryption + KMS integration, DEK rotation script, structured logging + redaction, OTel traces, rate limits, Trivy DB refresh CronJob, GitLab webhook for auto-rescan, GHA CI/CD pipelines, Helm chart + KEDA |

---

## 14. Acceptance Criteria

- ECR, ACR, and Docker Hub images register and validate successfully
- Trivy scan of a real image returns real CVEs (no mock data)
- 100 simultaneous scans complete without timeout or worker crash (KEDA scales worker pods, trivy-server holds DB)
- Selecting fixable CVEs → Raise MR with user-supplied branch template → GitLab MR opens on correct branch with OS-package pins in the Dockerfile
- Re-raising for the same image digest updates the existing MR, not a new one (enforced by unique partial index + ON CONFLICT)
- No credential value ever appears in an API response body or application log; each credential encrypted with its own DEK
- After an MR merges, the Image Detail screen shows "Re-scan recommended" banner
- Helm chart deploys cleanly to a Kubernetes cluster via `helm install`; KEDA ScaledObject autoscales workers
- GHA pipeline builds all three images and publishes a Helm release on tag push
