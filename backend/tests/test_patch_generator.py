import textwrap

from app.workers.patch_generator import PatchGenerator

SIMPLE_DOCKERFILE = textwrap.dedent("""\
    FROM debian:12-slim
    RUN apt-get update && apt-get install -y libssl3 curl ca-certificates
    COPY app /app
    CMD ["/app/server"]
""")

MULTISTAGE_DOCKERFILE = textwrap.dedent("""\
    FROM golang:1.22 AS builder
    WORKDIR /src
    RUN apt-get update && apt-get install -y libssl-dev
    COPY . .
    RUN go build -o /app

    FROM debian:12-slim
    RUN apt-get update && apt-get install -y libssl3 curl
    COPY --from=builder /app /app
    CMD ["/app"]
""")

FIXABLE = [
    {"pkg_name": "libssl3", "fixed_version": "3.0.14", "is_fixable": True},
    {"pkg_name": "curl", "fixed_version": "7.88.1", "is_fixable": True},
]
UNFIXABLE = [
    {"pkg_name": "bash", "fixed_version": None, "is_fixable": False},
]


def test_pins_apt_packages():
    result = PatchGenerator().patch(SIMPLE_DOCKERFILE, FIXABLE)
    assert "libssl3=3.0.14" in result.patched_content
    assert "curl=7.88.1" in result.patched_content


def test_reports_patches_applied():
    result = PatchGenerator().patch(SIMPLE_DOCKERFILE, FIXABLE)
    pkgs = {p["pkg"] for p in result.patches_applied}
    assert pkgs == {"libssl3", "curl"}


def test_skips_unfixable_findings():
    result = PatchGenerator().patch(SIMPLE_DOCKERFILE, UNFIXABLE)
    assert result.patched_content == SIMPLE_DOCKERFILE
    assert result.patches_applied == []


def test_from_line_not_modified():
    result = PatchGenerator().patch(SIMPLE_DOCKERFILE, FIXABLE)
    assert "FROM debian:12-slim" in result.patched_content


def test_unrelated_lines_unchanged():
    result = PatchGenerator().patch(SIMPLE_DOCKERFILE, FIXABLE)
    assert "COPY app /app" in result.patched_content
    assert 'CMD ["/app/server"]' in result.patched_content


def test_multistage_only_patches_final_stage():
    result = PatchGenerator().patch(MULTISTAGE_DOCKERFILE, FIXABLE)
    lines = result.patched_content.splitlines()
    # Find the second FROM (final stage) line index
    from_indices = [i for i, ln in enumerate(lines) if ln.startswith("FROM")]
    assert len(from_indices) == 2
    final_stage_start = from_indices[1]
    builder_section = "\n".join(lines[:final_stage_start])
    final_section = "\n".join(lines[final_stage_start:])
    # builder stage must NOT be touched
    assert "libssl3=3.0.14" not in builder_section
    assert "libssl-dev=3.0.14" not in builder_section
    # final stage must have pins
    assert "libssl3=3.0.14" in final_section


def test_empty_findings_returns_unchanged():
    result = PatchGenerator().patch(SIMPLE_DOCKERFILE, [])
    assert result.patched_content == SIMPLE_DOCKERFILE
    assert result.patches_applied == []


def test_short_pkg_name_does_not_corrupt_longer_package():
    """libssl must not match libssl-dev and mangle it."""
    dockerfile = textwrap.dedent("""\
        FROM debian:12-slim
        RUN apt-get update && apt-get install -y libssl3 libssl3-dev
    """)
    findings = [{"pkg_name": "libssl3", "fixed_version": "3.0.14", "is_fixable": True}]
    result = PatchGenerator().patch(dockerfile, findings)
    # libssl3 gets pinned
    assert "libssl3=3.0.14" in result.patched_content
    # libssl3-dev must NOT be corrupted to libssl3=3.0.14-dev
    assert "libssl3-dev" in result.patched_content
    assert "libssl3=3.0.14-dev" not in result.patched_content


def test_package_already_pinned_gets_updated():
    dockerfile = textwrap.dedent("""\
        FROM debian:12-slim
        RUN apt-get install -y libssl3=3.0.2
    """)
    result = PatchGenerator().patch(dockerfile, FIXABLE[:1])  # only libssl3
    assert "libssl3=3.0.14" in result.patched_content
    assert "libssl3=3.0.2" not in result.patched_content
