# Architecture Review v2 — PatchPilot Design Spec (2026-06-16, revised)

**Reviewer perspective:** SRE / cloud-infra architect
**Verdict:** The three v1 blockers are resolved correctly. Two new/remaining issues should be fixed before you start Phase 2, one before Phase 4. Everything else is yellow/green. This is now a buildable spec.

---

## Resolved from v1 (verified)

- 🔴→✅ **Trivy model** (§7 / ADR-A): correct now — worker shells out to `trivy image --server`, pulls/decompresses locally, server does matching only, creds never sent to server.
- 🔴→✅ **Concurrency** (ADR-B): prefork `concurrency=2` + KEDA on Redis queue depth. `max_tasks_per_child` now used on the pool it actually applies to.
- 🔴→✅ **Idempotency** (§8): unique partial index `WHERE state='OPENED'` + `ON CONFLICT DO UPDATE`. Race closed in the DB.
- 🟡→✅ **Envelope encryption** (§6): per-record DEK wrapped by KMS-held KEK. Right model.
- 🟡→✅ **Base-image bump** (§8): honestly descoped to OS-package pinning; multi-stage `FROM` parsing called out.
- 🟡→✅ **Loop closure** (§8): manual re-scan banner v1, webhook auto-rescan v2.
- 🟡→✅ **MR author identity**: bot-account guidance + on-behalf-of footer.

---

## 🔴 1. §6 says envelope encryption; §4/§9/§12/§13 still say single-key Fernet — and Phase plan defers envelope to Phase 8

This is the most important remaining issue because it's a **security regression buried in the phasing**, plus a schema rework you'll pay for twice:

- §4: *"Secrets: cryptography.Fernet — AES-128-CBC; key from `FERNET_KEY` env var"*
- §6: per-record DEK + KEK from `MASTER_KEY`, columns `auth_ciphertext` / `auth_dek_enc`
- §9: comments still say *"creds → Fernet-encrypted"*
- §12: ExternalSecret refs `FERNET_KEY`
- §13: Phase 1 *"Fernet secret abstraction"*, Phase 2 builds registry creds, **Phase 8** *"envelope encryption + KMS integration"*

So as written, you store **real registry creds and GitLab `api` tokens under a single static Fernet key from Phase 2 through Phase 7**, then re-architect encryption and re-migrate the credential columns in Phase 8. That means the crown-jewels live under the weak model for the entire build, and the `auth_encrypted`→(`auth_ciphertext`,`auth_dek_enc`) column change is a data migration over already-populated secret rows.

**Fix:** Make §6 the single source of truth. Build the envelope schema (`auth_ciphertext`, `auth_dek_enc`) in the **Phase 1** Alembic migration. Implement the DEK/KEK abstraction in Phase 2 with the **local `MASTER_KEY` KEK fallback** (already in §6) so dev works without KMS; swap the KEK provider to real KMS in Phase 8 — that swap is a config change, not a schema change. Delete the `FERNET_KEY` references in §4/§9/§12 and standardize on `MASTER_KEY`/KEK naming.

## 🔴 2. trivy-server is a single-pod SPOF and bottleneck — and the requirement now makes it real

With concurrency real, 50 pods × 2 = **100 concurrent `trivy --server` clients all POST package lists to one trivy-server pod** for CVE matching. That single pod is both a throughput bottleneck and a SPOF, and §7/§12 keep it at one replica with one PVC.

Also: you can't just bump replicas, because an `RWO` PVC won't mount across multiple pods.

**Fix (before Phase 4, where you'll load-test):**
- Make trivy-server a Deployment with **HPA** (e.g. 2–N replicas).
- Give each replica its **own DB cache** via an `initContainer` running `trivy image --download-db-only` into an `emptyDir`/ephemeral volume — drop the shared `RWO` PVC. (Or use `ReadOnlyMany` if your CSI supports it.)
- The nightly refresh CronJob model still works; each pod refreshes its own cache, or you roll the Deployment to pick up a new DB image.

## 🟡 3. "100 parallel" is now a real and expensive capacity claim — pressure-test the requirement

The corrected model surfaces the true cost: 100 parallel scans = 50 pods × 2 CPU ≈ **100 vCPUs** plus the memory/ephemeral-disk to pull and decompress up to 100 images at once (commonly 0.3–2 GB each → **tens to ~200 GB of concurrent transfer and disk**). That's a large, bursty cluster footprint for what may be infrequent peak load.

Decide deliberately: is 100 *simultaneous* a real SLO, or is "100 in the queue, drained quickly" acceptable? The latter lets you cap maxReplicas far lower and lean on KEDA to burn down the backlog — much cheaper. Set ephemeral-storage requests/limits on the worker pod and a per-scan cleanup (already in the §7 flow — good) or a single oversized pull will evict neighbors.

## 🟡 4. Registry pull rate limits still unaddressed (carried from v1 #7)

100 concurrent pulls will trip **Docker Hub** anonymous/free limits and **ECR** throttling. Nothing handles 429/throttle.

**Fix:** in-cluster pull-through cache / registry mirror, exponential backoff + jitter on throttle responses, and a per-registry concurrency cap (complements the per-user cap you already have).

## 🟡 5. The Celery `task_id` dedup claim is inaccurate

§8: *"Celery deduplication via `task_id` prevents the same task from being enqueued twice."* Celery (Redis broker) does **not** dedup by `task_id` — submitting the same id twice does not reliably prevent a second execution. Your DB unique index is what actually guarantees correctness (good), so this is a wording/safety-belt issue, not a correctness hole.

**Fix:** either drop the claim, or implement real dispatch dedup with `celery-once` / a short-TTL Redis `SET NX` lock keyed on that sha256. Keep the DB index as the source of truth regardless.

## 🟡 6. Auto-MRs can still produce non-building Dockerfiles (carried from v1 #5)

OS-package pinning is still done by locating `RUN apt-get install` lines and injecting `pkg=fixed_version`. Two residual risks: the pinned version may not exist in the image's configured repo snapshot (→ build break), and you parse `FROM`/`RUN` by line-matching rather than a real Dockerfile parser (breaks on `\` continuations, heredocs, `ARG`-built commands).

**Fix:** use a real parser (`dockerfile-parse` or BuildKit's parser), and **track the MR's GitLab pipeline status** — surface pass/fail in the MRs dashboard so a patch that doesn't build is visibly flagged, not silently trusted. An auto-MR that fails CI erodes user trust fast.

## 🟢 7. Smaller items still open

- **Broker durability:** Redis is the Celery broker (StatefulSet). For reliable at-least-once scans set `task_acks_late=True` + a sane visibility timeout, and use managed/replicated Redis in prod. Idempotency (which you now have) is the required partner to at-least-once.
- **Observability still in Phase 8:** pull tracing/structured logs + a dead-letter path for failed scans forward into Phase 4 — that's when you'll be debugging the 100-parallel behavior.
- **Team-scope + soft-delete:** enforce `deleted_at IS NULL AND team_id IN (...)` centrally (base query or Postgres RLS) to avoid a cross-team leak slipping into one endpoint.

---

## Bottom line

Ship-ready in shape. Do #1 (reconcile encryption + move envelope schema to Phase 1) and #2 (trivy-server scaling) before you write Phase 2 / Phase 4 code respectively — both are cheaper now than after data and load exist. #3–#6 are deliberate-decision items; #7 is polish.
