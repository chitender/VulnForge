# Architecture Review — PatchPilot Design Spec (2026-06-16)

**Reviewer perspective:** SRE / cloud-infra architect
**Subject:** `2026-06-16-patchpilot-design.md`
**Verdict:** Approve the *shape*, block on three issues before Phase 4. The spec is well-organized and the bones are right. But the scanning architecture rests on a factual misunderstanding of Trivy, the concurrency model won't deliver "100 parallel" the way it's written, and the credential-encryption design is under-built for what this app holds.

Findings are severity-ranked. 🔴 = fix before building that phase, 🟡 = decide deliberately, 🟢 = polish.

---

## 🔴 1. The Trivy client/server model in §7 is wrong

The spec says the worker does:

```
POST http://trivy-server:4954/scan  body: { image: "registry/repo:tag", auth: {...} }
```
…and Tech Stack §4 states *"Trivy HTTP client — calls trivy-server REST API, no subprocess."*

**That is not how Trivy client/server mode works.** `trivy server` holds only the **vulnerability database** and performs **matching**. It does **not** pull images and there is no endpoint that takes an image reference + registry creds and scans it for you. In client/server mode the **client** (`trivy image --server <url> <ref>`) pulls the image, extracts OS/language packages locally, and sends the *analyzed artifact* to the server for CVE matching. The server never sees the image or the credentials.

Consequences of building it as written:
- There is no Python "Trivy HTTP client" that does what §7 describes. You will end up **shelling out to the `trivy` binary** (`trivy image --server …`) — i.e. a subprocess — directly contradicting the "no subprocess" decision and the gevent assumptions built on top of it.
- The heavy work (image pull, layer decompress, package extraction) happens **on the worker**, not on trivy-server. Your capacity model must be sized for the worker doing this, not a thin HTTP call.
- Sending registry creds in a POST body to trivy-server is both unnecessary and a security smell — in correct mode, creds never leave the client.

**Recommendation:** Pick the execution model explicitly (see ADR-A below). Either run the trivy client as a subprocess per scan, or embed the Trivy Go library in a sidecar/Go microservice. Keep trivy-server purely for DB matching, HPA it, and treat the *worker* as the resource-heavy component.

---

## 🔴 2. `gevent --concurrency 100` on one worker will not give you 100 real parallel scans

A single Celery worker with `gevent` pool and `concurrency=100` is sized for **IO-bound greenlets that yield on network sockets**. Container scanning is not that workload:

- Image pull + gzip decompress + tar extraction is **CPU-bound native code** that doesn't cooperatively yield to gevent, and is serialized by the GIL. 100 greenlets ≠ 100× throughput; they queue behind CPU.
- 100 concurrent image pulls on one pod means 100 images on local disk simultaneously. At 300 MB–2 GB each, that's tens to hundreds of GB of ephemeral storage and proportional memory/network → **OOMKill or disk-full**, not parallelism.
- `CELERY_WORKER_MAX_TASKS_PER_CHILD = 500` only applies to the **prefork** pool — it's a no-op for gevent. The comment ("prevent gevent leak") signals a copy-pasted config.

**Recommendation:** "100 parallel" is a *fleet* property, not a single-worker setting. Use bounded per-pod concurrency (prefork, 4–8 workers, or gevent with a much lower number) and **scale pods horizontally** via the queue + HPA on queue depth (KEDA on Redis list length is the clean pattern). Bound concurrent image pulls per node and set ephemeral-storage requests/limits. Add a per-scan disk-cleanup step. See ADR-B.

---

## 🔴 3. Idempotency as written has a race that violates your own acceptance criterion

§8 does read-then-write: `SELECT … WHERE … state='OPENED'` → if none, create. Two near-simultaneous "Raise MR" clicks, or a Celery **retry** of a task that already partially succeeded, will both read "none" and both create branches + MRs → duplicates. Your acceptance criterion explicitly forbids this.

**Recommendation:** Enforce it in the database, not in application logic:
- Add a **unique partial index**: `UNIQUE (gitlab_project_id, image_digest, target_branch, target_kind) WHERE state = 'OPENED'`.
- Wrap the create in `INSERT … ON CONFLICT DO NOTHING/UPDATE`, or take a Postgres advisory lock keyed on that tuple.
- Make the Celery task **idempotent under at-least-once delivery** (it will retry): check GitLab for an existing PatchPilot branch/MR before creating, and make commit/branch creation safe to repeat.

---

## 🟡 4. Credential encryption is under-built for the blast radius

This app holds **registry pull creds + GitLab `api` tokens for multiple teams** — a compromise is a supply-chain write foothold. §6 uses a single static `FERNET_KEY` (AES-128-CBC) loaded into app memory.

Problems:
- One static symmetric key = one compromise decrypts **everything**, all teams.
- §6 is internally inconsistent: `auth_ref` ("pointer label") implies an external secret store, but `auth_encrypted` (bytes in DB) implies in-DB encryption. Decide which.
- Key rotation is deferred to Phase 8 — but rotation design constrains the storage schema, so it can't be a bolt-on.

**Recommendation (forward-looking):**
- Prefer **envelope encryption**: a KMS-managed master key (AWS KMS / Azure Key Vault / GCP KMS) encrypts a per-record (or per-team) data key; store only the wrapped DEK + ciphertext. Compromise of the DB without KMS access yields nothing.
- Better still for the highest-value secrets (GitLab tokens): store in **Vault** and persist only a reference — which is what `auth_ref` was hinting at. Then drop `auth_encrypted`.
- For GitLab specifically, move off long-lived PATs toward **short-lived, project-scoped tokens / a bot service account per team**, or OAuth-on-behalf-of-user. Decide the MR **author identity** (bot vs human) for audit/compliance now, not later.

---

## 🟡 5. "Bump base image to recommended fixed tag" is the hardest part of the product and is hand-waved

§8 says: find `FROM image:tag`, replace with "recommended fixed tag." Two real problems:

1. **Trivy doesn't give you a fixed base-image tag.** It reports fixed *package* versions. Computing "which newer base tag clears these N CVEs" is a separate, non-trivial step (base-image lookup + re-scan of candidates). Where does "recommended fixed tag" come from? Undefined.
2. **Regex Dockerfile editing is brittle.** It breaks on multi-stage builds (multiple `FROM`), `ARG`-parameterized tags (`FROM base:${VERSION}`), digest pins, `--platform`, and line continuations. Pinning `pkg=fixed_version` in `apt-get install` also fails when the version isn't in the pinned repo snapshot, and doesn't help when the vulnerable package originates in the **base layer** (it gets reinstalled upstream).

**Recommendation:**
- Treat base-image recommendation as its own component with a defined source (e.g. scan candidate tags and pick the minimal upgrade), or scope v1 to *flag* base-image CVEs and only auto-patch app-layer package pins. Don't promise auto base bumps you can't reliably compute.
- Parse Dockerfiles with a real parser (BuildKit's `dockerfile/parser`, or `dockerfile-parse`) — not regex — and explicitly handle multi-stage and ARG.
- **Validate before you trust:** an auto-MR that doesn't build erodes confidence fast. The MR should trigger the GitLab pipeline, and PatchPilot should track pipeline status before calling anything "fixed."

---

## 🟡 6. The loop doesn't actually close — no re-scan / verification

The design stops at "MR opened." "Closing the loop" requires: MR merged → image rebuilt → **re-scan to confirm the CVEs are gone**. Without it you have no MTTR metric and no proof the patch worked. Acceptance criteria don't verify vulnerability reduction, only that an MR opened.

**Recommendation:** Add a verification stage: on merge webhook, queue a re-scan of the new digest and mark findings `RESOLVED` only when confirmed absent. This is also your best product differentiator.

---

## 🟡 7. Registry pull rate limits at 100× are unaddressed

100 concurrent pulls will hit **Docker Hub** anonymous/free limits (~100–200 pulls/6h) and **ECR** throttling fast. Nothing in the design handles this.

**Recommendation:** Pull-through cache / registry mirror in-cluster, exponential backoff with jitter on 429/throttle, and per-registry concurrency caps. This pairs naturally with the bounded-concurrency model in ADR-B.

---

## 🟡 8. trivy-server and Redis reliability posture is inconsistent

- **trivy-server** is a single Deployment with one PVC for the DB cache. Under the (corrected) matching load it's a bottleneck and SPOF, and an `RWO` PVC won't mount across replicas. Define its scaling story (HPA + per-replica cache, or `ReadOnlyMany`).
- **Redis** is bundled as a StatefulSet while Postgres and Keycloak are externalized. Redis is your Celery broker — losing it loses in-flight jobs. For "reliable, no-duplicate MRs," use `acks_late=True`, a sane visibility timeout, durable result backend, and managed/replicated Redis in prod. Be deliberate about at-least-once + idempotency (which ties back to finding #3).

---

## 🟢 9. Observability is sequenced too late

OTel/structured logging/rate limits all land in **Phase 8**, but you'll be debugging 100-parallel scan behavior and external-API flakiness in Phases 4–7 — blind. Pull tracing, structured logs, a dead-letter queue for failed scans, and basic alerting (queue depth, scan failure rate, trivy-server latency) **forward into Phase 4**.

## 🟢 10. Smaller items

- `/api/registries/{id}/validate` runs a sync registry call in the API process — give it a tight timeout or make it async.
- Soft deletes + team scoping: enforce `deleted_at IS NULL AND team_id IN (...)` centrally (base query / Postgres RLS) or you'll leak across teams in some endpoint eventually.
- In-cluster traffic to trivy-server is plain `http://` — once #1 is fixed, creds won't transit it, but still consider mTLS for defense in depth.

---

## ADR-A: Trivy execution model

**Status:** Proposed · **Date:** 2026-06-16 · **Deciders:** Chitender + platform

**Context:** §7's "POST image+creds to trivy-server REST API, no subprocess" is not a real Trivy capability. The client must pull+analyze; the server only matches.

| Option | Complexity | Perf at 100× | Familiarity | Notes |
|---|---|---|---|---|
| **A1. Worker shells out to `trivy image --server`** | Low | Medium | High (Python) | Pragmatic. Subprocess per scan; worker does the heavy pull/extract. Bound concurrency, manage temp disk. Recommended for v1. |
| **A2. Dedicated Go scan-service using Trivy library** | High | High | Low (adds Go) | Clean API, best control, no subprocess fragility. Heavier to build/operate. |
| **A3. Keep "server scans image" as written** | — | — | — | **Not viable** — capability doesn't exist. Reject. |

**Recommendation:** **A1** for v1 (accept the subprocess; it's the supported path), with A2 as a later optimization if scan volume justifies it. Update §4 to drop "no subprocess."

## ADR-B: Concurrency & scaling model

**Status:** Proposed · **Date:** 2026-06-16 · **Deciders:** Chitender + platform

**Context:** "100 parallel scans" is a CPU/IO/disk-heavy fleet requirement, not a single-worker pool setting.

| Option | Complexity | Scalability | Notes |
|---|---|---|---|
| **B1. Single worker, gevent=100** | Low | **Poor** | GIL/CPU-bound serialization, disk/OOM risk. Reject as the parallelism mechanism. |
| **B2. Bounded per-pod concurrency + HPA on CPU** | Medium | Good | Works; CPU isn't the cleanest scale signal for queue-driven bursty work. |
| **B3. Bounded per-pod concurrency + KEDA autoscale on Redis queue depth** | Medium | **Best** | Scales pods to backlog, drains to zero when idle. Recommended. Cap pulls/node, set ephemeral-storage limits, clean up per scan. |

**Recommendation:** **B3.** Treat "100 parallel" as fleet capacity (e.g. ~8 concurrent scans/pod × replicas), not `concurrency=100` on one box.

---

## What's already good (keep)

- Clean monorepo split, shared backend/worker codebase, Alembic-managed schema.
- Write-only Pydantic credential fields + strict output schemas + log-redaction filter.
- Digest-based idempotency *intent* (just needs DB enforcement).
- Sensible auth model (Keycloak OIDC + realm-role RBAC + team scoping via JWT claim).
- Real-integrations-only discipline and a coherent phased plan.
- ExternalSecrets for the encryption key, HPA on backend.

## Suggested spec edits

1. Rewrite §7 per ADR-A (client pulls/analyzes; server matches; subprocess acknowledged).
2. Replace `concurrency=100` narrative with the fleet/KEDA model (ADR-B); fix the misleading `max_tasks_per_child` line.
3. Add the unique partial index + `ON CONFLICT` to §8 and §11; make the MR task retry-safe.
4. Upgrade §6 to envelope encryption (KMS) or Vault-by-reference; resolve `auth_ref` vs `auth_encrypted`; move rotation design out of Phase 8.
5. Scope base-image auto-bump honestly in §8; use a real Dockerfile parser; add MR pipeline-status tracking.
6. Add a merge→rebuild→re-scan verification stage and a corresponding acceptance criterion.
7. Add registry rate-limit handling (mirror + backoff) and pull caps.
8. Pull observability + DLQ forward into Phase 4.
