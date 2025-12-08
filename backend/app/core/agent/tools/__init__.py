"""Tool system for ReAct agent."""

from app.core.agent.tools.base import Tool, ToolRegistry
from app.core.agent.tools.bash_tool import BashTool
from app.core.agent.tools.file_tools import FileReadTool, FileWriteTool
from app.core.agent.tools.search_tool_unified import UnifiedSearchTool
from app.core.agent.tools.environment_tool import SetupEnvironmentTool
from app.core.agent.tools.think_tool import ThinkTool
from app.core.agent.tools.line_edit_tool import LineEditTool

# Aliases for backward compatibility
SearchTool = UnifiedSearchTool

__all__ = [
    "Tool",
    "ToolRegistry",
    "BashTool",
    "FileReadTool",
    "FileWriteTool",
    "UnifiedSearchTool",
    "SearchTool",  # Alias
    "SetupEnvironmentTool",
    "ThinkTool",
    "LineEditTool",
]
