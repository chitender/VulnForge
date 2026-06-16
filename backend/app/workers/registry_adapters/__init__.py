from app.models.registry import RegistryType
from app.workers.registry_adapters.base import BaseRegistryAdapter
from app.workers.registry_adapters.dockerhub import DockerHubAdapter
from app.workers.registry_adapters.generic import GenericOCIAdapter

_ADAPTERS: dict[RegistryType, BaseRegistryAdapter] = {
    RegistryType.DOCKERHUB: DockerHubAdapter(),
    RegistryType.GENERIC_OCI: GenericOCIAdapter(),
}


def get_adapter(registry_type: RegistryType) -> BaseRegistryAdapter:
    adapter = _ADAPTERS.get(registry_type)
    if adapter is None:
        raise ValueError(f"No adapter registered for registry type: {registry_type}")
    return adapter
