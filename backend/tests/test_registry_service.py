import pytest
from cryptography.fernet import Fernet

from app.core.credentials import CredentialStore, LocalKEKProvider
from app.models.registry import RegistryType
from app.services.registry_service import RegistryService

MASTER_KEY = Fernet.generate_key().decode()


@pytest.fixture
def store():
    return CredentialStore(LocalKEKProvider(MASTER_KEY))


@pytest.fixture
def service(store):
    return RegistryService(credential_store=store)


@pytest.mark.asyncio
async def test_create_registry_encrypts_creds(db, service, test_user):
    registry = await service.create(
        db=db,
        owner_id="00000000-0000-0000-0000-000000000001",
        team_id="00000000-0000-0000-0000-000000000002",
        name="My ECR",
        registry_type=RegistryType.ECR,
        registry_url="123456789.dkr.ecr.us-east-1.amazonaws.com",
        region="us-east-1",
        creds={"aws_access_key_id": "AKIA...", "aws_secret_access_key": "secret"},
    )
    assert registry.auth_ciphertext is not None
    assert registry.auth_dek_enc is not None
    assert b"AKIA" not in registry.auth_ciphertext
    assert b"secret" not in registry.auth_ciphertext


@pytest.mark.asyncio
async def test_list_registries_excludes_deleted(db, service, test_user):
    await service.create(
        db=db,
        owner_id="00000000-0000-0000-0000-000000000001",
        team_id="00000000-0000-0000-0000-000000000004",
        name="ActiveHub",
        registry_type=RegistryType.DOCKERHUB,
        registry_url="registry-1.docker.io",
        region=None,
        creds={"username": "user", "password": "pass"},
    )
    rows = await service.list(db=db, team_id="00000000-0000-0000-0000-000000000004")
    assert any(r.name == "ActiveHub" for r in rows)


@pytest.mark.asyncio
async def test_delete_soft_deletes(db, service, test_user):
    reg = await service.create(
        db=db,
        owner_id="00000000-0000-0000-0000-000000000001",
        team_id="00000000-0000-0000-0000-000000000005",
        name="ToDelete",
        registry_type=RegistryType.GENERIC_OCI,
        registry_url="myregistry.example.com",
        region=None,
        creds={"username": "u", "password": "p"},
    )
    await service.delete(db=db, registry_id=str(reg.id), team_id="00000000-0000-0000-0000-000000000005")
    rows = await service.list(db=db, team_id="00000000-0000-0000-0000-000000000005")
    assert not any(r.id == reg.id for r in rows)


@pytest.mark.asyncio
async def test_decrypt_creds_roundtrip(db, service, test_user):
    plaintext = {"aws_access_key_id": "AKIAIOSFODNN7EXAMPLE", "aws_secret_access_key": "wJalrXUtnFEMI"}
    reg = await service.create(
        db=db,
        owner_id="00000000-0000-0000-0000-000000000001",
        team_id="00000000-0000-0000-0000-000000000006",
        name="Roundtrip",
        registry_type=RegistryType.ECR,
        registry_url="111.dkr.ecr.eu-west-1.amazonaws.com",
        region="eu-west-1",
        creds=plaintext,
    )
    recovered = service.decrypt_creds(reg)
    assert recovered == plaintext
