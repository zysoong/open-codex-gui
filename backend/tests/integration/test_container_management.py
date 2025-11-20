"""Integration tests for container pool management."""

import pytest
from app.core.sandbox.manager import get_container_manager, ContainerPoolManager


@pytest.mark.integration
@pytest.mark.container
class TestContainerManagement:
    """Test container lifecycle management."""

    @pytest.mark.asyncio
    async def test_create_container(self, skip_if_no_docker):
        """Test creating a new container."""
        manager = get_container_manager()
        session_id = "test-session-create"

        try:
            container = await manager.create_container(
                session_id=session_id,
                env_type="python3.11"
            )

            assert container is not None
            assert container.is_running
            assert container.container_id is not None
        finally:
            # Cleanup
            await manager.destroy_container(session_id)

    @pytest.mark.asyncio
    async def test_container_reuse(self, skip_if_no_docker):
        """Test that creating a container with same session ID reuses existing container."""
        manager = get_container_manager()
        session_id = "test-session-reuse"

        try:
            # Create first container
            container1 = await manager.create_container(session_id, "python3.11")
            container1_id = container1.container_id

            # Try to create again with same session ID
            container2 = await manager.create_container(session_id, "python3.11")
            container2_id = container2.container_id

            # Should be the same container
            assert container1_id == container2_id
        finally:
            await manager.destroy_container(session_id)

    @pytest.mark.asyncio
    async def test_get_container(self, skip_if_no_docker):
        """Test getting an existing container."""
        manager = get_container_manager()
        session_id = "test-session-get"

        try:
            # Create container
            created = await manager.create_container(session_id, "python3.11")

            # Get container
            retrieved = await manager.get_container(session_id)

            assert retrieved is not None
            assert retrieved.container_id == created.container_id
        finally:
            await manager.destroy_container(session_id)

    @pytest.mark.asyncio
    async def test_get_nonexistent_container(self):
        """Test getting a container that doesn't exist."""
        manager = get_container_manager()

        container = await manager.get_container("nonexistent-session")

        assert container is None

    @pytest.mark.asyncio
    async def test_container_execute_command(self, skip_if_no_docker):
        """Test executing commands in container."""
        manager = get_container_manager()
        session_id = "test-session-execute"

        try:
            container = await manager.create_container(session_id, "python3.11")

            # Execute simple command
            exit_code, stdout, stderr = await container.execute("echo 'Hello World'")

            assert exit_code == 0
            assert "Hello World" in stdout
            assert stderr == ""
        finally:
            await manager.destroy_container(session_id)

    @pytest.mark.asyncio
    async def test_container_execute_python(self, skip_if_no_docker):
        """Test executing Python code in container."""
        manager = get_container_manager()
        session_id = "test-session-python"

        try:
            container = await manager.create_container(session_id, "python3.11")

            # Execute Python code
            exit_code, stdout, stderr = await container.execute(
                "python3 -c \"print('Python works!')\""
            )

            assert exit_code == 0
            assert "Python works!" in stdout
        finally:
            await manager.destroy_container(session_id)

    @pytest.mark.asyncio
    async def test_container_file_operations(self, skip_if_no_docker):
        """Test file read/write in container."""
        manager = get_container_manager()
        session_id = "test-session-files"

        try:
            container = await manager.create_container(session_id, "python3.11")

            # Write file
            test_content = "This is test content"
            success = container.write_file("/workspace/test.txt", test_content)
            assert success

            # Read file
            content = container.read_file("/workspace/test.txt")
            assert content == test_content
        finally:
            await manager.destroy_container(session_id)

    @pytest.mark.asyncio
    async def test_container_reset(self, skip_if_no_docker):
        """Test resetting container to clean state."""
        manager = get_container_manager()
        session_id = "test-session-reset"

        try:
            container = await manager.create_container(session_id, "python3.11")

            # Create some files
            container.write_file("/workspace/agent_workspace/test.txt", "data")
            container.write_file("/workspace/outputs/output.txt", "output")

            # Reset container
            success = await manager.reset_container(session_id)
            assert success

            # Files should be removed
            exit_code, stdout, _ = await container.execute("ls /workspace/agent_workspace/")
            assert "test.txt" not in stdout
        finally:
            await manager.destroy_container(session_id)

    @pytest.mark.asyncio
    async def test_destroy_container(self, skip_if_no_docker):
        """Test destroying a container."""
        manager = get_container_manager()
        session_id = "test-session-destroy"

        # Create container
        container = await manager.create_container(session_id, "python3.11")
        assert container.is_running

        # Destroy it
        success = await manager.destroy_container(session_id)
        assert success

        # Should no longer exist
        retrieved = await manager.get_container(session_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_orphaned_container_cleanup(self, skip_if_no_docker):
        """Test cleanup of orphaned containers with same name."""
        import docker

        manager = get_container_manager()
        session_id = "test-session-orphan"

        try:
            # Manually create a container with the expected name using Docker directly
            client = docker.from_env()
            container_name = f"opencodex-sandbox-{session_id}"

            orphan = client.containers.run(
                "python:3.11-slim",
                name=container_name,
                detach=True,
                command="sleep 60"
            )

            # Now try to create container through manager
            # Should detect and clean up orphan
            container = await manager.create_container(session_id, "python3.11")

            assert container is not None
            assert container.is_running

            # Verify old container was removed
            try:
                client.containers.get(orphan.id)
                # If we get here, orphan wasn't removed
                assert False, "Orphaned container was not cleaned up"
            except docker.errors.NotFound:
                # Expected - orphan was removed
                pass

        finally:
            await manager.destroy_container(session_id)
            # Extra cleanup in case test failed
            try:
                client = docker.from_env()
                container = client.containers.get(container_name)
                container.remove(force=True)
            except:
                pass

    @pytest.mark.asyncio
    async def test_multiple_containers(self, skip_if_no_docker):
        """Test managing multiple containers simultaneously."""
        manager = get_container_manager()
        sessions = ["session-1", "session-2", "session-3"]

        try:
            # Create multiple containers
            containers = []
            for session_id in sessions:
                container = await manager.create_container(session_id, "python3.11")
                containers.append(container)

            # Verify all are running
            for container in containers:
                assert container.is_running

            # Verify all are tracked
            for session_id in sessions:
                retrieved = await manager.get_container(session_id)
                assert retrieved is not None

        finally:
            # Cleanup all
            for session_id in sessions:
                await manager.destroy_container(session_id)

    @pytest.mark.asyncio
    async def test_container_resource_limits(self, skip_if_no_docker):
        """Test that containers have resource limits applied."""
        manager = get_container_manager()
        session_id = "test-session-limits"

        try:
            container = await manager.create_container(session_id, "python3.11")

            # Check container configuration (memory and CPU limits)
            import docker
            client = docker.from_env()
            docker_container = client.containers.get(container.container_id)

            # Verify memory limit (1GB = 1073741824 bytes)
            mem_limit = docker_container.attrs['HostConfig']['Memory']
            assert mem_limit == 1073741824

            # Verify CPU quota
            cpu_quota = docker_container.attrs['HostConfig']['CpuQuota']
            assert cpu_quota == 50000  # 50% of one core

        finally:
            await manager.destroy_container(session_id)

    @pytest.mark.asyncio
    async def test_container_workspace_mounting(self, skip_if_no_docker):
        """Test that workspace is properly mounted."""
        manager = get_container_manager()
        session_id = "test-session-mount"

        try:
            container = await manager.create_container(session_id, "python3.11")

            # Write file from host side
            # (workspace_path is host path)
            import os
            workspace_file = os.path.join(container.workspace_path, "host_file.txt")
            os.makedirs(container.workspace_path, exist_ok=True)

            with open(workspace_file, 'w') as f:
                f.write("Created from host")

            # Read from container
            exit_code, stdout, _ = await container.execute("cat /workspace/host_file.txt")

            assert exit_code == 0
            assert "Created from host" in stdout

        finally:
            await manager.destroy_container(session_id)

    @pytest.mark.asyncio
    async def test_container_stats(self, skip_if_no_docker):
        """Test getting container resource statistics."""
        manager = get_container_manager()
        session_id = "test-session-stats"

        try:
            container = await manager.create_container(session_id, "python3.11")

            stats = manager.get_container_stats(session_id)

            # Should return stats dict with resource usage
            assert stats is not None
            assert isinstance(stats, dict)

        finally:
            await manager.destroy_container(session_id)
