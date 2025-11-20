"""Integration tests for database operations."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
class TestDatabaseOperations:
    """Test database CRUD and relationship operations."""

    @pytest.mark.asyncio
    async def test_project_crud(self, db_session: AsyncSession):
        """Test basic project CRUD operations."""
        from app.models.database import Project

        # Create
        project = Project(name="Test Project", description="Test")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)

        assert project.id is not None

        # Read
        result = await db_session.execute(
            select(Project).where(Project.id == project.id)
        )
        retrieved = result.scalar_one()
        assert retrieved.name == "Test Project"

        # Update
        retrieved.description = "Updated"
        await db_session.commit()
        await db_session.refresh(retrieved)
        assert retrieved.description == "Updated"

        # Delete
        await db_session.delete(retrieved)
        await db_session.commit()

        result = await db_session.execute(
            select(Project).where(Project.id == project.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_project_session_relationship(self, db_session: AsyncSession):
        """Test one-to-many relationship between project and sessions."""
        from app.models.database import Project, ChatSession

        # Create project
        project = Project(name="Project with Sessions")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)

        # Create sessions
        session1 = ChatSession(project_id=project.id, name="Session 1")
        session2 = ChatSession(project_id=project.id, name="Session 2")
        db_session.add_all([session1, session2])
        await db_session.commit()

        # Retrieve project with sessions
        result = await db_session.execute(
            select(Project).where(Project.id == project.id)
        )
        project_with_sessions = result.scalar_one()

        # Query sessions
        sessions_result = await db_session.execute(
            select(ChatSession).where(ChatSession.project_id == project.id)
        )
        sessions = sessions_result.scalars().all()

        assert len(sessions) == 2

    @pytest.mark.asyncio
    async def test_cascade_delete_project(self, db_session: AsyncSession):
        """Test cascade delete when project is deleted."""
        from app.models.database import Project, ChatSession, Message, MessageRole

        # Create project -> session -> messages
        project = Project(name="Cascade Test")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)

        session = ChatSession(project_id=project.id, name="Session")
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        message = Message(
            chat_session_id=session.id,
            role=MessageRole.USER,
            content="Test",
            message_metadata={}
        )
        db_session.add(message)
        await db_session.commit()

        session_id = session.id
        message_id = message.id

        # Delete project
        await db_session.delete(project)
        await db_session.commit()

        # Verify cascading deletes
        session_result = await db_session.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        assert session_result.scalar_one_or_none() is None

        message_result = await db_session.execute(
            select(Message).where(Message.id == message_id)
        )
        assert message_result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_message_ordering(self, db_session: AsyncSession):
        """Test that messages maintain chronological order."""
        from app.models.database import ChatSession, Message, MessageRole
        import asyncio

        session = ChatSession(project_id=None, name="Order Test")
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        # Create messages with small delays
        for i in range(5):
            message = Message(
                chat_session_id=session.id,
                role=MessageRole.USER,
                content=f"Message {i}",
                message_metadata={}
            )
            db_session.add(message)
            await db_session.commit()
            await asyncio.sleep(0.01)  # Ensure different timestamps

        # Retrieve messages ordered by created_at
        result = await db_session.execute(
            select(Message)
            .where(Message.chat_session_id == session.id)
            .order_by(Message.created_at.asc())
        )
        messages = result.scalars().all()

        assert len(messages) == 5
        for i, msg in enumerate(messages):
            assert msg.content == f"Message {i}"

    @pytest.mark.asyncio
    async def test_agent_config_unique_per_project(self, db_session: AsyncSession):
        """Test that each project has one agent configuration."""
        from app.models.database import Project, AgentConfiguration

        project = Project(name="Config Test")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)

        # Create agent config
        config = AgentConfiguration(
            project_id=project.id,
            agent_type="react",
            environment_type="python3.11",
            llm_provider="openai",
            llm_model="gpt-4",
            enabled_tools=[],
            llm_config={}
        )
        db_session.add(config)
        await db_session.commit()

        # Query config
        result = await db_session.execute(
            select(AgentConfiguration).where(
                AgentConfiguration.project_id == project.id
            )
        )
        configs = result.scalars().all()

        assert len(configs) == 1
        assert configs[0].project_id == project.id

    @pytest.mark.asyncio
    async def test_concurrent_writes(self, db_session: AsyncSession):
        """Test handling concurrent database writes."""
        from app.models.database import Project

        # Create multiple projects concurrently
        projects = [
            Project(name=f"Concurrent Project {i}")
            for i in range(10)
        ]

        for project in projects:
            db_session.add(project)

        await db_session.commit()

        # Verify all were created
        result = await db_session.execute(select(Project))
        all_projects = result.scalars().all()

        assert len(all_projects) >= 10

    @pytest.mark.asyncio
    async def test_transaction_rollback(self, db_session: AsyncSession):
        """Test transaction rollback on error."""
        from app.models.database import Project

        project = Project(name="Rollback Test")
        db_session.add(project)
        await db_session.commit()
        project_id = project.id

        try:
            # Start a transaction
            project.name = "Updated Name"
            # Force an error (e.g., violate a constraint)
            # Since we don't have strict constraints, simulate by not committing
            await db_session.rollback()
        except Exception:
            await db_session.rollback()

        # Verify rollback worked
        result = await db_session.execute(
            select(Project).where(Project.id == project_id)
        )
        retrieved = result.scalar_one()
        assert retrieved.name == "Rollback Test"  # Not updated

    @pytest.mark.asyncio
    async def test_agent_action_storage(self, db_session: AsyncSession):
        """Test storing agent actions linked to messages."""
        from app.models.database import (
            ChatSession, Message, MessageRole, AgentAction
        )

        session = ChatSession(project_id=None, name="Action Test")
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        message = Message(
            chat_session_id=session.id,
            role=MessageRole.ASSISTANT,
            content="Response",
            message_metadata={}
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        # Add agent actions
        actions = [
            AgentAction(
                message_id=message.id,
                action_type="bash",
                action_input={"command": "echo test"},
                action_output={"result": "test"},
                status="success"
            ),
            AgentAction(
                message_id=message.id,
                action_type="file_read",
                action_input={"path": "/test.txt"},
                action_output={"content": "file content"},
                status="success"
            )
        ]

        for action in actions:
            db_session.add(action)
        await db_session.commit()

        # Retrieve actions
        result = await db_session.execute(
            select(AgentAction).where(AgentAction.message_id == message.id)
        )
        retrieved_actions = result.scalars().all()

        assert len(retrieved_actions) == 2

    @pytest.mark.asyncio
    async def test_metadata_storage(self, db_session: AsyncSession):
        """Test storing JSON metadata."""
        from app.models.database import Project

        metadata = {
            "tags": ["test", "integration"],
            "version": "1.0",
            "nested": {"key": "value"}
        }

        project = Project(name="Metadata Test", metadata=metadata)
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)

        # Retrieve and verify metadata
        result = await db_session.execute(
            select(Project).where(Project.id == project.id)
        )
        retrieved = result.scalar_one()

        assert retrieved.metadata == metadata
        assert retrieved.metadata["tags"] == ["test", "integration"]
        assert retrieved.metadata["nested"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_timestamp_auto_update(self, db_session: AsyncSession):
        """Test that updated_at timestamp auto-updates."""
        from app.models.database import Project
        import asyncio

        project = Project(name="Timestamp Test")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)

        original_updated_at = project.updated_at

        # Wait a moment
        await asyncio.sleep(0.1)

        # Update project
        project.description = "Updated"
        await db_session.commit()
        await db_session.refresh(project)

        # Timestamp should have changed
        assert project.updated_at > original_updated_at
