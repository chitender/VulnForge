import pytest

from app.models.image import ServiceType
from app.models.registry import RegistryType
from app.services.image_service import ImageService
from app.services.registry_service import RegistryService
from app.core.credentials import CredentialStore, LocalKEKProvider
from cryptography.fernet import Fernet

OWNER_ID = "00000000-0000-0000-0000-000000000001"
TEAM_A = "00000000-0000-0000-0000-000000000020"
TEAM_B = "00000000-0000-0000-0000-000000000021"


@pytest.fixture(scope="module")
def cred_store():
    return CredentialStore(LocalKEKProvider(Fernet.generate_key().decode()))


@pytest.fixture
def image_svc():
    return ImageService()


@pytest.fixture
async def registry_id(db, cred_store, test_user):
    """Create a registry for image tests to reference."""
    svc = RegistryService(credential_store=cred_store)
    reg = await svc.create(
        db=db,
        owner_id=OWNER_ID,
        team_id=TEAM_A,
        name="Test Registry",
        registry_type=RegistryType.DOCKERHUB,
        registry_url="registry-1.docker.io",
        region=None,
        creds={"username": "user", "password": "pass"},
    )
    return str(reg.id)


@pytest.mark.asyncio
async def test_create_image(db, image_svc, registry_id, test_user):
    img = await image_svc.create(
        db=db,
        owner_id=OWNER_ID,
        team_id=TEAM_A,
        registry_id=registry_id,
        repository="myorg/payments-api",
        tag="1.4.2",
        service_type=ServiceType.BACKEND,
        base_dockerfile_path="docker/Dockerfile.base",
        app_dockerfile_path="Dockerfile",
        gitlab_project_id="myorg/payments-api",
        gitlab_default_branch="main",
    )
    assert img.repository == "myorg/payments-api"
    assert img.tag == "1.4.2"
    assert img.service_type == ServiceType.BACKEND
    assert str(img.team_id) == TEAM_A


@pytest.mark.asyncio
async def test_list_excludes_other_team(db, image_svc, registry_id, test_user):
    await image_svc.create(
        db=db,
        owner_id=OWNER_ID,
        team_id=TEAM_A,
        registry_id=registry_id,
        repository="myorg/web-app",
        tag="2.0.0",
        service_type=ServiceType.UI,
        base_dockerfile_path="Dockerfile.base",
        app_dockerfile_path="Dockerfile",
        gitlab_project_id="myorg/web-app",
        gitlab_default_branch="develop",
    )
    rows_a = await image_svc.list(db=db, team_id=TEAM_A)
    rows_b = await image_svc.list(db=db, team_id=TEAM_B)
    assert any(r.repository == "myorg/web-app" for r in rows_a)
    assert not any(r.repository == "myorg/web-app" for r in rows_b)


@pytest.mark.asyncio
async def test_update_tag(db, image_svc, registry_id, test_user):
    img = await image_svc.create(
        db=db,
        owner_id=OWNER_ID,
        team_id=TEAM_A,
        registry_id=registry_id,
        repository="myorg/auth-service",
        tag="1.0.0",
        service_type=ServiceType.BACKEND,
        base_dockerfile_path="Dockerfile",
        app_dockerfile_path="Dockerfile",
        gitlab_project_id="myorg/auth-service",
        gitlab_default_branch="main",
    )
    updated = await image_svc.update(
        db=db, image_id=str(img.id), team_id=TEAM_A, tag="1.0.1"
    )
    assert updated is not None
    assert updated.tag == "1.0.1"
    assert updated.repository == "myorg/auth-service"  # unchanged


@pytest.mark.asyncio
async def test_delete_soft_deletes(db, image_svc, registry_id, test_user):
    img = await image_svc.create(
        db=db,
        owner_id=OWNER_ID,
        team_id=TEAM_A,
        registry_id=registry_id,
        repository="myorg/to-delete",
        tag="0.1.0",
        service_type=ServiceType.BACKEND,
        base_dockerfile_path="Dockerfile",
        app_dockerfile_path="Dockerfile",
        gitlab_project_id="myorg/to-delete",
        gitlab_default_branch="main",
    )
    await image_svc.delete(db=db, image_id=str(img.id), team_id=TEAM_A)
    rows = await image_svc.list(db=db, team_id=TEAM_A)
    assert not any(r.id == img.id for r in rows)
    # get also returns None for deleted
    gone = await image_svc.get(db=db, image_id=str(img.id), team_id=TEAM_A)
    assert gone is None
