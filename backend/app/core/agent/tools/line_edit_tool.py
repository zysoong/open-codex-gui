"""Line-based file editing tool for precise edits using line numbers."""

import ast
from typing import List, Optional, Type
from pathlib import Path
from pydantic import BaseModel, Field, field_validator, ConfigDict

from app.core.agent.tools.base import Tool, ToolParameter, ToolResult
from app.core.sandbox.container import SandboxContainer


class LineEditInput(BaseModel):
    """Input schema for line-based editing with validation."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "command": "replace",
                    "path": "/workspace/out/main.py",
                    "start_line": 15,
                    "end_line": 17,
                    "new_content": "    return result",
                }
            ]
        }
    )

    command: str = Field(description="Action: 'replace', 'insert', or 'delete'")
    path: str = Field(description="File path to edit")
    start_line: Optional[int] = Field(
        default=None, description="Start line number (1-indexed). Required for replace/delete."
    )
    end_line: Optional[int] = Field(
        default=None, description="End line number (inclusive). Required for replace/delete."
    )
    insert_line: Optional[int] = Field(
        default=None, description="Line number after which to insert (0 = beginning). Required for insert."
    )
    new_content: Optional[str] = Field(
        default=None, description="New content to insert/replace. Required for replace/insert."
    )
    auto_indent: bool = Field(
        default=True, description="Automatically adjust indentation to match context."
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if not v.startswith("/workspace/"):
            raise ValueError("Path must start with /workspace/")
        if "/project_files" in v:
            raise ValueError("Cannot edit files in /workspace/project_files (read-only)")
        return v

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        valid_commands = {"replace", "insert", "delete"}
        if v.lower() not in valid_commands:
            raise ValueError(f"Command must be one of: {', '.join(valid_commands)}")
        return v.lower()

    @field_validator("start_line", "end_line", "insert_line")
    @classmethod
    def validate_line_numbers(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("Line numbers must be >= 0")
        return v


class LineEditTool(Tool):
    """Line-based file editing tool that handles indentation automatically.

    This tool addresses the common issue where LLMs struggle with exact
    whitespace matching in pattern-based edits. By using line numbers
    (visible in file_read output), the LLM can make precise edits without
    worrying about whitespace matching.

    Features:
    - Line-number based targeting (no whitespace matching issues)
    - Automatic indentation detection and application
    - Python syntax validation before committing changes
    """

    def __init__(self, container: SandboxContainer):
        """Initialize LineEditTool with a sandbox container.

        Args:
            container: SandboxContainer instance for file operations
        """
        self._container = container

    @property
    def name(self) -> str:
        return "edit_lines"

    @property
    def description(self) -> str:
        return (
            "Line-based file editing - use line numbers from file_read output.\n\n"
            "⚠️ MANDATORY: ALWAYS call file_read() FIRST before using this tool!\n"
            "You MUST see the current file content and line numbers before editing.\n"
            "Blind edits without reading the file first will cause errors.\n\n"
            "COMMANDS:\n"
            "- replace: Replace lines start_line to end_line (INCLUSIVE) with new_content\n"
            "- insert: Insert new_content after insert_line (0 = file start). MUST specify insert_line!\n"
            "- delete: Delete lines start_line to end_line (INCLUSIVE)\n\n"
            "CRITICAL - LINE RANGES ARE INCLUSIVE:\n"
            "- To edit ONLY line 7: use start_line=7, end_line=7 (SAME number!)\n"
            "- To edit lines 7-9: use start_line=7, end_line=9 (edits 7, 8, AND 9)\n"
            "- WRONG: start_line=7, end_line=8 to edit line 7 (this also removes line 8!)\n\n"
            "WORKFLOW:\n"
            "1. file_read('/workspace/out/file.py') → see line numbers\n"
            "2. Identify exact line(s) to change\n"
            "3. edit_lines(...) with correct line numbers\n"
            "4. If error persists, file_read() again to see updated line numbers!\n\n"
            "EXAMPLES:\n"
            "  Replace SINGLE line 15:\n"
            '    edit_lines(command="replace", path="/workspace/out/main.py",\n'
            '               start_line=15, end_line=15, new_content="    return result")\n\n'
            "  Insert after line 10 (MUST specify insert_line):\n"
            '    edit_lines(command="insert", path="/workspace/out/main.py",\n'
            '               insert_line=10, new_content="# New comment")'
        )

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="command",
                type="string",
                description="Action: 'replace', 'insert', or 'delete'",
                required=True,
            ),
            ToolParameter(
                name="path",
                type="string",
                description="File path to edit (e.g., '/workspace/out/main.py')",
                required=True,
            ),
            ToolParameter(
                name="start_line",
                type="integer",
                description="Start line number (1-indexed). Required for replace/delete.",
                required=False,
            ),
            ToolParameter(
                name="end_line",
                type="integer",
                description="End line number (inclusive). Required for replace/delete.",
                required=False,
            ),
            ToolParameter(
                name="insert_line",
                type="integer",
                description="Line number after which to insert (0 = beginning). Required for insert.",
                required=False,
            ),
            ToolParameter(
                name="new_content",
                type="string",
                description="New content to insert/replace. Required for replace/insert.",
                required=False,
            ),
            ToolParameter(
                name="auto_indent",
                type="boolean",
                description="Automatically adjust indentation to match context. Default: true",
                required=False,
                default=True,
            ),
        ]

    @property
    def input_schema(self) -> Type[BaseModel]:
        return LineEditInput

    async def execute(
        self,
        command: str,
        path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        insert_line: Optional[int] = None,
        new_content: Optional[str] = None,
        auto_indent: bool = True,
        **kwargs,
    ) -> ToolResult:
        """Execute line-based edit command.

        Args:
            command: 'replace', 'insert', or 'delete'
            path: File path to edit
            start_line: Start line number (1-indexed) for replace/delete
            end_line: End line number (inclusive) for replace/delete
            insert_line: Line after which to insert (0 = beginning)
            new_content: Content to insert/replace
            auto_indent: Whether to auto-adjust indentation

        Returns:
            ToolResult with success/error status
        """
        try:
            # 1. Read current file content
            content = await self._container.read_file(path)

            if content is None:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to read file '{path}': File not found or cannot be read.",
                    metadata={"path": path},
                )

            lines = content.split("\n")
            total_lines = len(lines)

            # 2. Validate and execute command
            old_content_lines = []
            new_content_lines = []

            if command == "replace":
                result = self._validate_replace_params(start_line, end_line, new_content, total_lines)
                if result:
                    return result

                # Capture old content before replacement
                old_content_lines = lines[start_line - 1:end_line]

                # Apply auto-indent if enabled
                if auto_indent and new_content:
                    new_content = self._apply_auto_indent(new_content, lines, start_line)

                new_content_lines = new_content.split("\n") if new_content else []
                new_lines = self._replace_lines(lines, start_line, end_line, new_content)
                action_desc = f"Replaced lines {start_line}-{end_line}"

            elif command == "insert":
                result = self._validate_insert_params(insert_line, new_content, total_lines)
                if result:
                    return result

                # Apply auto-indent if enabled
                if auto_indent and new_content:
                    target_line = insert_line + 1 if insert_line < total_lines else insert_line
                    new_content = self._apply_auto_indent(new_content, lines, target_line)

                new_content_lines = new_content.split("\n") if new_content else []
                new_lines = self._insert_lines(lines, insert_line, new_content)
                action_desc = f"Inserted after line {insert_line}"

            elif command == "delete":
                result = self._validate_delete_params(start_line, end_line, total_lines)
                if result:
                    return result

                # Capture content being deleted
                old_content_lines = lines[start_line - 1:end_line]
                new_lines = self._delete_lines(lines, start_line, end_line)
                action_desc = f"Deleted lines {start_line}-{end_line}"

            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown command: {command}. Use 'replace', 'insert', or 'delete'.",
                    metadata={"command": command},
                )

            # 3. Validate Python syntax before writing
            new_content_str = "\n".join(new_lines)
            syntax_error = self._validate_python_syntax(new_content_str, path)
            if syntax_error:
                return ToolResult(
                    success=False,
                    output="",
                    error=syntax_error,
                    metadata={"path": path, "validation_failed": True},
                )

            # 4. Write the file
            write_result = await self._write_file(path, new_content_str)
            if not write_result.success:
                return write_result

            # 5. Build detailed output
            output_parts = [
                f"Successfully edited {path}",
                f"{action_desc}",
                f"File now has {len(new_lines)} lines.",
                "",
            ]

            # Show what was removed (for replace and delete)
            if old_content_lines:
                output_parts.append("--- Removed:")
                for i, line in enumerate(old_content_lines):
                    line_num = (start_line or 1) + i
                    output_parts.append(f"  {line_num:>4}: {line}")

            # Show what was added (for replace and insert)
            if new_content_lines:
                output_parts.append("+++ Added:")
                # Calculate the starting line number for new content
                if command == "replace":
                    new_start = start_line
                elif command == "insert":
                    new_start = insert_line + 1
                else:
                    new_start = 1
                for i, line in enumerate(new_content_lines):
                    line_num = new_start + i
                    output_parts.append(f"  {line_num:>4}: {line}")

            # Add warning if line counts differ significantly (helps catch mistakes)
            if command == "replace" and old_content_lines and new_content_lines:
                removed_count = len(old_content_lines)
                added_count = len(new_content_lines)
                if removed_count != added_count:
                    output_parts.append("")
                    output_parts.append(f"NOTE: Removed {removed_count} line(s), added {added_count} line(s).")
                    if removed_count > added_count:
                        output_parts.append("      If unintended, you may have specified too large a line range.")

            return ToolResult(
                success=True,
                output="\n".join(output_parts),
                metadata={
                    "path": path,
                    "command": command,
                    "lines_before": total_lines,
                    "lines_after": len(new_lines),
                    "old_content": old_content_lines,
                    "new_content": new_content_lines,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Edit failed: {str(e)}",
                metadata={"path": path, "command": command},
            )

    def _validate_replace_params(
        self,
        start_line: Optional[int],
        end_line: Optional[int],
        new_content: Optional[str],
        total_lines: int,
    ) -> Optional[ToolResult]:
        """Validate parameters for replace command."""
        if start_line is None or end_line is None:
            return ToolResult(
                success=False,
                output="",
                error="Replace command requires both start_line and end_line parameters.",
            )
        if new_content is None:
            return ToolResult(
                success=False,
                output="",
                error="Replace command requires new_content parameter.",
            )
        if start_line < 1:
            return ToolResult(
                success=False,
                output="",
                error=f"start_line must be >= 1, got {start_line}",
            )
        if end_line < start_line:
            return ToolResult(
                success=False,
                output="",
                error=f"end_line ({end_line}) must be >= start_line ({start_line})",
            )
        if start_line > total_lines:
            return ToolResult(
                success=False,
                output="",
                error=f"start_line ({start_line}) exceeds file length ({total_lines} lines)",
            )
        return None

    def _validate_insert_params(
        self,
        insert_line: Optional[int],
        new_content: Optional[str],
        total_lines: int,
    ) -> Optional[ToolResult]:
        """Validate parameters for insert command."""
        if insert_line is None:
            return ToolResult(
                success=False,
                output="",
                error=(
                    "Insert command requires insert_line parameter.\n"
                    "Use file_read() first to see line numbers, then specify insert_line.\n"
                    "Example: insert_line=10 to insert after line 10, insert_line=0 for file start."
                ),
            )
        if new_content is None:
            return ToolResult(
                success=False,
                output="",
                error="Insert command requires new_content parameter.",
            )
        if insert_line < 0:
            return ToolResult(
                success=False,
                output="",
                error=f"insert_line must be >= 0, got {insert_line}",
            )
        if insert_line > total_lines:
            return ToolResult(
                success=False,
                output="",
                error=f"insert_line ({insert_line}) exceeds file length ({total_lines} lines). Use {total_lines} to append.",
            )
        return None

    def _validate_delete_params(
        self,
        start_line: Optional[int],
        end_line: Optional[int],
        total_lines: int,
    ) -> Optional[ToolResult]:
        """Validate parameters for delete command."""
        if start_line is None or end_line is None:
            return ToolResult(
                success=False,
                output="",
                error="Delete command requires both start_line and end_line parameters.",
            )
        if start_line < 1:
            return ToolResult(
                success=False,
                output="",
                error=f"start_line must be >= 1, got {start_line}",
            )
        if end_line < start_line:
            return ToolResult(
                success=False,
                output="",
                error=f"end_line ({end_line}) must be >= start_line ({start_line})",
            )
        if start_line > total_lines:
            return ToolResult(
                success=False,
                output="",
                error=f"start_line ({start_line}) exceeds file length ({total_lines} lines)",
            )
        return None

    def _replace_lines(
        self, lines: List[str], start: int, end: int, new_content: str
    ) -> List[str]:
        """Replace lines[start-1:end] with new_content.

        Args:
            lines: Original file lines
            start: Start line (1-indexed)
            end: End line (1-indexed, inclusive)
            new_content: Content to replace with

        Returns:
            New list of lines
        """
        new_lines = new_content.split("\n") if new_content else []
        # Convert to 0-indexed: lines[start-1:end] covers lines start to end inclusive
        return lines[: start - 1] + new_lines + lines[end:]

    def _insert_lines(self, lines: List[str], after: int, new_content: str) -> List[str]:
        """Insert new_content after the specified line.

        Args:
            lines: Original file lines
            after: Line number after which to insert (0 = beginning)
            new_content: Content to insert

        Returns:
            New list of lines
        """
        new_lines = new_content.split("\n") if new_content else []
        return lines[:after] + new_lines + lines[after:]

    def _delete_lines(self, lines: List[str], start: int, end: int) -> List[str]:
        """Delete lines from start to end (inclusive).

        Args:
            lines: Original file lines
            start: Start line (1-indexed)
            end: End line (1-indexed, inclusive)

        Returns:
            New list of lines
        """
        return lines[: start - 1] + lines[end:]

    def _apply_auto_indent(
        self, new_content: str, context_lines: List[str], target_line: int
    ) -> str:
        """Apply automatic indentation to new content based on context.

        This implements a "middle-out" approach inspired by RooCode:
        1. Detect the target indentation from surrounding context
        2. Detect the base indentation of the new content
        3. Re-indent each line to match the target context

        Args:
            new_content: The new content to indent
            context_lines: The original file lines for context
            target_line: The line number where content will be placed (1-indexed)

        Returns:
            The re-indented content
        """
        if not new_content.strip():
            return new_content

        # Find target indentation from context
        target_indent = self._detect_context_indent(context_lines, target_line)

        # Detect base indentation of new content
        new_lines = new_content.split("\n")
        base_indent = self._detect_base_indent(new_lines)

        # Re-indent each line
        result = []
        for line in new_lines:
            if not line.strip():  # Empty or whitespace-only
                result.append("")
            else:
                line_indent = len(line) - len(line.lstrip())
                relative_indent = line_indent - base_indent
                new_indent = max(0, target_indent + relative_indent)
                result.append(" " * new_indent + line.lstrip())

        return "\n".join(result)

    def _detect_context_indent(self, lines: List[str], target_line: int) -> int:
        """Detect appropriate indentation level from surrounding context.

        Args:
            lines: The file lines
            target_line: The target line number (1-indexed)

        Returns:
            The detected indentation level (number of spaces)
        """
        # Convert to 0-indexed
        target_idx = target_line - 1

        # Look at surrounding lines for context (prefer line before)
        for offset in [-1, 0, 1, -2, 2]:
            idx = target_idx + offset
            if 0 <= idx < len(lines):
                line = lines[idx]
                if line.strip():  # Non-empty line
                    indent = len(line) - len(line.lstrip())

                    # If the previous line ends with ':', the next line should be indented more
                    if offset < 0 and line.rstrip().endswith(":"):
                        return indent + 4  # Standard Python indent

                    return indent

        return 0  # Default to no indent

    def _detect_base_indent(self, lines: List[str]) -> int:
        """Detect the minimum indentation in the new content (base level).

        Args:
            lines: The lines of new content

        Returns:
            The minimum indentation level found
        """
        min_indent = float("inf")

        for line in lines:
            if line.strip():  # Non-empty line
                indent = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent)

        return 0 if min_indent == float("inf") else int(min_indent)

    def _validate_python_syntax(self, content: str, path: str) -> Optional[str]:
        """Validate Python syntax before writing.

        Args:
            content: The file content to validate
            path: The file path (used to check if it's a Python file)

        Returns:
            None if valid, or error message string if invalid
        """
        if not path.endswith(".py"):
            return None  # Skip non-Python files

        try:
            ast.parse(content)
            return None
        except SyntaxError as e:
            error_line = e.text.rstrip() if e.text else ""
            pointer = " " * ((e.offset or 1) - 1) + "^" if e.offset else ""

            return (
                f"Edit would create syntax error at line {e.lineno}:\n"
                f"  {error_line}\n"
                f"  {pointer}\n"
                f"Error: {e.msg}\n\n"
                f"Edit NOT applied. Please fix the syntax and try again."
            )

    async def _write_file(self, path: str, content: str) -> ToolResult:
        """Write content to file.

        Args:
            path: File path
            content: Content to write

        Returns:
            ToolResult indicating success or failure
        """
        try:
            # Use container's write_file method (same as FileWriteTool)
            success = await self._container.write_file(path, content)

            if not success:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to write file: {path}",
                    metadata={"path": path},
                )

            return ToolResult(success=True, output="", metadata={"path": path})

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Write failed: {str(e)}",
                metadata={"path": path},
            )
