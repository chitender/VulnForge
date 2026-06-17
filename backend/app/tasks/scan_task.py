from __future__ import annotations

import structlog
import redis as redis_lib
from opentelemetry import trace

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.credentials import CredentialStore
from app.core.db import SyncSessionLocal
from app.models.finding import Finding
from app.models.scan import Scan, ScanStatus
from app.workers.findings_parser import parse_findings, summarize_findings
from app.workers.registry_adapters import get_adapter
from app.workers.trivy_client import TrivyClient

log = structlog.get_logger()
tracer = trace.get_tracer(__name__)
_redis = redis_lib.from_url(settings.REDIS_URL)


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

            image = scan.image
            registry = image.registry
            trivy = TrivyClient(settings.TRIVY_SERVER_URL)

            try:
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
                _redis.rpush("scans_dlq", scan_id)
                raise self.retry(exc=exc)

            finally:
                try:
                    trivy.cleanup()
                except Exception:
                    pass
