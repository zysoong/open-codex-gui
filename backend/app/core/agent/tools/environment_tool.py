"""Environment setup tool for agent."""

from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.agent.tools.base import Tool, ToolParameter, ToolResult
from app.core.sandbox.manager import ContainerPoolManager
from app.models.database import ChatSession


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
            "**Python:**\n"
            "- **python3.13**: Python 3.13 (RECOMMENDED - latest stable, includes numpy, pandas, matplotlib, scikit-learn)\n"
            "- **python3.12**: Python 3.12\n"
            "- **python3.11**: Python 3.11\n\n"
            "**JavaScript/TypeScript:**\n"
            "- **nodejs**: Node.js 22 with TypeScript, ESLint, Prettier\n\n"
            "**JVM Languages:**\n"
            "- **java**: Java 21 (OpenJDK) with Maven and Gradle\n"
            "- **kotlin**: Kotlin with Gradle\n"
            "- **scala**: Scala with sbt\n\n"
            "**Systems Languages:**\n"
            "- **go**: Go 1.23\n"
            "- **rust**: Rust 1.83 with Cargo\n"
            "- **cpp**: C++ with GCC 14, Clang, CMake, GDB\n\n"
            "**Scripting Languages:**\n"
            "- **ruby**: Ruby 3.3 with Bundler, RSpec\n"
            "- **php**: PHP 8.3 with Composer\n\n"
            "**.NET:**\n"
            "- **dotnet**: .NET 8 SDK (C#, F#)\n\n"
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
                    "Type of environment to set up. Options: "
                    "'python3.13' (recommended), 'python3.12', 'python3.11', "
                    "'nodejs', 'java', 'kotlin', 'scala', 'go', 'rust', 'cpp', "
                    "'ruby', 'php', 'dotnet'"
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
        self, environment_type: str, reason: str | None = None, **kwargs
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
            valid_types = [
                # Python
                "python3.13", "python3.12", "python3.11",
                # JavaScript/TypeScript
                "nodejs",
                # JVM languages
                "java", "kotlin", "scala",
                # Systems languages
                "go", "rust", "cpp",
                # Scripting languages
                "ruby", "php",
                # .NET
                "dotnet",
            ]
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
                .values(environment_type=environment_type, environment_config={})
            )
            await self._db.execute(update_stmt)
            await self._db.commit()

            # Create container (project volume is mounted automatically)
            container = await self._container_manager.create_container(
                self._session_id,
                session.project_id,  # Project volume mounted at /workspace/project_files
                environment_type,
                {},  # environment_config
            )

            # Build success message
            output_parts = [
                "✓ Sandbox environment set up successfully!",
                "",
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
