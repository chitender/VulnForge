"""Dockerfile patch generator — OS-package pinning via dockerfile-parse.

Scope (v1): pins fixable OS packages in the *final* stage's RUN blocks only.
FROM lines are never modified (base image tag bump is out of scope for v1).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from dockerfile_parse import DockerfileParser


@dataclass
class PatchResult:
    patched_content: str
    patches_applied: list[dict] = field(default_factory=list)


class PatchGenerator:
    def patch(self, dockerfile_content: str, findings: list[dict]) -> PatchResult:
        """Apply OS-package version pins from fixable findings to the final stage.

        Args:
            dockerfile_content: raw Dockerfile text
            findings: list of dicts with keys pkg_name, fixed_version, is_fixable

        Returns:
            PatchResult with the patched content and a list of applied patches.
        """
        fixable = {
            f["pkg_name"]: f["fixed_version"]
            for f in findings
            if f.get("is_fixable") and f.get("fixed_version")
        }
        if not fixable:
            return PatchResult(patched_content=dockerfile_content)

        # Parse structure via dockerfile-parse (BuildKit-compatible)
        dfp = DockerfileParser(fileobj=io.BytesIO(dockerfile_content.encode()))
        structure = dfp.structure  # list of {instruction, startline, endline, value}

        # Locate the final FROM — all RUN blocks before it belong to earlier stages
        from_indices = [i for i, s in enumerate(structure) if s["instruction"] == "FROM"]
        final_stage_start_idx = from_indices[-1] if from_indices else 0

        patches_applied: list[dict] = []
        content = dockerfile_content

        for i, item in enumerate(structure):
            if i <= final_stage_start_idx:
                continue  # skip builder stages
            if item["instruction"] != "RUN":
                continue

            run_value = item["value"]
            new_run_value = run_value
            changed = False

            for pkg, fixed_ver in fixable.items():
                if not self._pkg_in_run(pkg, new_run_value):
                    continue
                updated, was_changed = self._pin_package(new_run_value, pkg, fixed_ver)
                if was_changed:
                    new_run_value = updated
                    changed = True
                    patches_applied.append({"pkg": pkg, "pinned_to": fixed_ver})

            if changed:
                content = content.replace(run_value, new_run_value, 1)

        return PatchResult(patched_content=content, patches_applied=patches_applied)

    # ── internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _pkg_in_run(pkg: str, run_value: str) -> bool:
        """True if pkg appears as a word boundary in the RUN instruction."""
        return bool(re.search(rf"\b{re.escape(pkg)}\b", run_value))

    @staticmethod
    def _pin_package(run_value: str, pkg: str, fixed_version: str) -> tuple[str, bool]:
        """Replace `pkg` or `pkg=old` with `pkg=fixed_version` (first occurrence)."""
        pattern = re.compile(rf"\b{re.escape(pkg)}(?:=[^\s\\]+)?")
        new_val, n = pattern.subn(f"{pkg}={fixed_version}", run_value, count=1)
        return new_val, n > 0
