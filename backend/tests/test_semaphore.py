from unittest.mock import MagicMock

from app.core.semaphore import RegistrySemaphore


def test_acquire_returns_true_when_under_cap():
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 3
    sem = RegistrySemaphore(redis_client=mock_redis, max_per_registry=10)
    assert sem.acquire("reg-id-1") is True


def test_acquire_returns_false_when_at_cap():
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 11
    sem = RegistrySemaphore(redis_client=mock_redis, max_per_registry=10)
    assert sem.acquire("reg-id-1") is False
    mock_redis.decr.assert_called_once()


def test_release_decrements_counter():
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 1
    sem = RegistrySemaphore(redis_client=mock_redis, max_per_registry=10)
    sem.acquire("reg-id-2")
    sem.release("reg-id-2")
    mock_redis.decr.assert_called_once()


def test_key_is_namespaced():
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 1
    sem = RegistrySemaphore(redis_client=mock_redis, max_per_registry=10)
    sem.acquire("my-registry-id")
    mock_redis.incr.assert_called_with("registry_sem:my-registry-id")
