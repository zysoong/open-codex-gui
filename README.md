<div align="center">

# OpenCodex

**Self-hosted AI coding assistant with autonomous agents and sandboxed execution**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Node.js 18+](https://img.shields.io/badge/node-18+-339933?logo=node.js&logoColor=white)](https://nodejs.org/)
[![Docker](https://img.shields.io/badge/docker-required-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

[Features](#features) · [Quick Start](#quick-start) · [Documentation](#documentation) · [Contributing](#contributing)

</div>

---

## What is OpenCodex?

OpenCodex is a self-hosted alternative to cloud-based AI coding assistants. It provides a web interface for interacting with autonomous AI agents that can write, execute, and debug code in isolated Docker containers.

**Key benefits:**
- **Privacy** - Your code stays on your infrastructure
- **Choice** - Use any LLM provider (OpenAI, Anthropic, Google, or 100+ others via LiteLLM)
- **Control** - Configure agents, tools, and execution environments per project
- **Safety** - All code execution happens in sandboxed Docker containers

## Features

### Autonomous Agents

ReAct-based agents that reason through problems step by step:

- **Multi-step execution** - Agents plan, execute, observe, and iterate
- **Tool use** - File operations, bash commands, code search, and more
- **Streaming output** - Watch the agent think and act in real-time
- **Configurable limits** - Control iteration count, timeouts, and resource usage

### Sandboxed Execution

Secure Docker containers for code execution:

- **13 language environments** - Python (3.11-3.13), Node.js (20, 22), Java 21, Go 1.23, Rust 1.83, C++, Ruby 3.3, PHP 8.3, .NET 8, Kotlin, Scala
- **Container pooling** - Pre-warmed containers for fast startup
- **Resource limits** - CPU, memory, and disk quotas
- **File isolation** - Workspace separation between projects

### Agent Tools

| Tool | Description |
|------|-------------|
| `bash` | Execute shell commands with timeout |
| `file_read` | Read files with line numbers, detect binary/images |
| `file_write` | Create files in workspace |
| `edit_lines` | Line-based editing with auto-indent and syntax validation |
| `search` | Code search with ast-grep or regex |
| `think` | Structured reasoning for complex decisions |

### Real-time Interface

Modern React frontend with optimized streaming:

- **30ms batched updates** - Smooth streaming like ChatGPT
- **Virtual scrolling** - Handle thousands of messages
- **Tool visualization** - Collapsible steps showing agent actions
- **Rich content** - Markdown, syntax highlighting, images

### Multi-Provider LLM Support

Use any LLM via LiteLLM:

- OpenAI (GPT-4o, GPT-4o-mini)
- Anthropic (Claude Sonnet 4, Claude Opus 4)
- Google (Gemini Pro, Gemini Flash)
- Azure OpenAI
- Groq, Together, Ollama, and 100+ more

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker 20.10+
- An LLM API key (OpenAI, Anthropic, etc.)

### Installation

```bash
# Clone the repository
git clone https://github.com/anthropics/opencodex.git
cd opencodex

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env and add your API keys

# Start backend
python -m app.main

# Frontend setup (new terminal)
cd frontend
npm install
npm run dev

# Open http://localhost:5173
```

### Using Docker Compose

```bash
docker-compose up -d
# Open http://localhost:3000
```

## Configuration

Create `backend/.env`:

```bash
# LLM API Keys (add the ones you use)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/open_codex.db

# Security
SECRET_KEY=generate-a-random-key
ENCRYPTION_KEY=generate-a-32-byte-key

# Docker
DOCKER_HOST=unix:///var/run/docker.sock
CONTAINER_PREFIX=opencodex
```

See [backend/README.md](backend/README.md) for all configuration options.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│  React + TypeScript + Vite                                  │
│  - Real-time streaming via WebSocket                        │
│  - Virtual scrolling with React-Virtuoso                    │
│  - Tool visualization with collapsible steps                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                        Backend                               │
│  FastAPI + SQLAlchemy + LiteLLM                             │
│  - ReAct agent with tool execution                          │
│  - WebSocket streaming                                       │
│  - REST API for projects, sessions, files                   │
└────────────────────────┬────────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
     ┌─────────┐   ┌─────────┐   ┌─────────┐
     │ LiteLLM │   │ SQLite  │   │ Docker  │
     │ (LLMs)  │   │  (DB)   │   │(Sandbox)│
     └─────────┘   └─────────┘   └─────────┘
```

## Documentation

| Resource | Description |
|----------|-------------|
| [Frontend README](frontend/README.md) | React app setup and components |
| [Backend README](backend/README.md) | API server, agent system, tools |
| [API Docs](http://localhost:8000/docs) | Interactive Swagger documentation |

## Agent Templates

Pre-configured agents for common tasks:

| Template | Use Case |
|----------|----------|
| `python_dev` | Python 3.13 development with pytest |
| `node_dev` | TypeScript/JavaScript development |
| `data_analyst` | Data analysis with pandas, matplotlib |
| `code_reviewer` | Read-only code review |
| `test_writer` | Test generation |
| `default` | General purpose (Python 3.13) |

## Example Usage

1. **Create a project** - Click "New Project" and give it a name
2. **Start a chat** - Open the project and create a new chat session
3. **Ask the agent** - Examples:
   - "Create a Flask API with user authentication"
   - "Analyze this CSV and create visualizations"
   - "Write tests for the utils module"
   - "Debug why the login function fails"

The agent will:
- Set up the environment (Python, Node.js, etc.)
- Write and execute code in the sandbox
- Show you results and iterate based on errors
- Present the final output

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
# Backend
cd backend
pip install -r requirements-dev.txt
pytest
black app tests
mypy app

# Frontend
cd frontend
npm install
npm run lint
npm run test:e2e
```

### Areas for Contribution

- New agent tools
- Additional LLM provider support
- UI/UX improvements
- Documentation
- Bug fixes and optimizations

## Related Projects

OpenCodex is inspired by:

- [OpenHands](https://github.com/All-Hands-AI/OpenHands) - Open-source AI software engineers
- [Aider](https://aider.chat) - AI pair programming in terminal
- [Continue](https://continue.dev) - AI code assistant for IDEs

## License

MIT License - see [LICENSE](LICENSE) for details.

---

<div align="center">

**[Get Started](#quick-start)** · **[Report Bug](https://github.com/anthropics/opencodex/issues)** · **[Request Feature](https://github.com/anthropics/opencodex/issues)**

</div>
