"""Docker volume storage backend for production use."""

import io
import tarfile
import asyncio
from pathlib import Path
from typing import List, Optional
import docker

from app.core.storage.workspace_storage import WorkspaceStorage, FileInfo


class VolumeStorage(WorkspaceStorage):
    """Storage backend using Docker named volumes for better isolation."""

    def __init__(self, docker_client: Optional[docker.DockerClient] = None):
        """
        Initialize volume storage.

        Args:
            docker_client: Docker client instance (will create if not provided)
        """
        self.docker_client = docker_client or docker.from_env()
        # Keep track of volumes we create
        self._volumes = {}

    def _get_volume_name(self, session_id: str) -> str:
        """Get volume name for a session."""
        return f"openclaudeui-workspace-{session_id}"

    async def write_file(self, session_id: str, container_path: str, content: bytes) -> bool:
        """Write content to a file in the Docker volume."""
        try:
            volume_name = self._get_volume_name(session_id)

            # Create a temporary container to write to the volume
            def _write():
                # Create tar archive with the file
                tar_stream = io.BytesIO()
                tar = tarfile.open(fileobj=tar_stream, mode="w")

                # Get path components
                path = container_path.lstrip("/")
                file_name = path.split("/")[-1]

                # Add file to tar
                tarinfo = tarfile.TarInfo(name=file_name)
                tarinfo.size = len(content)
                tar.addfile(tarinfo, io.BytesIO(content))
                tar.close()

                tar_stream.seek(0)

                # Get directory path
                dir_path = "/".join(path.split("/")[:-1]) if "/" in path else ""

                # Run temporary container to write file
                container = self.docker_client.containers.run(
                    "alpine:latest",
                    command=f"sh -c 'mkdir -p /{dir_path} && sleep 1'",
                    volumes={volume_name: {"bind": "/workspace", "mode": "rw"}},
                    detach=True,
                    remove=False,
                )

                # Wait for container to start
                container.wait(timeout=5)

                # Write file using put_archive
                target_path = f"/{dir_path}" if dir_path else "/"
                container.put_archive(path=target_path, data=tar_stream.getvalue())

                # Clean up
                container.remove(force=True)

                return True

            return await asyncio.to_thread(_write)
        except Exception as e:
            print(f"Error writing file to volume: {e}")
            return False

    async def read_file(self, session_id: str, container_path: str) -> bytes:
        """Read a file from the Docker volume."""
        volume_name = self._get_volume_name(session_id)

        def _read():
            # Run temporary container to read file
            path = container_path.lstrip("/")

            container = self.docker_client.containers.run(
                "alpine:latest",
                command="sh -c 'sleep 5'",
                volumes={volume_name: {"bind": "/workspace", "mode": "ro"}},
                detach=True,
                remove=False,
            )

            try:
                # Get file using get_archive
                bits, stat = container.get_archive(f"/{path}")

                # Extract from tar
                tar_stream = io.BytesIO()
                for chunk in bits:
                    tar_stream.write(chunk)
                tar_stream.seek(0)

                tar = tarfile.open(fileobj=tar_stream, mode="r")
                member = tar.next()

                if member is None:
                    raise FileNotFoundError(f"File not found: {container_path}")

                file_content = tar.extractfile(member)
                if file_content is None:
                    raise FileNotFoundError(f"File not found: {container_path}")

                content = file_content.read()
                tar.close()

                return content
            finally:
                container.remove(force=True)

        try:
            return await asyncio.to_thread(_read)
        except Exception as e:
            if "No such file" in str(e) or "404" in str(e):
                raise FileNotFoundError(f"File not found: {container_path}")
            raise

    async def list_files(
        self, session_id: str, container_path: str = "/workspace"
    ) -> List[FileInfo]:
        """List files in a directory in the Docker volume."""
        volume_name = self._get_volume_name(session_id)

        def _list():
            path = container_path.lstrip("/")

            # Run temporary container to list files
            result = self.docker_client.containers.run(
                "alpine:latest",
                command=f"sh -c 'find /{path} -type f -exec stat -c \"%n %s\" {{}} \\;'",
                volumes={volume_name: {"bind": "/workspace", "mode": "ro"}},
                remove=True,
            )

            files = []
            output = result.decode("utf-8").strip()

            if output:
                for line in output.split("\n"):
                    parts = line.rsplit(" ", 1)
                    if len(parts) == 2:
                        file_path, size_str = parts
                        files.append(FileInfo(path=file_path, size=int(size_str), is_dir=False))

            return files

        try:
            return await asyncio.to_thread(_list)
        except Exception as e:
            print(f"Error listing files: {e}")
            return []

    async def delete_file(self, session_id: str, container_path: str) -> bool:
        """Delete a file from the Docker volume."""
        try:
            volume_name = self._get_volume_name(session_id)

            def _delete():
                path = container_path.lstrip("/")

                # Run temporary container to delete file
                self.docker_client.containers.run(
                    "alpine:latest",
                    command=f"sh -c 'rm -rf /{path}'",
                    volumes={volume_name: {"bind": "/workspace", "mode": "rw"}},
                    remove=True,
                )
                return True

            return await asyncio.to_thread(_delete)
        except Exception as e:
            print(f"Error deleting file from volume: {e}")
            return False

    async def file_exists(self, session_id: str, container_path: str) -> bool:
        """Check if a file exists in the Docker volume."""
        try:
            volume_name = self._get_volume_name(session_id)

            def _exists():
                path = container_path.lstrip("/")

                # Run temporary container to check file
                result = self.docker_client.containers.run(
                    "alpine:latest",
                    command=f"sh -c 'test -e /{path} && echo exists || echo notfound'",
                    volumes={volume_name: {"bind": "/workspace", "mode": "ro"}},
                    remove=True,
                )

                return b"exists" in result

            return await asyncio.to_thread(_exists)
        except Exception:
            return False

    async def create_workspace(self, session_id: str) -> None:
        """Create a new Docker volume for a session."""
        volume_name = self._get_volume_name(session_id)

        def _create():
            try:
                # Create volume
                volume = self.docker_client.volumes.create(name=volume_name)
                self._volumes[session_id] = volume

                # Initialize directory structure
                # Note: /workspace/project_files is mounted from project volume
                self.docker_client.containers.run(
                    "alpine:latest",
                    command="sh -c 'mkdir -p /workspace/out'",
                    volumes={volume_name: {"bind": "/workspace", "mode": "rw"}},
                    remove=True,
                )
            except docker.errors.APIError as e:
                if "already exists" not in str(e):
                    raise

        await asyncio.to_thread(_create)

    async def delete_workspace(self, session_id: str) -> None:
        """Delete the Docker volume for a session."""
        volume_name = self._get_volume_name(session_id)

        def _delete():
            try:
                volume = self.docker_client.volumes.get(volume_name)
                volume.remove(force=True)
                if session_id in self._volumes:
                    del self._volumes[session_id]
            except docker.errors.NotFound:
                pass  # Volume already deleted

        await asyncio.to_thread(_delete)

    async def copy_to_workspace(
        self, session_id: str, source_path: Path, dest_container_path: str
    ) -> None:
        """Copy files from host to Docker volume."""
        volume_name = self._get_volume_name(session_id)

        def _copy():
            # Create tar archive from source
            tar_stream = io.BytesIO()
            tar = tarfile.open(fileobj=tar_stream, mode="w")

            if source_path.is_file():
                tar.add(source_path, arcname=source_path.name)
            elif source_path.is_dir():
                for file in source_path.rglob("*"):
                    if file.is_file():
                        arcname = file.relative_to(source_path.parent)
                        tar.add(file, arcname=str(arcname))

            tar.close()
            tar_stream.seek(0)

            # Get destination path
            dest_path = dest_container_path.lstrip("/")
            parent_path = "/".join(dest_path.split("/")[:-1]) if "/" in dest_path else ""

            # Run temporary container to copy files
            container = self.docker_client.containers.run(
                "alpine:latest",
                command=f"sh -c 'mkdir -p /{parent_path} && sleep 2'",
                volumes={volume_name: {"bind": "/workspace", "mode": "rw"}},
                detach=True,
                remove=False,
            )

            try:
                container.wait(timeout=3)

                # Put archive
                target_path = f"/{parent_path}" if parent_path else "/"
                container.put_archive(path=target_path, data=tar_stream.getvalue())
            finally:
                container.remove(force=True)

        await asyncio.to_thread(_copy)

    def get_volume_config(self, session_id: str) -> dict:
        """
        Get Docker volume configuration for named volume.

        Args:
            session_id: Session ID

        Returns:
            Docker volume configuration dict
        """
        volume_name = self._get_volume_name(session_id)
        return {volume_name: {"bind": "/workspace", "mode": "rw"}}
