"""Unified search tool - AST-aware for code structures, text-based for content."""

from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import re
from app.core.agent.tools.base import Tool, ToolParameter, ToolResult
from app.core.sandbox.container import SandboxContainer


# Pattern shortcuts that expand to language-specific AST patterns
PATTERN_SHORTCUTS: Dict[str, Dict[str, str]] = {
    "functions": {
        "python": "def $NAME($$$)",
        "javascript": "function $NAME($$$)",
        "typescript": "function $NAME($$$)",
        "go": "func $NAME($$$)",
        "rust": "fn $NAME($$$)",
        "java": "$RET $NAME($$$) {$$$}",
        "c": "$RET $NAME($$$)",
        "cpp": "$RET $NAME($$$)",
    },
    "async_functions": {
        "python": "async def $NAME($$$)",
        "javascript": "async function $NAME($$$)",
        "typescript": "async function $NAME($$$)",
        "rust": "async fn $NAME($$$)",
    },
    "classes": {
        "python": "class $NAME",
        "javascript": "class $NAME",
        "typescript": "class $NAME",
        "go": "type $NAME struct",
        "rust": "struct $NAME",
        "java": "class $NAME",
        "c": "struct $NAME",
        "cpp": "class $NAME",
    },
    "imports": {
        "python": "import $$$",
        "javascript": "import $$$",
        "typescript": "import $$$",
        "go": "import $$$",
        "rust": "use $$$",
        "java": "import $$$",
        "c": "#include $$$",
        "cpp": "#include $$$",
    },
    "exports": {
        "javascript": "export $$$",
        "typescript": "export $$$",
        "rust": "pub $$$",
        "java": "public $$$",
    },
    "tests": {
        "python": "def test_$NAME($$$)",
        "javascript": "test($$$)",
        "typescript": "test($$$)",
        "go": "func Test$NAME($$$)",
        "rust": "#[test]",
        "java": "@Test",
    },
    "methods": {
        "python": "def $NAME(self, $$$)",
        "javascript": "$NAME($$$) {",
        "typescript": "$NAME($$$) {",
        "go": "func ($R $TYPE) $NAME($$$)",
        "rust": "fn $NAME(&self, $$$)",
        "java": "$MOD $RET $NAME($$$)",
        "cpp": "$RET $CLASS::$NAME($$$)",
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


class UnifiedSearchTool(Tool):
    """Unified search tool - automatically uses the best search method."""

    def __init__(self, container: SandboxContainer):
        self._container = container

    @property
    def name(self) -> str:
        return "search"

    @property
    def description(self) -> str:
        return (
            "Search for code, text, or files in the workspace.\n\n"
            "USAGE:\n"
            "- Find functions: query='functions', language='python'\n"
            "- Find classes: query='classes', language='python'\n"
            "- Find text: query='error message' (searches file contents)\n"
            "- Find files: query='*.py' (finds Python files)\n\n"
            "The 'language' parameter is REQUIRED for code structure searches.\n"
            "Supported languages: python, javascript, typescript, go, rust, java, c, cpp"
        )

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description=(
                    "What to search for: 'functions', 'classes', 'imports' for code; "
                    "any text for grep; '*.py' for files"
                ),
                required=True,
            ),
            ToolParameter(
                name="language",
                type="string",
                description=(
                    "REQUIRED for code search. Options: python, javascript, typescript, go, rust, java, c, cpp"
                ),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="path",
                type="string",
                description="Directory to search (default: /workspace/agent_workspace)",
                required=False,
                default="/workspace/agent_workspace",
            ),
            ToolParameter(
                name="max_results",
                type="number",
                description="Max results (default: 50)",
                required=False,
                default=50,
            ),
        ]

    def _detect_mode(self, query: str) -> str:
        """Auto-detect the search mode based on query pattern."""
        query_lower = query.lower().strip()

        # Check if it's a shortcut
        if query_lower in PATTERN_SHORTCUTS:
            return "code"

        # Check if it looks like an AST pattern (contains metavariables)
        if "$" in query or "$$" in query:
            return "code"

        # Check if it looks like a filename pattern
        if "*" in query or query.startswith(".") or "/" not in query and "." in query:
            # Patterns like *.py, *.js, config.json, .gitignore
            if re.match(r'^[\w\-.*?]+\.\w+$', query) or query.startswith("*"):
                return "filename"

        # Default to text search
        return "text"

    def _normalize_language(self, language: Optional[str]) -> Optional[str]:
        if not language:
            return None
        lang = language.lower()
        return LANGUAGE_ALIASES.get(lang, lang)

    def _resolve_pattern(self, pattern: str, language: Optional[str]) -> str:
        """Resolve shortcut to AST pattern."""
        if pattern.lower() in PATTERN_SHORTCUTS:
            shortcut = pattern.lower()
            shortcuts = PATTERN_SHORTCUTS[shortcut]
            if language:
                lang = LANGUAGE_ALIASES.get(language.lower(), language.lower())
                if lang in shortcuts:
                    return shortcuts[lang]
            return shortcuts.get("python", list(shortcuts.values())[0])
        return pattern

    async def execute(
        self,
        query: str,
        mode: Optional[str] = None,
        language: Optional[str] = None,
        path: str = "/workspace/agent_workspace",
        file_pattern: Optional[str] = None,
        max_results: int = 50,
        **kwargs
    ) -> ToolResult:
        """Execute search using the appropriate method."""
        try:
            # Resolve path
            search_path = Path(path)
            if not search_path.is_absolute():
                search_path = Path("/workspace") / path

            # Validate path exists
            exit_code, _, _ = await self._container.execute(
                f"test -e {search_path} && echo 'exists'",
                workdir="/workspace",
                timeout=5
            )
            if exit_code != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path not found: {search_path}",
                    metadata={"path": str(search_path)},
                )

            # Auto-detect mode if not specified
            detected_mode = mode or self._detect_mode(query)

            if detected_mode == "code":
                return await self._search_code(query, language, search_path, max_results)
            elif detected_mode == "filename":
                return await self._search_filename(query, search_path, max_results)
            else:  # text
                return await self._search_text(query, search_path, file_pattern, max_results)

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Search failed: {str(e)}",
                metadata={"query": query},
            )

    async def _search_code(
        self,
        query: str,
        language: Optional[str],
        search_path: Path,
        max_results: int
    ) -> ToolResult:
        """AST-aware code structure search."""
        # Check if language is provided for shortcut queries
        query_lower = query.lower().strip()
        is_shortcut = query_lower in PATTERN_SHORTCUTS

        if is_shortcut and not language:
            return ToolResult(
                success=False,
                output="",
                error=(
                    f"The 'language' parameter is required when searching for '{query}'. "
                    f"Please specify language='python' (or javascript, typescript, go, rust, java, c, cpp)."
                ),
                metadata={"query": query},
            )

        # Check if ast-grep is available
        exit_code, _, _ = await self._container.execute(
            "which ast-grep",
            workdir="/workspace",
            timeout=5
        )
        if exit_code != 0:
            # Fallback to text search
            return await self._search_text(query, search_path, None, max_results)

        norm_language = self._normalize_language(language)
        resolved_pattern = self._resolve_pattern(query, norm_language)

        # Build command using short flags: ast-grep run -p 'PATTERN' -l LANG --json PATH
        cmd_parts = ["ast-grep", "run", "-p", f"'{resolved_pattern}'"]
        if norm_language:
            cmd_parts.extend(["-l", norm_language])
        cmd_parts.append("--json")
        cmd_parts.append(str(search_path))

        cmd = " ".join(cmd_parts)

        exit_code, stdout, stderr = await self._container.execute(
            cmd, workdir="/workspace", timeout=60
        )

        if exit_code != 0 and not stdout:
            if "no matches" in stderr.lower() or exit_code == 1:
                return ToolResult(
                    success=True,
                    output=f"No code matches found for: {query}",
                    metadata={"query": query, "mode": "code", "matches": 0},
                )
            # Fallback to text search on error
            return await self._search_text(query, search_path, None, max_results)

        matches = self._parse_ast_results(stdout, max_results)

        if not matches:
            return ToolResult(
                success=True,
                output=f"No code matches found for: {query}",
                metadata={"query": query, "mode": "code", "matches": 0},
            )

        output = self._format_code_results(matches, query, resolved_pattern, max_results)
        return ToolResult(
            success=True,
            output=output,
            metadata={"query": query, "mode": "code", "matches": len(matches)},
        )

    async def _search_text(
        self,
        query: str,
        search_path: Path,
        file_pattern: Optional[str],
        max_results: int
    ) -> ToolResult:
        """Text/grep-based content search."""
        safe_query = query.replace("'", "'\\''")

        if file_pattern:
            safe_pattern = file_pattern.replace("'", "'\\''")
            cmd = f"find {search_path} -type f -name '{safe_pattern}' -exec grep -l '{safe_query}' {{}} \\; 2>/dev/null | head -n {max_results}"
        else:
            cmd = f"grep -rl '{safe_query}' {search_path} 2>/dev/null | head -n {max_results}"

        exit_code, stdout, stderr = await self._container.execute(
            cmd, workdir="/workspace", timeout=30
        )

        files = [f.strip() for f in stdout.strip().split("\n") if f.strip()]

        if not files:
            return ToolResult(
                success=True,
                output=f"No files found containing: {query}",
                metadata={"query": query, "mode": "text", "matches": 0},
            )

        # Get context for matches
        output = f"Found '{query}' in {len(files)} file(s):\n\n"
        for file_path in files[:max_results]:
            output += f"📄 {file_path}\n"
            # Get matching lines
            context_cmd = f"grep -n '{safe_query}' '{file_path}' 2>/dev/null | head -n 3"
            _, context, _ = await self._container.execute(
                context_cmd, workdir="/workspace", timeout=10
            )
            for line in context.strip().split("\n")[:3]:
                if line.strip():
                    output += f"   {line[:100]}\n"
            output += "\n"

        return ToolResult(
            success=True,
            output=output.strip(),
            metadata={"query": query, "mode": "text", "matches": len(files)},
        )

    async def _search_filename(
        self,
        query: str,
        search_path: Path,
        max_results: int
    ) -> ToolResult:
        """Find files by name pattern."""
        safe_query = query.replace("'", "'\\''")

        # Handle recursive patterns
        if "**" in query:
            base_pattern = query.split("**")[-1].lstrip("/")
            cmd = f"find {search_path} -type f -name '{base_pattern}' 2>/dev/null | head -n {max_results}"
        else:
            cmd = f"find {search_path} -type f -name '{safe_query}' 2>/dev/null | head -n {max_results}"

        exit_code, stdout, stderr = await self._container.execute(
            cmd, workdir="/workspace", timeout=30
        )

        files = [f.strip() for f in stdout.strip().split("\n") if f.strip()]

        if not files:
            return ToolResult(
                success=True,
                output=f"No files found matching: {query}",
                metadata={"query": query, "mode": "filename", "matches": 0},
            )

        output = f"Found {len(files)} file(s) matching '{query}':\n"
        for f in files[:max_results]:
            output += f"  - {f}\n"

        return ToolResult(
            success=True,
            output=output.strip(),
            metadata={"query": query, "mode": "filename", "matches": len(files), "files": files},
        )

    def _parse_ast_results(self, stdout: str, max_results: int) -> List[Dict[str, Any]]:
        """Parse ast-grep JSON output.

        ast-grep --json outputs a JSON array, not newline-delimited JSON.
        """
        matches = []
        if not stdout.strip():
            return matches

        try:
            # ast-grep outputs a JSON array
            results = json.loads(stdout)

            # Handle both array format and single object
            if isinstance(results, dict):
                results = [results]
            elif not isinstance(results, list):
                return matches

            for result in results:
                if len(matches) >= max_results:
                    break
                matches.append({
                    "file": result.get("file", ""),
                    "line": result.get("range", {}).get("start", {}).get("line", 0),
                    "match": result.get("text", ""),
                })
        except json.JSONDecodeError:
            # Fallback: try parsing as NDJSON (newline-delimited)
            for line in stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    result = json.loads(line)
                    matches.append({
                        "file": result.get("file", ""),
                        "line": result.get("range", {}).get("start", {}).get("line", 0),
                        "match": result.get("text", ""),
                    })
                    if len(matches) >= max_results:
                        break
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass

        return matches

    def _format_code_results(
        self,
        matches: List[Dict[str, Any]],
        query: str,
        resolved_pattern: str,
        max_results: int
    ) -> str:
        """Format AST search results."""
        is_shortcut = query.lower() in PATTERN_SHORTCUTS
        if is_shortcut:
            output = f"Found {len(matches)} match(es) for '{query}' (pattern: {resolved_pattern}):\n\n"
        else:
            output = f"Found {len(matches)} match(es) for pattern '{resolved_pattern}':\n\n"

        by_file: Dict[str, List] = {}
        for match in matches[:max_results]:
            file_path = match.get("file", "unknown")
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(match)

        for file_path, file_matches in by_file.items():
            output += f"📄 {file_path}\n"
            for m in file_matches:
                line = m.get("line", "?")
                match_text = m.get("match", "").strip().split("\n")[0][:80]
                output += f"   Line {line}: {match_text}\n"
            output += "\n"

        return output.strip()
