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
        self._server_url = server_url

    def scan(self, image_ref: str, cred_env: dict[str, str]) -> TrivyScanResult:
        env = {**os.environ, **cred_env}
        cmd = [
            "trivy", "image",
            "--server", self._server_url,
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
            raise RuntimeError(
                f"trivy failed (exit {proc.returncode}): {proc.stderr[:2000]}"
            )

        report = json.loads(proc.stdout)
        meta = report.get("Metadata", {})
        return TrivyScanResult(
            image_digest=meta.get("ImageID", ""),
            results=report.get("Results", []),
            trivy_version=str(report.get("SchemaVersion", "")),
            db_version=str(meta.get("DBSchema", {}).get("Version", "")),
        )

    def cleanup(self) -> None:
        """Remove cached image layers from worker disk after scan."""
        subprocess.run(
            ["trivy", "image", "--clear-cache"],
            capture_output=True,
            timeout=60,
        )
