from app.workers.findings_parser import parse_findings, summarize_findings
from app.models.finding import FindingStatus, Severity

SCAN_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

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
    findings = parse_findings(TRIVY_RESULTS, SCAN_ID)
    assert len(findings) == 2


def test_fixable_flag_set_when_fixed_version_present():
    findings = parse_findings(TRIVY_RESULTS, SCAN_ID)
    ssl = next(f for f in findings if f.vuln_id == "CVE-2024-1234")
    curl = next(f for f in findings if f.vuln_id == "CVE-2024-5678")
    assert ssl.is_fixable is True
    assert ssl.fixed_version == "3.0.14"
    assert curl.is_fixable is False
    assert curl.fixed_version is None


def test_severity_mapped_correctly():
    findings = parse_findings(TRIVY_RESULTS, SCAN_ID)
    ssl = next(f for f in findings if f.vuln_id == "CVE-2024-1234")
    assert ssl.severity == Severity.CRITICAL


def test_unknown_severity_defaults_to_unknown():
    results = [{
        "Target": "test",
        "Vulnerabilities": [
            {"VulnerabilityID": "CVE-X", "PkgName": "pkg",
             "InstalledVersion": "1.0", "FixedVersion": None,
             "Severity": "WEIRD", "Title": None, "PrimaryURL": None}
        ],
    }]
    findings = parse_findings(results, SCAN_ID)
    assert findings[0].severity == Severity.UNKNOWN


def test_status_defaults_to_open():
    findings = parse_findings(TRIVY_RESULTS, SCAN_ID)
    assert all(f.status == FindingStatus.OPEN for f in findings)


def test_target_preserved():
    findings = parse_findings(TRIVY_RESULTS, SCAN_ID)
    assert all(f.target == "debian (debian 12.5)" for f in findings)


def test_empty_results_returns_empty_list():
    assert parse_findings([], SCAN_ID) == []


def test_result_with_no_vulnerabilities_key():
    results = [{"Target": "clean-image", "Class": "os-pkgs"}]
    assert parse_findings(results, SCAN_ID) == []


def test_summarize_findings():
    findings = parse_findings(TRIVY_RESULTS, SCAN_ID)
    summary = summarize_findings(findings)
    assert summary["by_severity"]["CRITICAL"] == 1
    assert summary["by_severity"]["HIGH"] == 1
    assert summary["total"] == 2
    assert summary["fixable"] == 1
