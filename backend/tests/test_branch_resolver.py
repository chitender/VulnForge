import pytest

from app.workers.branch_resolver import resolve_branch


def test_resolves_all_variables():
    result = resolve_branch(
        "hotfix/backend/{version}-sec-{image}",
        {"version": "1.4.2", "image": "payments-api", "date": "2026-06-17"},
    )
    assert result == "hotfix/backend/1.4.2-sec-payments-api"


def test_image_slug_replaces_slashes():
    result = resolve_branch(
        "feature/{image}-patch",
        {"image": "myorg/payments/api"},
    )
    assert result == "feature/myorg-payments-api-patch"


def test_unknown_variables_left_as_is():
    result = resolve_branch("fix/{unknown}", {})
    assert result == "fix/{unknown}"


def test_raises_on_empty_template():
    with pytest.raises(ValueError):
        resolve_branch("", {"image": "foo"})


def test_raises_on_whitespace_only_template():
    with pytest.raises(ValueError):
        resolve_branch("   ", {})


def test_date_variable_not_double_substituted():
    # {date} value contains no further {placeholders}
    result = resolve_branch("{date}-fix", {"date": "2026-06-17"})
    assert result == "2026-06-17-fix"


def test_partial_substitution():
    result = resolve_branch("{image}-{tag}", {"image": "myapp"})
    assert result == "myapp-{tag}"  # {tag} left as-is when not in vars
