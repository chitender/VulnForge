"""MR creation Celery task.

Idempotency layers:
1. dispatch_mr_task(): Redis SET NX lock (30s) prevents double-enqueue from UI double-click.
2. create_mr_task():  DB unique partial index + INSERT ... ON CONFLICT handles Celery retries.
"""
from __future__ import annotations

import hashlib
import uuid as _uuid

import redis as redis_lib
import structlog
from opentelemetry import trace

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.db import SyncSessionLocal
from app.models.finding import Finding, FindingStatus
from app.models.merge_request import MRState, MergeRequest, PipelineStatus
from app.models.scan import Scan
from app.models.image import Image
from app.workers.branch_resolver import resolve_branch
from app.workers.gitlab_client import GitLabClient
from app.workers.patch_generator import PatchGenerator

log = structlog.get_logger()
tracer = trace.get_tracer(__name__)
_redis = redis_lib.from_url(settings.REDIS_URL)

_DISPATCH_LOCK_TTL = 30  # seconds


def _dedup_key(
    gitlab_project_id: str,
    image_digest: str,
    target_branch: str,
    target_kind: str,
) -> str:
    raw = f"{gitlab_project_id}:{image_digest}:{target_branch}:{target_kind}"
    return f"mr_dispatch:{hashlib.sha256(raw.encode()).hexdigest()}"


def dispatch_mr_task(
    *,
    scan_id: str,
    finding_ids: list[str],
    mr_type: str,
    target_kind: str,
    source_branch_template: str,
    target_branch: str,
    template_vars: dict,
    gitlab_project_id: str,
    gitlab_token: str,
    image_digest: str,
) -> bool:
    """Queue the MR creation task with dispatch-time deduplication.

    Returns True if task was enqueued, False if a duplicate was detected.
    """
    lock_key = _dedup_key(gitlab_project_id, image_digest, target_branch, target_kind)
    acquired = _redis.set(lock_key, "1", nx=True, ex=_DISPATCH_LOCK_TTL)
    if not acquired:
        log.info("mr_dispatch_skipped_duplicate", lock_key=lock_key)
        return False

    create_mr_task.apply_async(
        args=[
            scan_id, finding_ids, mr_type, target_kind,
            source_branch_template, target_branch, template_vars,
            gitlab_project_id, gitlab_token, image_digest,
        ]
    )
    return True


@celery_app.task(
    name="patchpilot.create_mr",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def create_mr_task(
    self,
    scan_id: str,
    finding_ids: list[str],
    mr_type: str,
    target_kind: str,
    source_branch_template: str,
    target_branch: str,
    template_vars: dict,
    gitlab_project_id: str,
    gitlab_token: str,
    image_digest: str,
) -> None:
    with tracer.start_as_current_span("create_mr", attributes={"scan_id": scan_id}):
        with SyncSessionLocal() as db:
            try:
                _create_mr(
                    db=db,
                    scan_id=scan_id,
                    finding_ids=finding_ids,
                    mr_type=mr_type,
                    target_kind=target_kind,
                    source_branch_template=source_branch_template,
                    target_branch=target_branch,
                    template_vars=template_vars,
                    gitlab_project_id=gitlab_project_id,
                    gitlab_token=gitlab_token,
                    image_digest=image_digest,
                )
            except Exception as exc:
                import gitlab as _gl_mod

                # Permanent GitLab errors should not be retried
                if isinstance(exc, _gl_mod.exceptions.GitlabError) and getattr(
                    exc, "response_code", None
                ) in (401, 403, 404):
                    log.error(
                        "mr_task_permanent_failure",
                        scan_id=scan_id,
                        status=exc.response_code,
                        error=str(exc),
                    )
                    raise  # surface immediately — no retry
                log.error("mr_task_failed", scan_id=scan_id, error=str(exc))
                raise self.retry(exc=exc)


def _create_mr(
    *,
    db,
    scan_id: str,
    finding_ids: list[str],
    mr_type: str,
    target_kind: str,
    source_branch_template: str,
    target_branch: str,
    template_vars: dict,
    gitlab_project_id: str,
    gitlab_token: str,
    image_digest: str,
) -> None:
    scan = db.get(Scan, scan_id)
    if not scan:
        log.warning("mr_task_scan_not_found", scan_id=scan_id)
        return

    image = db.get(Image, str(scan.image_id))

    # Single GitLabClient for all operations — no dual-session overhead
    gl = GitLabClient(url="https://gitlab.com", token=gitlab_token)

    dockerfile_path = (
        image.base_dockerfile_path
        if target_kind == "BASE_DOCKERFILE"
        else image.app_dockerfile_path
    )

    dockerfile_content = gl.get_file_content(gitlab_project_id, dockerfile_path, target_branch)

    # Build patch from selected findings
    findings = db.query(Finding).filter(Finding.id.in_(finding_ids)).all()
    finding_dicts = [
        {
            "pkg_name": f.pkg_name,
            "fixed_version": f.fixed_version,
            "is_fixable": f.is_fixable,
        }
        for f in findings
    ]

    patch_result = PatchGenerator().patch(dockerfile_content, finding_dicts)
    if not patch_result.patches_applied:
        log.info("mr_no_patches", scan_id=scan_id, target_kind=target_kind)
        return

    # Resolve branch name
    vars_with_image = {
        **template_vars,
        "image": image.repository.replace("/", "-"),
        "tag": image.tag,
    }
    source_branch = resolve_branch(source_branch_template, vars_with_image)

    # Build MR description
    raised_by = template_vars.get("raised_by", "unknown")
    cve_rows = "\n".join(
        f"| {f.vuln_id} | {f.pkg_name} | {f.installed_version} → {f.fixed_version} | {f.severity.value} |"
        for f in findings
        if f.is_fixable
    )
    description = (
        "## PatchPilot Security Fix\n\n"
        "| CVE | Package | Installed → Fixed | Severity |\n"
        "|-----|---------|-------------------|----------|\n"
        f"{cve_rows}\n\n"
        f"[View scan in PatchPilot](/scans/{scan_id})\n\n"
        f"> **Note:** Base image tag bump not automated. "
        "Consider upgrading the FROM line manually.\n\n"
        f"_Raised by PatchPilot on behalf of {raised_by}._"
    )

    # Create branch + commit + open/update MR
    gl.ensure_branch(gitlab_project_id, source_branch, target_branch)
    gl.commit_file(
        gitlab_project_id,
        source_branch,
        dockerfile_path,
        patch_result.patched_content,
        f"fix: pin vulnerable OS packages ({len(patch_result.patches_applied)} CVEs)",
    )
    mr_result = gl.create_or_update_mr(
        project_id=gitlab_project_id,
        source_branch=source_branch,
        target_branch=target_branch,
        title=f"🔒 [PatchPilot] Fix {len(findings)} vulnerabilities ({target_kind})",
        description=description,
        labels=["security", "patchpilot"],
    )

    # Upsert MR row — DB idempotency via unique partial index + ON CONFLICT
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = (
        pg_insert(MergeRequest)
        .values(
            id=str(_uuid.uuid4()),
            image_id=str(scan.image_id),
            scan_id=scan_id,
            mr_type=mr_type,
            target_kind=target_kind,
            gitlab_project_id=gitlab_project_id,
            gitlab_mr_iid=mr_result.iid,
            gitlab_mr_url=mr_result.url,
            gitlab_pipeline_id=mr_result.pipeline_id,
            pipeline_status=PipelineStatus.UNKNOWN,
            source_branch=source_branch,
            target_branch=target_branch,
            state=MRState.OPENED,
            finding_ids=finding_ids,
            image_digest=image_digest,
        )
        .on_conflict_do_update(
            # matches uix_mr_open: (gitlab_project_id, image_digest, target_branch, target_kind) WHERE state='OPENED'
            index_elements=["gitlab_project_id", "image_digest", "target_branch", "target_kind"],
            index_where="state = 'OPENED'",
            set_={
                "finding_ids": finding_ids,
                "gitlab_mr_iid": mr_result.iid,
                "gitlab_mr_url": mr_result.url,
            },
        )
    )
    db.execute(stmt)

    # Mark findings as MR_RAISED
    for f in findings:
        f.status = FindingStatus.MR_RAISED

    db.commit()
    log.info("mr_created", mr_url=mr_result.url, source_branch=source_branch)
