import json
from unittest.mock import MagicMock, patch

import pytest

from app.workers.trivy_client import TrivyClient

SAMPLE_REPORT = {
    "SchemaVersion": 2,
    "Metadata": {
        "ImageID": "sha256:abc123def456",
        "OS": {"Family": "debian", "Name": "12.5"},
    },
    "Results": [
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
                    "Title": "OpenSSL vuln",
                    "PrimaryURL": "https://nvd.nist.gov/vuln/detail/CVE-2024-1234",
                }
            ],
        }
    ],
}


def _mock_proc(returncode: int = 0, stdout: str = "", stderr: str = ""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


def test_scan_parses_image_digest():
    with patch("subprocess.run", return_value=_mock_proc(stdout=json.dumps(SAMPLE_REPORT))):
        result = TrivyClient("http://trivy-server:4954").scan("myimage:1.0", {})
    assert result.image_digest == "sha256:abc123def456"


def test_scan_returns_results():
    with patch("subprocess.run", return_value=_mock_proc(stdout=json.dumps(SAMPLE_REPORT))):
        result = TrivyClient("http://trivy-server:4954").scan("myimage:1.0", {})
    assert len(result.results) == 1
    assert result.results[0]["Vulnerabilities"][0]["VulnerabilityID"] == "CVE-2024-1234"


def test_scan_raises_on_nonzero_exit():
    with patch("subprocess.run", return_value=_mock_proc(returncode=1, stderr="image not found")):
        with pytest.raises(RuntimeError, match="trivy failed"):
            TrivyClient("http://trivy-server:4954").scan("badimage:1.0", {})


def test_scan_creds_not_in_subprocess_env_log(caplog):
    """Cred env vars must not appear in any log output."""
    with patch("subprocess.run", return_value=_mock_proc(stdout=json.dumps(SAMPLE_REPORT))):
        TrivyClient("http://trivy-server:4954").scan(
            "myimage:1.0", {"TRIVY_PASSWORD": "super_secret_token"}
        )
    assert "super_secret_token" not in caplog.text


def test_trivy_cmd_uses_server_flag():
    """Verify --server is passed so DB matching goes to trivy-server, not subprocess."""
    captured = {}

    def capture_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _mock_proc(stdout=json.dumps(SAMPLE_REPORT))

    with patch("subprocess.run", side_effect=capture_run):
        TrivyClient("http://trivy-server:4954").scan("myimage:1.0", {})

    assert "--server" in captured["cmd"]
    assert "http://trivy-server:4954" in captured["cmd"]


def test_scan_empty_results_when_no_vulnerabilities():
    report = {**SAMPLE_REPORT, "Results": []}
    with patch("subprocess.run", return_value=_mock_proc(stdout=json.dumps(report))):
        result = TrivyClient("http://trivy-server:4954").scan("clean:1.0", {})
    assert result.results == []
