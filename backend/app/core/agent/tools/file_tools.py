"""File operation tools for agent."""

from typing import List, Type
from pydantic import BaseModel, Field, field_validator, ValidationError, ConfigDict
from app.core.agent.tools.base import Tool, ToolParameter, ToolResult
from app.core.sandbox.container import SandboxContainer
from app.core.sandbox.security import validate_file_path


# Pydantic schemas for parameter validation

class FileReadInput(BaseModel):
    """Input schema for file_read tool."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{
                "path": "/workspace/out/script.py"
            }, {
                "path": "/workspace/project_files/data.csv"
            }]
        }
    )

    path: str = Field(
        description="Full path to the file (e.g., '/workspace/project_files/data.csv' or '/workspace/out/script.py')"
    )

    @field_validator('path')
    @classmethod
    def validate_path(cls, v: str) -> str:
        if not v.startswith('/workspace/'):
            raise ValueError('Path must start with /workspace/')
        return v


class FileWriteInput(BaseModel):
    """Input schema for file_write tool."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{
                "filename": "script.py",
                "content": "print('Hello, World!')"
            }, {
                "filename": "config.json",
                "content": '{"key": "value"}'
            }]
        }
    )

    filename: str = Field(
        description="Filename to write (e.g., 'script.py', 'config.json'). Must be a simple filename without path separators."
    )
    content: str = Field(
        description="Content to write to the file"
    )

    @field_validator('filename')
    @classmethod
    def validate_filename(cls, v: str) -> str:
        if '/' in v or '\\' in v or v.startswith('.'):
            raise ValueError('Filename must be a simple filename without path separators or leading dots')
        return v


class FileReadTool(Tool):
    """Tool for reading files from the sandbox environment."""

    def __init__(self, container: SandboxContainer, model_name: str = ""):
        """Initialize FileReadTool with a sandbox container.

        Args:
            container: SandboxContainer instance for file operations
            model_name: Name of the LLM model (not used in tool, only for context)
        """
        self._container = container

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return (
            "Read and visualize any file from the sandbox environment.\n\n"
            "DISPLAYING IMAGES - THIS IS THE ONLY WAY:\n"
            "After saving any image/plot/chart (e.g., plt.savefig('plot.png')), you MUST use this tool to display it.\n"
            "NEVER embed base64 data in your text response - it won't render properly!\n"
            "CORRECT: Save to file → file_read('/workspace/out/plot.png') → Frontend displays automatically\n"
            "WRONG: Embedding ![image](data:image/png;base64,...) in text response\n\n"
            "FILE SUPPORT:\n"
            "• Text files → returns content WITH LINE NUMBERS\n"
            "• Images (PNG, JPG, SVG, etc.) → frontend displays automatically\n"
            "• Data files (CSV, JSON) → returns content for inspection\n\n"
            "PATHS: /workspace/project_files (user files) or /workspace/out (your files)\n"
            "NOTE: Line numbers in output are for edit_lines tool."
        )

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="path",
                type="string",
                description="Full path to the file (e.g., '/workspace/project_files/data.csv' or '/workspace/out/script.py')",
                required=True,
            ),
        ]

    @property
    def input_schema(self) -> Type[BaseModel]:
        """Pydantic schema for parameter validation."""
        return FileReadInput

    async def execute(self, path: str, **kwargs) -> ToolResult:
        """Read a file from the sandbox.

        Args:
            path: Path to the file to read

        Returns:
            ToolResult with file content (text or base64 data URI for binary files)
        """
        try:
            # Validate file path for security
            if not validate_file_path(path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid file path: {path}",
                    metadata={"path": path},
                )

            # Read file from container
            content = await self._container.read_file(path)

            if content is None:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File not found or cannot be read: {path}. The file may not exist, or there was an error extracting it from the container.",
                    metadata={"path": path},
                )

            # Check if it's a binary file (data URI)
            is_binary = content.startswith('data:')

            # For images, provide helpful metadata
            metadata = {
                "path": path,
                "size": len(content),
                "is_binary": is_binary,
            }

            # Add helpful message for images
            if is_binary and 'image/' in content[:50]:
                filename = path.split('/')[-1]
                # Extract MIME type and calculate size
                mime_type = content.split(';')[0].replace('data:', '')
                data_size_kb = len(content) // 1024

                # ALWAYS use short message for LLM to save tokens
                # Full image data is stored in metadata for frontend display
                # Note: VLM support would require special vision message format,
                # not base64 text in regular messages
                output_msg = (
                    f"Successfully read image file: {path} ({data_size_kb}KB, {mime_type})\n"
                    f"Image will be displayed to the user in the chat."
                )

                # Store full image data in metadata for frontend to display
                metadata["type"] = "image"
                metadata["image_data"] = content  # Full base64 data URI
                metadata["filename"] = filename
                metadata["mime_type"] = mime_type
            else:
                # Format text content with line numbers for easy reference
                # This is essential for using edit_lines tool
                lines = content.split('\n')
                formatted_lines = []
                for i, line in enumerate(lines, 1):
                    formatted_lines.append(f"{i:>4}: {line}")
                output_msg = '\n'.join(formatted_lines)
                metadata["line_count"] = len(lines)

            return ToolResult(
                success=True,
                output=output_msg,
                metadata=metadata,
            )

        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error=f"File not found: {path}",
                metadata={"path": path},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to read file: {str(e)}",
                metadata={"path": path},
            )


class FileWriteTool(Tool):
    """Tool for writing/creating files in the sandbox environment."""

    def __init__(self, container: SandboxContainer):
        """Initialize FileWriteTool with a sandbox container.

        Args:
            container: SandboxContainer instance for file operations
        """
        self._container = container

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return (
            "Write or create a file in the output directory (/workspace/out).\n\n"
            "USAGE:\n"
            "• Creating source files, configs, scripts\n"
            "• Saving outputs (data, images, plots)\n"
            "• Only specify filename, not full path - files go to /workspace/out\n\n"
            "AFTER SAVING IMAGES/PLOTS:\n"
            "You MUST call file_read('/workspace/out/filename.png') to display images!\n"
            "The frontend renders images from file_read results, NOT from text responses.\n"
            "NEVER put base64 image data in your text - it won't display properly.\n\n"
            "WARNING: This overwrites existing files completely.\n"
            "For targeted changes to existing files, use edit_lines instead."
        )

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="filename",
                type="string",
                description="Filename to write (e.g., 'script.py', 'config.json'). Must be a simple filename without path separators.",
                required=True,
            ),
            ToolParameter(
                name="content",
                type="string",
                description="Content to write to the file",
                required=True,
            ),
        ]

    @property
    def input_schema(self) -> Type[BaseModel]:
        """Pydantic schema for parameter validation."""
        return FileWriteInput

    async def execute(self, filename: str, content: str, **kwargs) -> ToolResult:
        """Write content to a file in the output directory.

        Args:
            filename: Filename to write (must be a simple filename)
            content: Content to write

        Returns:
            ToolResult with operation status
        """
        try:
            # Security: Only allow simple filenames, no path separators
            if '/' in filename or '\\' in filename or filename.startswith('.'):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid filename: {filename}. Only simple filenames are allowed (no path separators or leading dots).",
                    metadata={"filename": filename},
                )

            # Construct full path in output directory
            output_path = f"/workspace/out/{filename}"

            # Write file to container
            success = await self._container.write_file(output_path, content)

            if not success:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to write file to output directory: {filename}",
                    metadata={"filename": filename},
                )

            return ToolResult(
                success=True,
                output=f"Successfully wrote {len(content)} bytes to {filename} in /workspace/out",
                metadata={
                    "filename": filename,
                    "output_path": output_path,
                    "size": len(content),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to write file: {str(e)}",
                metadata={"filename": filename},
            )
