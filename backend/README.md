# Open Claude UI Backend

<div align="center">

**FastAPI server powering autonomous AI coding agents**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![LiteLLM](https://img.shields.io/badge/LiteLLM-100%2B_providers-orange)](https://docs.litellm.ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../LICENSE)

</div>

---

## Overview

The Open Claude UI backend powers the chatbot with a ReAct-based agent system and sandboxed code execution. It supports 100+ LLM providers via LiteLLM and executes code safely in isolated Docker containers.

## Features

### Agent System
- **ReAct pattern** - Reasoning and Acting loop for autonomous problem solving
- **30 iteration limit** - Prevents runaway execution
- **Tool validation** - Pydantic-based parameter validation with retry logic
- **Streaming output** - Real-time LLM responses via WebSocket

### Agent Tools

| Tool | Description |
|------|-------------|
| `bash` | Execute shell commands with timeout support |
| `file_read` | Read files with line numbers, auto-detect binary/images |
| `file_write` | Create files in sandbox workspace |
| `edit_lines` | Line-based editing with auto-indentation and syntax validation |
| `search` | Code search with ast-grep or regex fallback |
| `think` | Structured reasoning tool for complex decisions |
| `setup_environment` | Initialize sandbox environments (13 languages supported) |

### Sandbox Execution
- **Docker isolation** - Each session runs in its own container
- **Container pooling** - Pre-warmed containers for fast startup
- **13 language environments** - Python (3.11-3.13), Node.js (20, 22), Java 21, Go 1.23, Rust 1.83, C++, Ruby 3.3, PHP 8.3, .NET 8, Kotlin, Scala
- **Resource limits** - CPU, memory, and disk quotas
- **Volume mounting** - Project files accessible read-only at `/workspace/project_files`

### LLM Integration
- **100+ providers** via LiteLLM (OpenAI, Anthropic, Google, Azure, Groq, etc.)
- **Function calling** - Native tool use with streaming support
- **API key encryption** - AES-256 encrypted credential storage
- **Per-project configuration** - Different models per project

### Storage Options
- **Local** - File system storage for development
- **Volume** - Docker volumes for production
- **S3** - AWS S3 or compatible (MinIO) for cloud deployments

## Quick Start

### Prerequisites

- Python 3.11+
- Docker 20.10+
- At least one LLM API key (OpenAI, Anthropic, etc.)

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start server
python -m app.main
```

### Using Poetry

```bash
poetry install
poetry run python -m app.main
```

### Docker

```bash
docker build -t open-claude-ui-backend .
docker run -p 8000:8000 --env-file .env -v /var/run/docker.sock:/var/run/docker.sock open-claude-ui-backend
```

## Configuration

Create `.env` file:

```bash
# LLM API Keys (add the ones you use)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
GROQ_API_KEY=...

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/open-claude-ui.db

# Security
SECRET_KEY=your-secret-key
ENCRYPTION_KEY=your-32-byte-encryption-key

# Server
HOST=127.0.0.1
PORT=8000
CORS_ORIGINS=["http://localhost:5173"]

# Docker
DOCKER_HOST=unix:///var/run/docker.sock
CONTAINER_PREFIX=openclaudeui
CONTAINER_POOL_SIZE=5

# Storage
STORAGE_TYPE=local
STORAGE_PATH=./data/storage

# Agent defaults
DEFAULT_LLM_MODEL=gpt-5-mini
AGENT_MAX_ITERATIONS=30
```

## Project Structure

```
app/
├── api/
│   ├── routes/              # REST endpoints
│   │   ├── chat.py
│   │   ├── projects.py
│   │   ├── sandbox.py
│   │   └── files.py
│   └── websocket/
│       └── chat_handler.py  # WebSocket streaming
├── core/
│   ├── agent/
│   │   ├── executor.py      # ReAct agent loop
│   │   ├── templates.py     # Agent configurations
│   │   └── tools/           # Agent tools
│   │       ├── bash_tool.py
│   │       ├── file_tools.py
│   │       ├── line_edit_tool.py
│   │       ├── search_tool_unified.py
│   │       └── think_tool.py
│   ├── llm/
│   │   └── provider.py      # LiteLLM wrapper
│   ├── sandbox/
│   │   ├── container.py     # Docker operations
│   │   └── manager.py       # Container pool
│   └── storage/
│       ├── local_storage.py
│       ├── volume_storage.py
│       └── s3_storage.py
├── models/
│   └── database/            # SQLAlchemy models
└── main.py
```

## Agent Tools

### `edit_lines` - Line-Based Editing

Precise file editing using line numbers (solves whitespace matching issues):

```python
# Replace lines 15-17
edit_lines(path="/workspace/out/main.py", command="replace",
           start_line=15, end_line=17, new_content="    return result")

# Insert after line 10
edit_lines(path="/workspace/out/main.py", command="insert",
           insert_line=10, new_content="    # New comment")

# Delete lines 5-8
edit_lines(path="/workspace/out/main.py", command="delete",
           start_line=5, end_line=8)
```

Features:
- Auto-indentation detection from context
- Python syntax validation before write
- Diff output showing changes

### `think` - Structured Reasoning

Chain-of-thought reasoning without side effects:

```python
think(thought="Let me analyze this error. The traceback shows...")
```

Based on [Anthropic's research](https://www.anthropic.com/engineering/claude-think-tool) - improves agent accuracy on complex tasks.

### `search` - Code Search

Unified search with pattern shortcuts:

```python
# Find all Python functions
search(query="functions", path="/workspace/out", pattern="*.py")

# Find specific text
search(query="TODO", path="/workspace/out")

# Find classes
search(query="classes", path="/workspace/out/models.py")
```

Shortcuts: `functions`, `classes`, `imports`, `async_functions`, `tests`, `methods`

## Agent Templates

Pre-configured agents in `app/core/agent/templates.py`:

| Template | Environment | Description |
|----------|-------------|-------------|
| `python_dev` | Python 3.13 | Python development with pytest |
| `node_dev` | Node.js 20 | TypeScript/JavaScript development |
| `data_analyst` | Python 3.13 | Data analysis with pandas, matplotlib |
| `script_writer` | Python 3.13 | Automation scripts |
| `code_reviewer` | Python 3.13 | Read-only code review |
| `test_writer` | Python 3.13 | Test generation |
| `minimal` | Python 3.13 | Simple read-only tasks |
| `default` | Python 3.13 | General purpose |

## API Reference

### REST Endpoints

```
# Projects
GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/{id}
PUT    /api/v1/projects/{id}
DELETE /api/v1/projects/{id}

# Chat Sessions
GET    /api/v1/projects/{id}/chat-sessions
POST   /api/v1/projects/{id}/chat-sessions
GET    /api/v1/chats/{id}
DELETE /api/v1/chats/{id}

# Messages
GET    /api/v1/chats/{id}/messages
POST   /api/v1/chats/{id}/messages

# Sandbox
POST   /api/v1/sandbox/{session_id}/start
POST   /api/v1/sandbox/{session_id}/execute
GET    /api/v1/sandbox/{session_id}/status
DELETE /api/v1/sandbox/{session_id}/stop

# Files
POST   /api/v1/files/upload/{project_id}
GET    /api/v1/files/project/{project_id}
GET    /api/v1/files/{id}/download
DELETE /api/v1/files/{id}
```

### WebSocket Streaming

```python
# Connect
ws = websocket.connect(f"ws://localhost:8000/api/v1/chats/{session_id}/stream")

# Send message
ws.send(json.dumps({"type": "message", "content": "Create a Flask API"}))

# Receive events
# Types: start, chunk, action, observation, tool_call_block, tool_result_block, end, error
```

### Interactive Docs

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Creating Custom Tools

```python
from app.core.agent.tools.base import Tool, ToolResult, ToolParameter

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Tool description for the LLM"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="param1",
                type="string",
                description="Parameter description",
                required=True
            )
        ]

    async def execute(self, param1: str, **kwargs) -> ToolResult:
        # Tool logic
        return ToolResult(success=True, output="Result")
```

Register in `chat_handler.py`:

```python
tool_registry.register(MyTool(container))
```

## Development

```bash
# Run with auto-reload
RELOAD=true python -m app.main

# Debug logging
LOG_LEVEL=DEBUG python -m app.main

# Run tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Type checking
mypy app

# Format code
black app tests
ruff check app tests
```

## Database

SQLite with async support via aiosqlite. Models:

- **Project** - Workspace container
- **ChatSession** - Individual chat sessions
- **ContentBlock** - Messages (user_text, assistant_text, tool_call, tool_result)
- **AgentConfiguration** - Per-project agent settings
- **ApiKey** - Encrypted API credentials
- **File** - File metadata

## Troubleshooting

### Docker Permission Denied

```bash
sudo usermod -aG docker $USER
newgrp docker
```

### Database Locked

```bash
# Enable WAL mode
sqlite3 data/open-claude-ui.db "PRAGMA journal_mode=WAL;"
```

### Port in Use

```bash
lsof -i :8000
kill -9 <PID>
```

## License

MIT License - see [LICENSE](../LICENSE) for details.
