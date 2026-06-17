from __future__ import annotations

import uuid

from app.models.finding import Finding, FindingStatus, Severity

_SEVERITY_MAP: dict[str, Severity] = {
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
            fixed = vuln.get("FixedVersion") or None
            findings.append(
                Finding(
                    id=uuid.uuid4(),
                    scan_id=uuid.UUID(scan_id),
                    vuln_id=vuln["VulnerabilityID"],
                    pkg_name=vuln["PkgName"],
                    installed_version=vuln["InstalledVersion"],
                    fixed_version=fixed,
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
    return {
        "by_severity": counts,
        "total": len(findings),
        "fixable": sum(1 for f in findings if f.is_fixable),
    }
