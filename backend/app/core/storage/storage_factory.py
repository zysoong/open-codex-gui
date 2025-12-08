"""Factory for creating storage backends based on configuration."""

import docker
from typing import Optional

from app.core.config import settings
from app.core.storage.workspace_storage import WorkspaceStorage
from app.core.storage.local_storage import LocalStorage
from app.core.storage.volume_storage import VolumeStorage
from app.core.storage.s3_storage import S3Storage
from app.core.storage.project_volume_storage import (
    ProjectVolumeStorage,
    get_project_volume_storage,
)


def create_storage(
    mode: Optional[str] = None,
    docker_client: Optional[docker.DockerClient] = None
) -> WorkspaceStorage:
    """
    Create appropriate storage backend based on configuration.

    Args:
        mode: Storage mode override (defaults to settings.storage_mode)
        docker_client: Docker client instance (required for volume storage)

    Returns:
        WorkspaceStorage implementation

    Raises:
        ValueError: If mode is invalid or required configuration is missing
    """
    storage_mode = mode or settings.storage_mode

    if storage_mode == "local":
        return LocalStorage(workspace_base=settings.storage_workspace_base)

    elif storage_mode == "volume":
        if docker_client is None:
            docker_client = docker.from_env()
        return VolumeStorage(docker_client=docker_client)

    elif storage_mode == "s3":
        if not settings.s3_bucket_name:
            raise ValueError("S3 storage requires s3_bucket_name to be configured")

        return S3Storage(
            bucket_name=settings.s3_bucket_name,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region
        )

    else:
        raise ValueError(
            f"Invalid storage mode: {storage_mode}. "
            f"Valid options are: local, volume, s3"
        )


# Global storage instance (lazy initialized)
_storage_instance: Optional[WorkspaceStorage] = None


def get_storage(docker_client: Optional[docker.DockerClient] = None) -> WorkspaceStorage:
    """
    Get global storage instance (singleton pattern).

    Args:
        docker_client: Docker client instance (required for volume storage)

    Returns:
        WorkspaceStorage implementation
    """
    global _storage_instance

    if _storage_instance is None:
        _storage_instance = create_storage(docker_client=docker_client)

    return _storage_instance
