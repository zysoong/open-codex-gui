"""Container pool manager for efficient sandbox management."""

from typing import Dict
from pathlib import Path
import docker
from docker.errors import DockerException, ImageNotFound

from app.core.sandbox.container import SandboxContainer
from app.core.storage.storage_factory import create_storage
from app.core.storage.workspace_storage import WorkspaceStorage
from app.core.storage.project_volume_storage import get_project_volume_storage


class ContainerPoolManager:
    """Manage a pool of Docker containers for sandboxed execution."""

    def __init__(self, pool_size: int = 5, storage: WorkspaceStorage | None = None):
        """
        Initialize container pool manager.

        Args:
            pool_size: Maximum number of containers in pool
            storage: Storage backend (will be created from config if not provided)
        """
        self.pool_size = pool_size

        try:
            self.docker_client = docker.from_env()
        except DockerException as e:
            raise Exception(f"Failed to connect to Docker: {e}")

        # Initialize storage backend
        self.storage = storage or create_storage(docker_client=self.docker_client)

        # Track active containers by session ID
        self.active_containers: Dict[str, SandboxContainer] = {}

        # Environment type to image mapping
        self.env_images = {
            # Python environments
            "python3.11": "openclaudeui-env-python3.11:latest",
            "python3.12": "openclaudeui-env-python3.12:latest",
            "python3.13": "openclaudeui-env-python3.13:latest",
            # JavaScript/TypeScript environments
            "nodejs": "openclaudeui-env-nodejs:latest",
            "node20": "openclaudeui-env-node20:latest",  # Legacy alias
            # JVM languages
            "java": "openclaudeui-env-java:latest",
            "kotlin": "openclaudeui-env-kotlin:latest",
            "scala": "openclaudeui-env-scala:latest",
            # Systems languages
            "go": "openclaudeui-env-go:latest",
            "rust": "openclaudeui-env-rust:latest",
            "cpp": "openclaudeui-env-cpp:latest",
            # Scripting languages
            "ruby": "openclaudeui-env-ruby:latest",
            "php": "openclaudeui-env-php:latest",
            # .NET
            "dotnet": "openclaudeui-env-dotnet:latest",
        }

    def _ensure_image_exists(self, env_type: str) -> str:
        """
        Ensure Docker image exists, build if necessary.

        Args:
            env_type: Environment type

        Returns:
            Image name

        Raises:
            Exception if image cannot be found or built
        """
        image_name = self.env_images.get(env_type)
        if not image_name:
            raise ValueError(f"Unknown environment type: {env_type}")

        try:
            self.docker_client.images.get(image_name)
            return image_name
        except ImageNotFound:
            # Try to build the image
            print(f"Image {image_name} not found, attempting to build...")
            dockerfile_path = Path(__file__).parent / "environments" / f"{env_type}.Dockerfile"

            if not dockerfile_path.exists():
                raise Exception(f"Dockerfile not found: {dockerfile_path}")

            try:
                image, build_logs = self.docker_client.images.build(
                    path=str(dockerfile_path.parent),
                    dockerfile=str(dockerfile_path.name),
                    tag=image_name,
                    rm=True,
                )
                print(f"Successfully built image: {image_name}")
                return image_name
            except Exception as e:
                raise Exception(f"Failed to build image {image_name}: {e}")

    async def create_container(
        self,
        session_id: str,
        project_id: str,
        env_type: str = "python3.13",
        environment_config: Dict | None = None,
    ) -> SandboxContainer:
        """
        Create a new container for a session.

        Args:
            session_id: Chat session ID
            project_id: Project ID (for mounting project files volume)
            env_type: Environment type
            environment_config: Additional environment configuration

        Returns:
            SandboxContainer instance
        """
        # Check if container already exists for this session
        if session_id in self.active_containers:
            container = self.active_containers[session_id]
            if container.is_running:
                return container
            else:
                # Clean up dead container
                await self.destroy_container(session_id)

        # Check if orphaned container with same name exists in Docker
        container_name = f"openclaudeui-sandbox-{session_id}"
        try:
            existing = self.docker_client.containers.get(container_name)
            # Found orphaned container - remove it
            print(f"Found orphaned container {container_name}, removing...")
            existing.stop(timeout=2)
            existing.remove(force=True)
        except docker.errors.NotFound:
            # No orphaned container, good to proceed
            pass
        except Exception as e:
            print(f"Error checking for orphaned container: {e}")

        # Ensure image exists
        image_name = self._ensure_image_exists(env_type)

        # Create session workspace using storage backend (for /workspace/out)
        await self.storage.create_workspace(session_id)

        # Get session volume configuration (mounts to /workspace/out)
        session_volume_config = self.storage.get_volume_config(session_id)

        # Get project volume configuration (mounts to /workspace/project_files)
        project_storage = get_project_volume_storage(self.docker_client)
        await project_storage.ensure_volume(project_id)
        project_volume_config = project_storage.get_volume_mount_config(project_id)

        # Combine volume configurations
        volume_config = {**session_volume_config, **project_volume_config}

        # Prepare environment variables
        env_vars = {
            "SESSION_ID": session_id,
            "WORKSPACE": "/workspace",
        }

        if environment_config:
            env_vars.update(environment_config.get("env_vars", {}))

        # Create container with volume mount
        try:
            container = self.docker_client.containers.run(
                image_name,
                detach=True,
                tty=True,
                stdin_open=True,
                volumes=volume_config,
                environment=env_vars,
                network_mode="bridge",
                mem_limit="1g",  # Memory limit
                cpu_quota=50000,  # CPU limit (50% of one core)
                name=f"openclaudeui-sandbox-{session_id}",
            )

            # Install additional packages if specified
            if environment_config and "packages" in environment_config:
                packages = environment_config["packages"]
                if env_type.startswith("python"):
                    if packages:
                        install_cmd = f"pip install {' '.join(packages)}"
                        container.exec_run(["bash", "-c", install_cmd])
                elif env_type.startswith("node"):
                    if packages:
                        install_cmd = f"npm install -g {' '.join(packages)}"
                        container.exec_run(["bash", "-c", install_cmd])

            # For volume/S3 storage, workspace_path is not directly accessible from host
            workspace_display = (
                f"volume://{session_id}" if hasattr(self.storage, "get_volume_name") else "N/A"
            )
            sandbox = SandboxContainer(container, workspace_display)
            self.active_containers[session_id] = sandbox

            return sandbox

        except Exception as e:
            raise Exception(f"Failed to create container: {e}")

    async def get_container(self, session_id: str) -> SandboxContainer | None:
        """
        Get container for a session.

        Args:
            session_id: Chat session ID

        Returns:
            SandboxContainer if exists, None otherwise
        """
        container = self.active_containers.get(session_id)
        if container and container.is_running:
            return container
        return None

    async def reset_container(self, session_id: str) -> bool:
        """
        Reset container to clean state.

        Args:
            session_id: Chat session ID

        Returns:
            Success boolean
        """
        container = self.active_containers.get(session_id)
        if container:
            return container.reset()
        return False

    async def destroy_container(self, session_id: str) -> bool:
        """
        Destroy container and cleanup.

        Args:
            session_id: Chat session ID

        Returns:
            Success boolean
        """
        container = self.active_containers.pop(session_id, None)
        if container:
            try:
                container.stop()
                container.remove()
                return True
            except Exception as e:
                print(f"Error destroying container: {e}")
                return False
        return True

    async def cleanup_all(self):
        """Cleanup all active containers."""
        session_ids = list(self.active_containers.keys())
        for session_id in session_ids:
            await self.destroy_container(session_id)

    def get_container_stats(self, session_id: str) -> Dict | None:
        """
        Get container resource usage stats.

        Args:
            session_id: Chat session ID

        Returns:
            Stats dict or None
        """
        container = self.active_containers.get(session_id)
        if container and container.is_running:
            try:
                stats = container.container.stats(stream=False)
                return stats
            except Exception:
                return None
        return None


# Global container pool manager instance
_container_manager: ContainerPoolManager | None = None


def get_container_manager() -> ContainerPoolManager:
    """Get global container pool manager instance."""
    global _container_manager
    if _container_manager is None:
        _container_manager = ContainerPoolManager()
    return _container_manager
