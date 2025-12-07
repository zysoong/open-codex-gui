"""Smart code editing tool - AST-aware for code, text-based for config files."""

from typing import List, Dict, Any, Optional
from pathlib import Path
import json
from app.core.agent.tools.base import Tool, ToolParameter, ToolResult
from app.core.sandbox.container import SandboxContainer


# File extensions that support AST editing
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".rb", ".swift", ".kt"
}

# Non-code files that need text-based editing
TEXT_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".toml", ".xml", ".html", ".css",
    ".md", ".txt", ".env", ".ini", ".cfg", ".conf", ".gitignore",
    ".dockerignore", ".editorconfig"
}


# Common refactoring patterns with their rewrites
REFACTORING_SHORTCUTS: Dict[str, Dict[str, Dict[str, str]]] = {
    "rename_function": {
        "description": "Rename function definitions and calls",
        "python": {"pattern": "def $OLD($$$ARGS)", "rewrite": "def $NEW($$$ARGS)"},
        "javascript": {"pattern": "function $OLD($$$ARGS)", "rewrite": "function $NEW($$$ARGS)"},
        "typescript": {"pattern": "function $OLD($$$ARGS)", "rewrite": "function $NEW($$$ARGS)"},
        "go": {"pattern": "func $OLD($$$ARGS)", "rewrite": "func $NEW($$$ARGS)"},
        "rust": {"pattern": "fn $OLD($$$ARGS)", "rewrite": "fn $NEW($$$ARGS)"},
    },
    "rename_class": {
        "description": "Rename class definitions",
        "python": {"pattern": "class $OLD", "rewrite": "class $NEW"},
        "javascript": {"pattern": "class $OLD", "rewrite": "class $NEW"},
        "typescript": {"pattern": "class $OLD", "rewrite": "class $NEW"},
        "java": {"pattern": "class $OLD", "rewrite": "class $NEW"},
    },
    "add_type_hint": {
        "description": "Add type hints to function parameters (Python)",
        "python": {"pattern": "def $NAME($PARAM)", "rewrite": "def $NAME($PARAM: $TYPE)"},
    },
    "convert_print_to_log": {
        "description": "Convert print statements to logging",
        "python": {"pattern": "print($$$ARGS)", "rewrite": "logger.info($$$ARGS)"},
        "javascript": {"pattern": "console.log($$$ARGS)", "rewrite": "logger.info($$$ARGS)"},
    },
    "add_error_handling": {
        "description": "Wrap async calls with error handling",
        "javascript": {"pattern": "await $CALL", "rewrite": "await $CALL.catch(handleError)"},
        "typescript": {"pattern": "await $CALL", "rewrite": "await $CALL.catch(handleError)"},
    },
    "convert_var_to_const": {
        "description": "Convert var declarations to const",
        "javascript": {"pattern": "var $NAME = $VALUE", "rewrite": "const $NAME = $VALUE"},
    },
    "convert_function_to_arrow": {
        "description": "Convert function expressions to arrow functions",
        "javascript": {"pattern": "function($$$ARGS) { $$$BODY }", "rewrite": "($$$ARGS) => { $$$BODY }"},
        "typescript": {"pattern": "function($$$ARGS) { $$$BODY }", "rewrite": "($$$ARGS) => { $$$BODY }"},
    },
}

# Language aliases
LANGUAGE_ALIASES: Dict[str, str] = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "jsx": "javascript",
    "rs": "rust",
    "c++": "cpp",
}


class AstEditTool(Tool):
    """Tool for AST-aware code refactoring using ast-grep."""

    def __init__(self, container: SandboxContainer):
        """Initialize AstEditTool with a sandbox container.

        Args:
            container: SandboxContainer instance for command execution
        """
        self._container = container

    @property
    def name(self) -> str:
        return "edit"

    @property
    def description(self) -> str:
        return (
            "Edit files by finding and replacing text or code patterns.\n\n"
            "TWO MODES (auto-detected):\n\n"
            "1. SIMPLE MODE (no $ in pattern) - Use for most edits:\n"
            "   pattern: exact text to find (copy from file)\n"
            "   rewrite: replacement text\n"
            "   Example: pattern='def old_name(' rewrite='def new_name('\n\n"
            "2. AST MODE (pattern contains $) - For bulk refactoring:\n"
            "   pattern: AST pattern with $VAR metavariables\n"
            "   rewrite: replacement with same metavariables\n"
            "   Example: pattern='print($$$ARGS)' rewrite='logger.info($$$ARGS)'\n\n"
            "TIPS:\n"
            "- For simple edits: copy EXACT text from file (whitespace matters in simple mode)\n"
            "- For refactoring: use $ for single match, $$$ for multiple\n"
            "- Use dry_run=true to preview changes first"
        )

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="pattern",
                type="string",
                description=(
                    "Text or code to find. "
                    "For simple edits: exact text to match (copy from file). "
                    "For refactoring: use $VAR for identifiers, $$$ for multiple items."
                ),
                required=True,
            ),
            ToolParameter(
                name="rewrite",
                type="string",
                description=(
                    "Replacement text. For AST patterns, use same $VAR names from pattern."
                ),
                required=True,
            ),
            ToolParameter(
                name="path",
                type="string",
                description=(
                    "File or directory path. For single file: '/workspace/out/app.py'. "
                    "For multi-file refactoring: '/workspace/agent_workspace' or '/workspace/out'"
                ),
                required=True,
            ),
            ToolParameter(
                name="language",
                type="string",
                description=(
                    "Programming language. Required for directory refactoring, optional for single files. "
                    "Options: python, javascript, typescript, go, rust, java, c, cpp"
                ),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="file_pattern",
                type="string",
                description=(
                    "Glob pattern to filter files in directory mode. "
                    "Examples: '*.py', '**/*.js', 'src/**/*.ts'. Default: all files of the language."
                ),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="dry_run",
                type="boolean",
                description=(
                    "If true, show what would be changed without modifying files. "
                    "Useful for previewing refactoring before applying. Default: false"
                ),
                required=False,
                default=False,
            ),
        ]

    def _is_code_file(self, path: str) -> bool:
        """Check if file is a code file that supports AST editing."""
        ext = Path(path).suffix.lower()
        return ext in CODE_EXTENSIONS

    def _is_text_file(self, path: str) -> bool:
        """Check if file is a non-code text file."""
        ext = Path(path).suffix.lower()
        return ext in TEXT_EXTENSIONS or ext not in CODE_EXTENSIONS

    def _is_ast_pattern(self, pattern: str) -> bool:
        """Check if pattern contains AST metavariables ($NAME or $$$).

        If pattern contains $ followed by letters/underscore, it's an AST pattern.
        Regular $ in strings (like '$100') won't match this.
        """
        import re
        # Match $IDENTIFIER or $$$IDENTIFIER patterns
        return bool(re.search(r'\$[A-Z_]', pattern))

    def _normalize_language(self, language: Optional[str]) -> Optional[str]:
        """Normalize language name for ast-grep."""
        if not language:
            return None
        lang = language.lower()
        return LANGUAGE_ALIASES.get(lang, lang)

    def _detect_language_from_file(self, path: str) -> Optional[str]:
        """Detect language from file extension."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".cc": "cpp",
            ".rb": "ruby",
            ".swift": "swift",
            ".kt": "kotlin",
        }
        ext = Path(path).suffix.lower()
        return ext_map.get(ext)

    async def _text_based_edit(
        self,
        file_path: Path,
        pattern: str,
        replacement: str,
        dry_run: bool
    ) -> ToolResult:
        """Fallback text-based editing for non-code files.

        Args:
            file_path: Path to the file
            pattern: Text pattern to find
            replacement: Text to replace with
            dry_run: Preview changes without applying

        Returns:
            ToolResult with edit results
        """
        try:
            # Read current file content
            exit_code, content, stderr = await self._container.execute(
                f"cat '{file_path}'",
                workdir="/workspace",
                timeout=30
            )

            if exit_code != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to read file: {stderr}",
                    metadata={"file": str(file_path)},
                )

            # Check if pattern exists
            if pattern not in content:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Pattern not found in file: {file_path}\nPattern: {pattern[:100]}...",
                    metadata={"file": str(file_path), "pattern": pattern},
                )

            # Count occurrences
            count = content.count(pattern)

            if dry_run:
                return ToolResult(
                    success=True,
                    output=f"Dry run: Would replace {count} occurrence(s) of pattern in {file_path}\n"
                           f"Pattern: {pattern[:100]}{'...' if len(pattern) > 100 else ''}\n"
                           f"Replace with: {replacement[:100]}{'...' if len(replacement) > 100 else ''}",
                    metadata={
                        "dry_run": True,
                        "file": str(file_path),
                        "occurrences": count,
                    },
                )

            # Perform replacement
            new_content = content.replace(pattern, replacement)

            # Write back using heredoc to handle special characters
            # Escape any single quotes in the content
            escaped_content = new_content.replace("'", "'\\''")
            write_cmd = f"printf '%s' '{escaped_content}' > '{file_path}'"

            exit_code, _, stderr = await self._container.execute(
                write_cmd,
                workdir="/workspace",
                timeout=30
            )

            if exit_code != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to write file: {stderr}",
                    metadata={"file": str(file_path)},
                )

            return ToolResult(
                success=True,
                output=f"Successfully edited {file_path}\n"
                       f"Replaced {count} occurrence(s) of pattern.\n"
                       f"(Used text-based editing for non-code file)",
                metadata={
                    "file": str(file_path),
                    "occurrences": count,
                    "method": "text-based",
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Text-based edit failed: {str(e)}",
                metadata={"file": str(file_path)},
            )

    async def execute(
        self,
        pattern: str,
        rewrite: str,
        path: str,
        language: Optional[str] = None,
        file_pattern: Optional[str] = None,
        dry_run: bool = False,
        **kwargs
    ) -> ToolResult:
        """Execute AST-aware code refactoring.

        Args:
            pattern: AST pattern to match
            rewrite: Replacement pattern
            path: File or directory to refactor
            language: Programming language
            file_pattern: Glob pattern to filter files
            dry_run: Preview changes without applying

        Returns:
            ToolResult with refactoring results
        """
        try:
            # Resolve path
            target_path = Path(path)
            if not target_path.is_absolute():
                target_path = Path("/workspace") / path

            # Validate path exists
            exit_code, stdout, _ = await self._container.execute(
                f"test -e {target_path} && echo 'exists'",
                workdir="/workspace",
                timeout=5
            )
            if exit_code != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path not found: {target_path}",
                    metadata={"path": str(target_path)},
                )

            # Check if it's a file or directory
            exit_code, stdout, _ = await self._container.execute(
                f"test -d {target_path} && echo 'dir' || echo 'file'",
                workdir="/workspace",
                timeout=5
            )
            is_directory = stdout.strip() == "dir"

            # Determine if we should use AST mode or simple text mode
            use_ast_mode = self._is_ast_pattern(pattern)

            # For single files: use text mode if not an AST pattern OR if not a code file
            if not is_directory:
                if not use_ast_mode or not self._is_code_file(str(target_path)):
                    # Use simple text-based editing
                    return await self._text_based_edit(target_path, pattern, rewrite, dry_run)

            # For directories: if not AST pattern, we can't do simple text mode across dirs
            if is_directory and not use_ast_mode:
                return ToolResult(
                    success=False,
                    output="",
                    error=(
                        "Directory-wide editing requires AST patterns (use $VAR metavariables). "
                        "For simple text replacement, specify a single file path instead."
                    ),
                    metadata={"path": str(target_path)},
                )

            # Check if ast-grep is available for AST mode
            exit_code, _, _ = await self._container.execute(
                "which ast-grep",
                workdir="/workspace",
                timeout=5
            )
            if exit_code != 0:
                # Fallback to text-based editing if ast-grep not available
                return await self._text_based_edit(target_path, pattern, rewrite, dry_run)

            # Normalize language
            norm_language = self._normalize_language(language)

            # Auto-detect language for single files
            if not norm_language and not is_directory:
                norm_language = self._detect_language_from_file(str(target_path))

            # For directories, language is required
            if is_directory and not norm_language:
                return ToolResult(
                    success=False,
                    output="",
                    error="Language parameter is required for directory refactoring. Specify --language.",
                    metadata={"path": str(target_path)},
                )

            # Build the refactoring command
            if is_directory:
                result = await self._refactor_directory(
                    target_path, pattern, rewrite, norm_language, file_pattern, dry_run
                )
            else:
                result = await self._refactor_file(
                    target_path, pattern, rewrite, norm_language, dry_run
                )

            return result

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"AST refactoring failed: {str(e)}",
                metadata={"pattern": pattern, "rewrite": rewrite, "path": path},
            )

    async def _refactor_file(
        self,
        file_path: Path,
        pattern: str,
        rewrite: str,
        language: Optional[str],
        dry_run: bool
    ) -> ToolResult:
        """Refactor a single file."""
        # Escape pattern and rewrite for shell
        safe_pattern = pattern.replace("'", "'\\''")
        safe_rewrite = rewrite.replace("'", "'\\''")

        # Build command: ast-grep run -p 'PATTERN' -r 'REWRITE' -l LANG [--json|-U] FILE
        cmd_parts = ["ast-grep", "run", "-p", f"'{safe_pattern}'", "-r", f"'{safe_rewrite}'"]

        if language:
            cmd_parts.extend(["-l", language])

        # For dry run, use --json to preview changes
        # For actual run, use -U (--update-all) to auto-apply without confirmation
        if dry_run:
            cmd_parts.append("--json")
        else:
            cmd_parts.append("-U")

        cmd_parts.append(str(file_path))

        cmd = " ".join(cmd_parts)

        # Execute
        exit_code, stdout, stderr = await self._container.execute(
            cmd,
            workdir="/workspace",
            timeout=60
        )

        if dry_run:
            return self._format_dry_run_result(stdout, pattern, rewrite, str(file_path))

        # Check for errors
        if exit_code != 0 and "no matches" not in stderr.lower():
            return ToolResult(
                success=False,
                output="",
                error=f"Refactoring failed: {stderr}",
                metadata={"file": str(file_path), "pattern": pattern},
            )

        # Parse result - sg outputs the modified content or shows changes
        if not stdout.strip() and exit_code == 0:
            return ToolResult(
                success=True,
                output=f"No matches found for pattern '{pattern}' in {file_path}",
                metadata={
                    "file": str(file_path),
                    "pattern": pattern,
                    "matches": 0,
                },
            )

        # Count changes (approximate from output)
        lines_changed = len([l for l in stdout.split('\n') if l.strip()])

        return ToolResult(
            success=True,
            output=f"Successfully refactored {file_path}\nPattern: {pattern}\nRewrite: {rewrite}\n\nChanges applied.",
            metadata={
                "file": str(file_path),
                "pattern": pattern,
                "rewrite": rewrite,
                "changes": lines_changed,
            },
        )

    async def _refactor_directory(
        self,
        dir_path: Path,
        pattern: str,
        rewrite: str,
        language: str,
        file_pattern: Optional[str],
        dry_run: bool
    ) -> ToolResult:
        """Refactor multiple files in a directory."""
        # Escape pattern and rewrite for shell
        safe_pattern = pattern.replace("'", "'\\''")
        safe_rewrite = rewrite.replace("'", "'\\''")

        # First, find matching files
        if file_pattern:
            find_cmd = f"find {dir_path} -type f -name '{file_pattern}'"
        else:
            # Use language-specific extensions
            ext_map = {
                "python": "*.py",
                "javascript": "*.js",
                "typescript": "*.ts",
                "go": "*.go",
                "rust": "*.rs",
                "java": "*.java",
                "c": "*.c",
                "cpp": "*.cpp",
            }
            ext = ext_map.get(language, "*")
            find_cmd = f"find {dir_path} -type f -name '{ext}'"

        # Get list of files
        exit_code, file_list, _ = await self._container.execute(
            find_cmd,
            workdir="/workspace",
            timeout=30
        )

        files = [f.strip() for f in file_list.strip().split('\n') if f.strip()]

        if not files:
            return ToolResult(
                success=True,
                output=f"No matching files found in {dir_path}",
                metadata={"directory": str(dir_path), "pattern": pattern},
            )

        # Build command for directory-wide refactoring using short flags
        cmd_parts = [
            "ast-grep", "run",
            "-p", f"'{safe_pattern}'",
            "-r", f"'{safe_rewrite}'",
            "-l", language,
        ]

        if dry_run:
            cmd_parts.append("--json")
        else:
            cmd_parts.append("-U")  # Auto-apply changes

        cmd_parts.append(str(dir_path))

        cmd = " ".join(cmd_parts)

        # Execute
        exit_code, stdout, stderr = await self._container.execute(
            cmd,
            workdir="/workspace",
            timeout=120  # Longer timeout for multi-file
        )

        if dry_run:
            return self._format_dry_run_result(stdout, pattern, rewrite, str(dir_path), len(files))

        # Check for errors
        if exit_code != 0 and "no matches" not in stderr.lower() and stdout.strip() == "":
            return ToolResult(
                success=False,
                output="",
                error=f"Refactoring failed: {stderr}",
                metadata={"directory": str(dir_path), "pattern": pattern},
            )

        # Success
        return ToolResult(
            success=True,
            output=(
                f"Successfully refactored files in {dir_path}\n"
                f"Pattern: {pattern}\n"
                f"Rewrite: {rewrite}\n"
                f"Language: {language}\n"
                f"Files scanned: {len(files)}\n\n"
                f"Changes have been applied."
            ),
            metadata={
                "directory": str(dir_path),
                "pattern": pattern,
                "rewrite": rewrite,
                "language": language,
                "files_scanned": len(files),
            },
        )

    def _format_dry_run_result(
        self,
        stdout: str,
        pattern: str,
        rewrite: str,
        path: str,
        total_files: int = 1
    ) -> ToolResult:
        """Format dry-run results showing what would change."""
        if not stdout.strip():
            return ToolResult(
                success=True,
                output=f"Dry run: No matches found for pattern '{pattern}' in {path}",
                metadata={
                    "dry_run": True,
                    "pattern": pattern,
                    "matches": 0,
                },
            )

        # Parse JSON output
        changes = []
        try:
            for line in stdout.strip().split('\n'):
                if line.strip():
                    try:
                        result = json.loads(line)
                        changes.append({
                            "file": result.get("file", ""),
                            "line": result.get("range", {}).get("start", {}).get("line", 0),
                            "original": result.get("text", ""),
                            "replacement": result.get("replacement", rewrite),
                        })
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

        if not changes:
            return ToolResult(
                success=True,
                output=f"Dry run: No matches found for pattern '{pattern}'",
                metadata={"dry_run": True, "pattern": pattern, "matches": 0},
            )

        # Format output
        output = f"Dry run preview - {len(changes)} change(s) would be made:\n\n"
        output += f"Pattern: {pattern}\n"
        output += f"Rewrite: {rewrite}\n\n"

        # Group by file
        by_file: Dict[str, List] = {}
        for change in changes[:50]:  # Limit output
            file_path = change["file"]
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(change)

        for file_path, file_changes in by_file.items():
            output += f"📄 {file_path}\n"
            for c in file_changes[:5]:  # Limit per file
                line = c["line"]
                original = c["original"].strip()[:60]
                output += f"   Line {line}: {original}\n"
            if len(file_changes) > 5:
                output += f"   ... and {len(file_changes) - 5} more changes\n"
            output += "\n"

        if len(changes) > 50:
            output += f"... and {len(changes) - 50} more changes\n"

        output += "\nRun without dry_run=true to apply these changes."

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "dry_run": True,
                "pattern": pattern,
                "rewrite": rewrite,
                "changes": len(changes),
                "files_affected": len(by_file),
            },
        )
