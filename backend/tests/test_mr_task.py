import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.mr_task import dispatch_mr_task, _dedup_key


def _dispatch_kwargs(**overrides):
    base = dict(
        scan_id=str(uuid.uuid4()),
        finding_ids=[str(uuid.uuid4())],
        mr_type="HOTFIX",
        target_kind="APP_DOCKERFILE",
        source_branch_template="hotfix/{image}-sec",
        target_branch="main",
        template_vars={},
        gitlab_project_id="myorg/payments",
        gitlab_token="glpat-fake",
        image_digest="sha256:abc",
    )
    base.update(overrides)
    return base


def test_dispatch_enqueues_task_first_time():
    with patch("app.tasks.mr_task._redis") as mock_redis, \
         patch("app.tasks.mr_task.create_mr_task") as mock_task:
        mock_redis.set.return_value = True  # lock acquired
        result = dispatch_mr_task(**_dispatch_kwargs())

    assert result is True
    mock_task.apply_async.assert_called_once()


def test_dispatch_deduplicates_second_call():
    with patch("app.tasks.mr_task._redis") as mock_redis, \
         patch("app.tasks.mr_task.create_mr_task") as mock_task:
        mock_redis.set.return_value = False  # lock already held
        result = dispatch_mr_task(**_dispatch_kwargs())

    assert result is False
    mock_task.apply_async.assert_not_called()


def test_dedup_key_same_for_same_inputs():
    k1 = _dedup_key("proj", "sha256:abc", "main", "APP_DOCKERFILE")
    k2 = _dedup_key("proj", "sha256:abc", "main", "APP_DOCKERFILE")
    assert k1 == k2


def test_dedup_key_differs_for_different_target():
    k1 = _dedup_key("proj", "sha256:abc", "main", "APP_DOCKERFILE")
    k2 = _dedup_key("proj", "sha256:abc", "main", "BASE_DOCKERFILE")
    assert k1 != k2


def test_dedup_key_differs_for_different_branch():
    k1 = _dedup_key("proj", "sha256:abc", "main", "APP_DOCKERFILE")
    k2 = _dedup_key("proj", "sha256:abc", "develop", "APP_DOCKERFILE")
    assert k1 != k2
