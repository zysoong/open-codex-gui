"""Docker container wrapper for sandbox execution."""

import os
import asyncio
from typing import Dict, Any, Tuple
import docker
from docker.models.containers import Container as DockerContainer


class SandboxContainer:
    """Wrapper for a Docker container used as a sandbox."""

    def __init__(self, container: DockerContainer, workspace_path: str):
        """
        Initialize sandbox container.

        Args:
            container: Docker container instance
            workspace_path: Host path to workspace directory
        """
        self.container = container
        self.workspace_path = workspace_path
        self.container_id = container.id

    @property
    def is_running(self) -> bool:
        """Check if container is running."""
        try:
            self.container.reload()
            return self.container.status == "running"
        except Exception:
            return False

    async def execute(
        self,
        command: str,
        workdir: str = "/workspace",
        timeout: int = 30
    ) -> Tuple[int, str, str]:
        """
        Execute a command in the container.

        Args:
            command: Command to execute
            workdir: Working directory for command
            timeout: Execution timeout in seconds

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        try:
            # Execute command in container
            exec_result = self.container.exec_run(
                cmd=["bash", "-c", command],
                workdir=workdir,
                demux=True,
                stream=False,
            )

            exit_code = exec_result.exit_code
            stdout = exec_result.output[0].decode("utf-8") if exec_result.output[0] else ""
            stderr = exec_result.output[1].decode("utf-8") if exec_result.output[1] else ""

            return exit_code, stdout, stderr

        except Exception as e:
            return 1, "", f"Execution error: {str(e)}"

    async def execute_stream(
        self,
        command: str,
        workdir: str = "/workspace"
    ):
        """
        Execute a command and stream output.

        Args:
            command: Command to execute
            workdir: Working directory

        Yields:
            Output chunks
        """
        try:
            exec_instance = self.container.exec_run(
                cmd=["bash", "-c", command],
                workdir=workdir,
                stream=True,
                demux=True,
            )

            for stdout, stderr in exec_instance.output:
                if stdout:
                    yield stdout.decode("utf-8")
                if stderr:
                    yield f"[ERROR] {stderr.decode('utf-8')}"

        except Exception as e:
            yield f"[ERROR] Execution error: {str(e)}"

    async def write_file(self, container_path: str, content: str) -> bool:
        """
        Write content to a file in the container.

        Args:
            container_path: Path inside container
            content: File content

        Returns:
            Success boolean
        """
        try:
            # Create a tar archive with the file
            import tarfile
            import io
            import asyncio

            # Run blocking I/O in thread pool
            def _write():
                tar_stream = io.BytesIO()
                tar = tarfile.open(fileobj=tar_stream, mode='w')

                # Add file to tar
                file_data = content.encode('utf-8')
                tarinfo = tarfile.TarInfo(name=os.path.basename(container_path))
                tarinfo.size = len(file_data)
                tar.addfile(tarinfo, io.BytesIO(file_data))
                tar.close()

                # Put tar archive in container
                tar_stream.seek(0)
                self.container.put_archive(
                    path=os.path.dirname(container_path),
                    data=tar_stream
                )
                return True

            return await asyncio.to_thread(_write)

        except Exception as e:
            print(f"Error writing file: {e}")
            return False

    async def read_file(self, container_path: str) -> str | None:
        """
        Read a file from the container.

        Args:
            container_path: Path inside container

        Returns:
            File content or None if error
            For binary files (images, etc), returns base64-encoded string with prefix "data:image/..."
        """
        try:
            import tarfile
            import io
            import asyncio
            import base64
            import mimetypes

            # Run blocking I/O in thread pool
            def _read():
                # Get file as tar archive
                bits, stat = self.container.get_archive(container_path)

                # Extract content from tar
                tar_stream = io.BytesIO()
                for chunk in bits:
                    tar_stream.write(chunk)
                tar_stream.seek(0)

                tar = tarfile.open(fileobj=tar_stream)
                member = tar.next()
                if member:
                    f = tar.extractfile(member)
                    if f:
                        raw_bytes = f.read()

                        # Try to decode as UTF-8 text
                        try:
                            content = raw_bytes.decode('utf-8')
                            return content
                        except UnicodeDecodeError:
                            # Binary file - encode as base64 with data URI
                            # Guess MIME type from file extension
                            mime_type, _ = mimetypes.guess_type(container_path)
                            if mime_type is None:
                                mime_type = 'application/octet-stream'

                            b64_data = base64.b64encode(raw_bytes).decode('ascii')
                            return f"data:{mime_type};base64,{b64_data}"

                return None

            return await asyncio.to_thread(_read)

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error reading file: {e}")
            print(f"Full traceback:\n{error_details}")
            # Return error as string so FileReadTool can display it
            raise Exception(f"Failed to read file: {str(e)}")

    def list_files(self, container_path: str = "/workspace") -> list[str]:
        """
        List files in a directory.

        Args:
            container_path: Directory path in container

        Returns:
            List of file paths
        """
        try:
            exit_code, stdout, stderr = asyncio.run(
                self.execute(f"find {container_path} -type f")
            )
            if exit_code == 0:
                return [f.strip() for f in stdout.split('\n') if f.strip()]
            return []
        except Exception:
            return []

    def reset(self) -> bool:
        """
        Reset container to clean state.

        Returns:
            Success boolean
        """
        try:
            # Clean agent workspace and out
            asyncio.run(self.execute("rm -rf /workspace/agent_workspace/* /workspace/out/*"))
            return True
        except Exception as e:
            print(f"Error resetting container: {e}")
            return False

    def stop(self):
        """Stop the container."""
        try:
            self.container.stop(timeout=5)
        except Exception as e:
            print(f"Error stopping container: {e}")

    def remove(self):
        """Remove the container."""
        try:
            self.container.remove(force=True)
        except Exception as e:
            print(f"Error removing container: {e}")
