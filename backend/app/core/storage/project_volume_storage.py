"""Project-level Docker volume storage for user uploads.

This module manages Docker volumes at the project level, allowing files
to be shared across all chat sessions within a project. Files are mounted
read-only into session containers at /workspace/project_files/.
"""

import io
import tarfile
import asyncio
from typing import List, Optional
import docker
from docker.errors import NotFound as DockerNotFound

from app.core.storage.workspace_storage import FileInfo


class ProjectVolumeStorage:
    """Manages project-level Docker volumes for user uploads.

    Each project gets its own Docker volume where uploaded files are stored.
    Session containers mount this volume read-only at /workspace/project_files/.

    Volume naming: openclaudeui-project-{project_id}
    """

    def __init__(self, docker_client: Optional[docker.DockerClient] = None):
        """Initialize project volume storage.

        Args:
            docker_client: Docker client instance (creates one if not provided)
        """
        self.docker_client = docker_client or docker.from_env()

    def _get_volume_name(self, project_id: str) -> str:
        """Get Docker volume name for a project."""
        return f"openclaudeui-project-{project_id}"

    async def ensure_volume(self, project_id: str) -> str:
        """Create project volume if it doesn't exist.

        Args:
            project_id: Project ID

        Returns:
            Volume name
        """
        volume_name = self._get_volume_name(project_id)

        def _ensure():
            try:
                self.docker_client.volumes.get(volume_name)
            except DockerNotFound:
                self.docker_client.volumes.create(name=volume_name)
            return volume_name

        return await asyncio.to_thread(_ensure)

    async def write_file(self, project_id: str, filename: str, content: bytes) -> bool:
        """Write a file to the project volume.

        Args:
            project_id: Project ID
            filename: Name of the file (no path separators)
            content: File content as bytes

        Returns:
            True if successful
        """
        volume_name = self._get_volume_name(project_id)

        def _write():
            # Ensure volume exists
            try:
                self.docker_client.volumes.get(volume_name)
            except DockerNotFound:
                self.docker_client.volumes.create(name=volume_name)

            # Create tar archive with the file
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                tarinfo = tarfile.TarInfo(name=filename)
                tarinfo.size = len(content)
                tar.addfile(tarinfo, io.BytesIO(content))
            tar_stream.seek(0)

            # Use temporary container to write file
            container = self.docker_client.containers.run(
                "alpine:latest",
                command="sh -c 'sleep 2'",
                volumes={volume_name: {"bind": "/data", "mode": "rw"}},
                detach=True,
                remove=False,
            )

            try:
                container.wait(timeout=5)
                container.put_archive(path="/data", data=tar_stream.getvalue())
                return True
            finally:
                container.remove(force=True)

        try:
            return await asyncio.to_thread(_write)
        except Exception as e:
            print(f"Error writing file to project volume: {e}")
            return False

    async def read_file(self, project_id: str, filename: str) -> bytes:
        """Read a file from the project volume.

        Args:
            project_id: Project ID
            filename: Name of the file

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        volume_name = self._get_volume_name(project_id)

        def _read():
            container = self.docker_client.containers.run(
                "alpine:latest",
                command="sh -c 'sleep 5'",
                volumes={volume_name: {"bind": "/data", "mode": "ro"}},
                detach=True,
                remove=False,
            )

            try:
                bits, stat = container.get_archive(f"/data/{filename}")

                # Extract from tar
                tar_stream = io.BytesIO()
                for chunk in bits:
                    tar_stream.write(chunk)
                tar_stream.seek(0)

                with tarfile.open(fileobj=tar_stream, mode="r") as tar:
                    member = tar.next()
                    if member is None:
                        raise FileNotFoundError(f"File not found: {filename}")

                    file_obj = tar.extractfile(member)
                    if file_obj is None:
                        raise FileNotFoundError(f"File not found: {filename}")

                    return file_obj.read()
            finally:
                container.remove(force=True)

        try:
            return await asyncio.to_thread(_read)
        except Exception as e:
            if "No such file" in str(e) or "404" in str(e):
                raise FileNotFoundError(f"File not found: {filename}")
            raise

    async def list_files(self, project_id: str) -> List[FileInfo]:
        """List all files in the project volume.

        Args:
            project_id: Project ID

        Returns:
            List of FileInfo objects
        """
        volume_name = self._get_volume_name(project_id)

        def _list():
            try:
                self.docker_client.volumes.get(volume_name)
            except DockerNotFound:
                return []

            try:
                result = self.docker_client.containers.run(
                    "alpine:latest",
                    command="sh -c 'find /data -maxdepth 1 -type f -exec stat -c \"%n %s\" {} \\;'",
                    volumes={volume_name: {"bind": "/data", "mode": "ro"}},
                    remove=True,
                )

                files = []
                output = result.decode("utf-8").strip()

                if output:
                    for line in output.split("\n"):
                        parts = line.rsplit(" ", 1)
                        if len(parts) == 2:
                            file_path, size_str = parts
                            # file_path is like /data/filename.ext
                            filename = file_path.split("/")[-1]
                            files.append(
                                FileInfo(
                                    path=f"/workspace/project_files/{filename}",
                                    size=int(size_str),
                                    is_dir=False,
                                )
                            )

                return files
            except Exception as e:
                print(f"Error listing project files: {e}")
                return []

        return await asyncio.to_thread(_list)

    async def delete_file(self, project_id: str, filename: str) -> bool:
        """Delete a file from the project volume.

        Args:
            project_id: Project ID
            filename: Name of the file

        Returns:
            True if successful
        """
        volume_name = self._get_volume_name(project_id)

        def _delete():
            try:
                self.docker_client.containers.run(
                    "alpine:latest",
                    command=f"sh -c 'rm -f /data/{filename}'",
                    volumes={volume_name: {"bind": "/data", "mode": "rw"}},
                    remove=True,
                )
                return True
            except Exception as e:
                print(f"Error deleting file from project volume: {e}")
                return False

        return await asyncio.to_thread(_delete)

    async def delete_volume(self, project_id: str) -> bool:
        """Delete the entire project volume.

        Call this when a project is deleted.

        Args:
            project_id: Project ID

        Returns:
            True if successful
        """
        volume_name = self._get_volume_name(project_id)

        def _delete_volume():
            try:
                volume = self.docker_client.volumes.get(volume_name)
                volume.remove(force=True)
                return True
            except DockerNotFound:
                return True  # Already deleted
            except Exception as e:
                print(f"Error deleting project volume: {e}")
                return False

        return await asyncio.to_thread(_delete_volume)

    def get_volume_mount_config(self, project_id: str) -> dict:
        """Get Docker volume mount configuration for containers.

        This returns the mount config to add to container creation,
        mounting the project volume read-only at /workspace/project_files.

        Args:
            project_id: Project ID

        Returns:
            Docker volume configuration dict
        """
        volume_name = self._get_volume_name(project_id)
        return {
            volume_name: {
                "bind": "/workspace/project_files",
                "mode": "ro",  # Read-only for session containers
            }
        }

    async def volume_exists(self, project_id: str) -> bool:
        """Check if project volume exists.

        Args:
            project_id: Project ID

        Returns:
            True if volume exists
        """
        volume_name = self._get_volume_name(project_id)

        def _exists():
            try:
                self.docker_client.volumes.get(volume_name)
                return True
            except DockerNotFound:
                return False

        return await asyncio.to_thread(_exists)


# Global instance
_project_volume_storage: Optional[ProjectVolumeStorage] = None


def get_project_volume_storage(
    docker_client: Optional[docker.DockerClient] = None,
) -> ProjectVolumeStorage:
    """Get global project volume storage instance.

    Args:
        docker_client: Docker client (optional, creates one if needed)

    Returns:
        ProjectVolumeStorage instance
    """
    global _project_volume_storage

    if _project_volume_storage is None:
        _project_volume_storage = ProjectVolumeStorage(docker_client)

    return _project_volume_storage
