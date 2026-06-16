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
| `trivy-server` | aquasec/trivy:latest | Vuln DB server (HPA 2–N replicas), per-pod DB via initContainer+emptyDir |
| `backend` | ghcr.io/org/patchpilot-backend | FastAPI on :8000 |
| `worker` | ghcr.io/org/patchpilot-worker | Celery prefork (concurrency=2/pod), scaled by KEDA |
| `keycloak` | quay.io/keycloak/keycloak:24 | OIDC identity provider |
| `frontend` | ghcr.io/org/patchpilot-frontend | Nginx serving built Vite app |

---

## 4. Tech Stack

### Backend
- **Python 3.12**, FastAPI, SQLAlchemy 2.0 (async), asyncpg, Alembic
- **Auth:** `python-jose[cryptography]` — validates Keycloak-issued JWT Bearer tokens
- **Secrets:** envelope encryption — per-record DEK (Fernet) wrapped by KEK (`MASTER_KEY` env var in dev, AWS KMS / Azure Key Vault / Vault in prod). Columns: `auth_ciphertext`, `auth_dek_enc`. Built in Phase 1 schema, implemented in Phase 2; KEK provider swapped to KMS in Phase 8 as a config-only change.
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

**trivy-server — HA design (fixes single-pod SPOF and RWO PVC bottleneck):**

- Deployment with **HPA** (minReplicas=2, maxReplicas=N, CPU target 60%).
- Each pod gets its own vuln DB via an **initContainer**: `trivy image --download-db-only --cache-dir /trivy-cache` on pod start, writing into an `emptyDir` volume mounted at `/trivy-cache`. The main `trivy server` container mounts the same `emptyDir`. No shared PVC needed.
- Nightly refresh: a Kubernetes **CronJob** rolls the trivy-server Deployment (`kubectl rollout restart`) — new pods run the initContainer and pick up the latest DB on start.
- Workers round-robin across trivy-server replicas via the Kubernetes Service. No client-side load balancing needed.
- Helm values expose `trivyServer.replicas` (default 2) and `trivyServer.hpa.enabled` (default true).

**Capacity SLO — deliberate decision required:**
100 truly simultaneous scans = 50 pods × 2 CPUs + ephemeral disk for up to 100 concurrent image pulls (typically 0.3–2 GB each = tens to ~200 GB of disk + network). That is a large, bursty footprint for infrequent peaks.
Chosen model: **"100 in-flight concurrently" is the stated SLO.** KEDA maxReplicas=50 enforces it. Worker pod spec must include `ephemeral-storage: requests: 4Gi / limits: 8Gi` and the existing post-scan cleanup (`delete temp image layers`) is mandatory, not optional — a single oversized pull without cleanup evicts neighbors.
If the real need turns out to be "100 in queue, drained fast," lower maxReplicas to 10 (20 parallel) and let KEDA burn the backlog at lower steady-state cost. This is a `values.yaml` knob, not a code change.

**Rate limiting:** Max 5 concurrent scans per user (Redis `INCR` + TTL counter at task dispatch). Org-wide cap enforced by KEDA maxReplicas × concurrency.

**Registry pull rate limits:** 100 concurrent pulls will trip Docker Hub free-tier limits and ECR throttling.
- In-cluster pull-through cache (Harbor or registry mirror) for Docker Hub images — workers pull from the mirror, not the upstream directly.
- All registry adapters implement exponential backoff + jitter on HTTP 429 / throttle responses (max 5 retries, base 2s, cap 60s).
- Per-registry concurrency cap: Redis semaphore keyed on registry ID, max 10 concurrent pulls per registry (configurable per registry type in values). Complements the per-user cap.

---

## 8. MR Engine

### Patch generation

**What Trivy actually gives us:** `fixed_version` for individual OS and language packages. It does **not** provide a "fixed base image tag." Regex-rewriting `FROM` lines also breaks on multi-stage builds and ARG-based tags.

**v1 scope — OS package pinning only (no base image tag bump):**
- **App Dockerfile:** locate the relevant `RUN apt-get install` / `apk add` / `yum install` line; inject `pkg=fixed_version` pins for each fixable package.
- **Language manifests:** if the Dockerfile `COPY`s a requirements.txt / package.json / go.mod that is also in the repo, update the pinned version there too.
- **Base Dockerfile:** same OS-package pinning approach as above.
- `FROM` line is **not auto-modified** in v1. The MR description instead includes a note: _"Base image tag bump not automated — consider upgrading to `<image>:latest-stable` manually."_

**Dockerfile parsing:** use `dockerfile-parse` (Python library, wraps BuildKit's parser) — not regex or line-matching. This handles `\` continuations, heredoc `RUN` blocks, multi-stage builds, and `ARG`-substituted base references correctly. Regex line-matching breaks on all of these and produces non-building Dockerfiles, which erodes user trust faster than no automation.

**Multi-stage Dockerfile handling:** parse all `FROM` lines and their aliases; apply package pins only to the final stage's `RUN` blocks (the stage that produces the runtime image). Comment in MR description lists which stage was patched.

**Only** patches findings where `is_fixable=true` and `fixed_version` is not null. Never rewrites unrelated lines.

**GitLab CI pipeline tracking:** after MR creation, the `merge_requests` table gains a `gitlab_pipeline_id` column (nullable). The `/api/merge-requests/{id}/sync` endpoint fetches the latest pipeline status from GitLab and stores it as `pipeline_status ENUM[PENDING,RUNNING,PASSED,FAILED,UNKNOWN]`. The MRs dashboard surfaces a pipeline badge per MR — a patch that breaks CI is visibly flagged, not silently trusted. A FAILED pipeline triggers a toast notification on the frontend polling update.

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

**Dispatch deduplication (separate from DB idempotency):** Celery with a Redis broker does not deduplicate by `task_id` — submitting the same id twice can still enqueue two executions. The DB unique partial index + `ON CONFLICT` is the authoritative correctness guarantee. For dispatch-time dedup (preventing double-enqueue from a UI double-click), use a short-TTL Redis `SET NX` lock keyed on `sha256(gitlab_project_id + image_digest + target_branch + target_kind)` with a 30s expiry, checked before `apply_async`. The DB constraint remains the backstop regardless.

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
POST   /api/registries                 register (creds → envelope-encrypted: DEK+KEK)
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
- `trivy-server` Deployment + Service + HPA; per-pod DB via initContainer + emptyDir (no shared PVC)
- `redis` StatefulSet (or managed Redis ref)
- External: PostgreSQL and Keycloak referenced via values (not bundled)
- ConfigMap for non-secret env, ExternalSecret CRD refs for `MASTER_KEY` (KEK) — registry creds stored as encrypted columns in Postgres, not as K8s secrets
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
| 1 | Repo scaffold, Postgres schema + Alembic (incl. `auth_ciphertext`/`auth_dek_enc` columns), Keycloak OIDC wired, envelope encryption abstraction (`CredentialStore` with `MASTER_KEY` KEK fallback), Docker Compose running all services |
| 2 | Registry CRUD API + envelope encryption (DEK per record) + per-type credential adapters (ECR/ACR/GAR/DockerHub/Generic) + `/validate` endpoint |
| 3 | Image CRUD API (Dockerfile paths, GitLab repo, service_type) |
| 4 | Celery worker + Trivy server (HA) integration + scan trigger + findings parsing + scan status polling + structlog + OTel traces + DLQ for failed scans |
| 5 | Findings table UI (sort/filter/select) + severity donut + Image Detail screen |
| 6 | Patch generators (dockerfile-parse, OS-package pinning) + python-gitlab MR creation + dispatch Redis SET NX dedup + DB idempotency + GitLab pipeline status tracking + audit log |
| 7 | Raise MR drawer (template inputs, live preview, diff preview) + MRs dashboard |
| 8 | RBAC full enforcement + Postgres RLS, swap KEK to real KMS (config-only), DEK rotation script, OTel full coverage + dashboards, GitLab webhook auto-rescan, registry pull-through cache, GHA CI/CD pipelines, Helm chart + KEDA + HPA for trivy-server |

---

## 14. Operational Decisions

### Celery broker durability
Redis as Celery broker requires `task_acks_late=True` + a sane `visibility_timeout` (set to `CELERY_TASK_TIME_LIMIT + 60s = 1020s`) so a worker crash doesn't drop in-flight scans. Idempotency (DB unique index) is the required partner to at-least-once delivery — a redelivered task must be safe to re-execute. Managed/replicated Redis (Redis Cluster or cloud-managed) in prod; single-node in dev.

### Observability — moved to Phase 4
Structured logging (structlog), OTel traces on scan tasks, and a dead-letter queue for failed scans must land **in Phase 4** alongside the scanner, not Phase 8. This is when 100-parallel behavior will be debugged. Phase 8 adds full coverage (API traces, frontend RUM, dashboards) on top of the Phase 4 foundation.

Phase 4 minimum:
- `structlog` JSON logging on workers with secret redaction filter
- OTel trace per scan task (`scan_id` as root span, Trivy subprocess as child)
- `scans_dlq` Redis list: failed scan task IDs + error text, surfaced in admin UI
- Scan duration histogram metric (Prometheus scrape from worker)

### Team scope + soft-delete enforcement
`deleted_at IS NULL AND team_id = ANY(:team_ids)` must be applied as a **SQLAlchemy base query mixin** (not per-endpoint) to every model that carries `team_id`. PostgreSQL Row-Level Security (RLS) is the Phase 8 defence-in-depth layer on top. A cross-team data leak slipping through one forgotten endpoint is an S1 incident; centralised enforcement is non-negotiable.

---

## 15. Acceptance Criteria

- ECR, ACR, and Docker Hub images register and validate successfully
- Trivy scan of a real image returns real CVEs (no mock data)
- 100 simultaneous scans complete without timeout or worker crash (KEDA scales worker pods, trivy-server HA via HPA + per-pod emptyDir DB)
- Selecting fixable CVEs → Raise MR with user-supplied branch template → GitLab MR opens on correct branch with OS-package pins in the Dockerfile
- Re-raising for the same image digest updates the existing MR, not a new one (enforced by unique partial index + ON CONFLICT)
- No credential value ever appears in an API response body or application log; each credential encrypted with its own DEK
- After an MR merges, the Image Detail screen shows "Re-scan recommended" banner
- A Dockerfile patch produced by the MR engine is parsed via `dockerfile-parse`, builds successfully, and does not rewrite unrelated lines
- A failed GitLab CI pipeline on a PatchPilot MR shows a FAILED badge in the MRs dashboard within one polling cycle
- Helm chart deploys cleanly to a Kubernetes cluster via `helm install`; KEDA ScaledObject autoscales workers; trivy-server HPA maintains ≥2 replicas
- GHA pipeline builds all three images and publishes a Helm release on tag push
