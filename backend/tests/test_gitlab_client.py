from unittest.mock import MagicMock, patch

import pytest

from app.workers.gitlab_client import GitLabClient, MRResult


def _make_client():
    with patch("app.workers.gitlab_client.gitlab.Gitlab") as MockGL:
        client = GitLabClient(url="https://gitlab.example.com", token="fake-token")
        client._gl = MockGL.return_value
        return client, MockGL


def test_ensure_branch_creates_when_absent():
    client, _ = _make_client()
    mock_project = MagicMock()
    mock_project.branches.list.return_value = []
    client._gl.projects.get.return_value = mock_project

    client.ensure_branch("myorg/repo", "hotfix/test", "main")

    mock_project.branches.create.assert_called_once_with(
        {"branch": "hotfix/test", "ref": "main"}
    )


def test_ensure_branch_skips_if_exists():
    client, _ = _make_client()
    mock_branch = MagicMock()
    mock_branch.name = "hotfix/test"
    mock_project = MagicMock()
    mock_project.branches.list.return_value = [mock_branch]
    client._gl.projects.get.return_value = mock_project

    client.ensure_branch("myorg/repo", "hotfix/test", "main")

    mock_project.branches.create.assert_not_called()


def test_create_mr_returns_result():
    client, _ = _make_client()
    mock_project = MagicMock()
    mock_project.mergerequests.list.return_value = []  # no existing MR
    mock_mr = MagicMock()
    mock_mr.iid = 42
    mock_mr.web_url = "https://gitlab.example.com/myorg/repo/-/merge_requests/42"
    mock_mr.pipelines.list.return_value = []
    mock_project.mergerequests.create.return_value = mock_mr
    client._gl.projects.get.return_value = mock_project

    result = client.create_or_update_mr(
        project_id="myorg/repo",
        source_branch="hotfix/test",
        target_branch="main",
        title="🔒 Fix CVEs",
        description="desc",
        labels=["security"],
    )

    assert isinstance(result, MRResult)
    assert result.iid == 42
    assert result.pipeline_id is None


def test_update_existing_mr():
    client, _ = _make_client()
    mock_mr = MagicMock()
    mock_mr.iid = 7
    mock_mr.web_url = "https://gitlab.example.com/mr/7"
    mock_mr.pipelines.list.return_value = []
    mock_project = MagicMock()
    mock_project.mergerequests.list.return_value = [mock_mr]
    client._gl.projects.get.return_value = mock_project

    result = client.create_or_update_mr(
        project_id="myorg/repo",
        source_branch="hotfix/test",
        target_branch="main",
        title="🔒 Fix CVEs",
        description="updated desc",
        labels=["security"],
    )

    mock_mr.save.assert_called_once()
    assert result.iid == 7
