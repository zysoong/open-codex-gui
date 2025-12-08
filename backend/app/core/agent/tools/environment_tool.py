"""Environment setup tool for agent."""

import shutil
from pathlib import Path
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.agent.tools.base import Tool, ToolParameter, ToolResult
from app.core.sandbox.manager import ContainerPoolManager
from app.models.database import ChatSession
from app.core.storage.file_manager import get_file_manager


class SetupEnvironmentTool(Tool):
    """Tool for setting up a sandbox environment for code execution."""

    def __init__(self, db: AsyncSession, session_id: str, container_manager: ContainerPoolManager):
        """Initialize SetupEnvironmentTool.

        Args:
            db: Database session for updating ChatSession
            session_id: ID of the current chat session
            container_manager: Container manager for creating sandboxes
        """
        self._db = db
        self._session_id = session_id
        self._container_manager = container_manager

    @property
    def name(self) -> str:
        return "setup_environment"

    @property
    def description(self) -> str:
        return (
            "Set up a sandbox environment for code execution. **Call this FIRST** before using "
            "bash, file_read, file_write, edit, or search tools. "
            "Choose the appropriate environment based on the user's task:\n\n"
            "- **python3.11**: Python 3.11 (recommended for general purpose, data science, ML, web scraping)\n"
            "- **python3.12**: Python 3.12 (latest Python features, async improvements)\n"
            "- **python3.13**: Python 3.13 (experimental, bleeding edge)\n"
            "- **nodejs**: Node.js (JavaScript/TypeScript development, web apps, React/Vue/Angular)\n"
            "- **cpp**: C++ (systems programming, performance-critical code, compilation)\n\n"
            "Once the environment is set up, you can use file and bash tools to work in it. "
            "The sandbox is isolated and persistent for this chat session."
        )

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="environment_type",
                type="string",
                description=(
                    "Type of environment to set up. Must be one of: "
                    "'python3.11', 'python3.12', 'python3.13', 'nodejs', 'cpp'"
                ),
                required=True,
            ),
            ToolParameter(
                name="reason",
                type="string",
                description=(
                    "Brief explanation of why you chose this environment "
                    "(helps users understand your decision)"
                ),
                required=False,
            ),
        ]

    async def execute(
        self,
        environment_type: str,
        reason: str | None = None,
        **kwargs
    ) -> ToolResult:
        """Set up the sandbox environment.

        Args:
            environment_type: Type of environment (python3.11, nodejs, cpp, etc.)
            reason: Optional reason for choosing this environment

        Returns:
            ToolResult with setup status
        """
        try:
            # Validate environment type
            valid_types = ["python3.11", "python3.12", "python3.13", "nodejs", "cpp"]
            if environment_type not in valid_types:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid environment type: {environment_type}. Must be one of: {', '.join(valid_types)}",
                    metadata={"environment_type": environment_type},
                )

            # Check if environment is already set up
            query = select(ChatSession).where(ChatSession.id == self._session_id)
            result = await self._db.execute(query)
            session = result.scalar_one_or_none()

            if not session:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Chat session not found: {self._session_id}",
                    metadata={"session_id": self._session_id},
                )

            if session.environment_type:
                return ToolResult(
                    success=False,
                    output="",
                    error=(
                        f"Environment already set up as '{session.environment_type}'. "
                        "Cannot change environment for an existing session. "
                        "Create a new chat session for a different environment."
                    ),
                    metadata={
                        "current_environment": session.environment_type,
                        "requested_environment": environment_type,
                    },
                )

            # Update database with environment type
            update_stmt = (
                update(ChatSession)
                .where(ChatSession.id == self._session_id)
                .values(
                    environment_type=environment_type,
                    environment_config={}
                )
            )
            await self._db.execute(update_stmt)
            await self._db.commit()

            # Create container
            container = await self._container_manager.create_container(
                self._session_id,
                environment_type,
                {}  # environment_config
            )

            # Copy user-uploaded files to workspace/project_files
            file_manager = get_file_manager()
            project_files_src = Path(file_manager.base_path) / session.project_id
            project_files_dst = Path(container.workspace_path) / "project_files"

            if project_files_src.exists():
                # Copy all files from project directory to workspace/project_files
                for file in project_files_src.rglob("*"):
                    if file.is_file():
                        relative_path = file.relative_to(project_files_src)
                        dest_file = project_files_dst / relative_path
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file, dest_file)

            # Build success message
            output_parts = [
                f"✓ Sandbox environment set up successfully!",
                f"",
                f"Environment: {environment_type}",
                f"Container ID: {container.container.id[:12]}",
                f"Workspace: {container.workspace_path}",
            ]

            if reason:
                output_parts.insert(2, f"Reason: {reason}")

            return ToolResult(
                success=True,
                output="\n".join(output_parts),
                metadata={
                    "environment_type": environment_type,
                    "container_id": container.container.id,
                    "workspace_path": str(container.workspace_path),
                    "reason": reason,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to set up environment: {str(e)}",
                metadata={
                    "environment_type": environment_type,
                    "session_id": self._session_id,
                },
            )
