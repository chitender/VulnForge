import uuid
from unittest.mock import MagicMock

import pytest

from app.models.registry import RegistryType
from app.workers.registry_adapters import get_adapter


def make_registry(rtype: RegistryType, url: str = "registry.example.com") -> MagicMock:
    reg = MagicMock()
    reg.id = uuid.uuid4()
    reg.type = rtype
    reg.registry_url = url
    reg.region = None
    return reg


def test_dockerhub_trivy_env():
    adapter = get_adapter(RegistryType.DOCKERHUB)
    env = adapter.get_trivy_env(
        {"username": "myuser", "password": "mypass"},
        make_registry(RegistryType.DOCKERHUB),
    )
    assert env["TRIVY_USERNAME"] == "myuser"
    assert env["TRIVY_PASSWORD"] == "mypass"


def test_generic_oci_trivy_env():
    adapter = get_adapter(RegistryType.GENERIC_OCI)
    env = adapter.get_trivy_env(
        {"username": "u", "password": "p"},
        make_registry(RegistryType.GENERIC_OCI),
    )
    assert env["TRIVY_USERNAME"] == "u"
    assert env["TRIVY_PASSWORD"] == "p"


def test_get_adapter_raises_for_unknown():
    with pytest.raises(ValueError, match="No adapter"):
        get_adapter("UNKNOWN_TYPE")  # type: ignore
