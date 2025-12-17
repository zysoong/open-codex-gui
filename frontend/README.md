# Open Claude UI Frontend

<div align="center">

**Modern React interface for AI-powered coding assistance**

[![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6?logo=typescript)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-5.4-646CFF?logo=vite)](https://vitejs.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../LICENSE)

</div>

---

## Overview

The Open Claude UI frontend provides a real-time chat interface for interacting with autonomous AI coding agents. The clean design is inspired by the Claude web interface. Built with React and TypeScript, it features optimized streaming, virtual scrolling, and rich tool visualization.

## Features

### Real-time Streaming
- WebSocket-based message streaming with 30ms batching
- Per-block content buffering for multi-response handling
- Automatic reconnection with message queue preservation
- Stream cancellation support

### Chat Interface
- **Virtualized message list** using React-Virtuoso for thousands of messages
- **Rich content rendering** - Markdown, syntax-highlighted code, images, PDFs
- **Multi-block responses** - Assistant responses can span multiple text blocks interleaved with tool calls
- **Auto-scroll** with smart follow-output behavior

### Tool Visualization
- **Step grouping** - Tool calls grouped by semantic purpose (Setup, Read, Edit, Run, Think)
- **Live execution display** - Watch tool arguments stream and results appear
- **Collapsible interface** - Auto-expand on run, auto-collapse on completion
- **Error highlighting** - Failed steps clearly marked with status indicators

### Project Management
- Project cards with metadata and quick actions
- Multiple chat sessions per project with tab navigation
- Workspace file browser with upload/download support
- Agent configuration panel for LLM and tool settings

### Agent Configuration
- LLM provider selection (OpenAI, Anthropic, Google, Azure)
- Model picker with latest options from each provider
- Tool enablement toggles
- Custom system instructions
- Pre-built agent templates

## Tech Stack

| Category | Technology |
|----------|------------|
| Framework | React 18.3 |
| Language | TypeScript 5.7 |
| Build Tool | Vite 5.4 |
| State Management | Zustand 5.0 |
| Data Fetching | TanStack Query 5.62 |
| Virtualization | React-Virtuoso 4.14 |
| Markdown | Streamdown 1.6 (streaming-optimized) |
| Code Highlighting | Prism via react-syntax-highlighter |
| Desktop | Electron 33 (optional) |
| Styling | Tailwind CSS 4 |

## Quick Start

### Prerequisites

- Node.js 18+
- npm or yarn
- Backend server running on port 8000

### Installation

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Open http://localhost:5173
```

### Desktop App (Electron)

```bash
# Development
npm run electron:dev

# Build
npm run electron:build
```

## Project Structure

```
src/
├── components/
│   ├── assistant-ui/          # Chat interface components
│   │   ├── AssistantUIChatPage.tsx
│   │   ├── AssistantUIMessage.tsx
│   │   ├── ToolStepGroup.tsx
│   │   └── DefaultToolFallback.tsx
│   ├── ProjectList/           # Project management
│   ├── ProjectSession/        # Chat workspace
│   │   └── hooks/
│   │       └── useOptimizedStreaming.ts
│   └── ChatFileSidebar/       # File browser
├── services/
│   ├── api.ts                 # REST API client
│   └── websocket.ts           # WebSocket client
├── stores/                    # Zustand state stores
├── types/                     # TypeScript definitions
└── main.tsx
```

## Key Components

### `useOptimizedStreaming`

Core hook managing WebSocket streaming with advanced features:

```typescript
const {
  streamingBlocks,    // Map of block ID to streaming content
  streamEvents,       // Buffered stream events
  isStreaming,        // Current streaming state
  sendMessage,        // Send user message
  cancelStream        // Cancel active stream
} = useOptimizedStreaming({ sessionId });
```

Features:
- Per-block state management
- 30ms flush interval for smooth streaming
- Smart content merging with API data
- Binary data and image handling
- Automatic reconnection

### `ToolStepGroup`

Groups consecutive tool calls into collapsible semantic steps:

- **Setup** - Environment initialization
- **Read** - File reads and searches
- **Edit** - File writes and modifications
- **Run** - Bash command execution
- **Think** - Agent reasoning (chain-of-thought)

### `AssistantUIMessage`

Renders assistant messages with support for:
- Multiple text blocks per response
- Interleaved tool calls and text
- Streaming content with cursor animation
- Binary data visualization (images from tool results)

## Scripts

```bash
npm run dev          # Start dev server
npm run build        # Production build
npm run preview      # Preview production build
npm run lint         # ESLint check
npm run test:e2e     # Playwright E2E tests
npm run electron:dev # Electron development
npm run electron:build # Build desktop app
```

## Environment Variables

Create `.env.local`:

```bash
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

## WebSocket Events

The frontend handles these streaming events:

| Event | Description |
|-------|-------------|
| `stream_sync` | Server state sync on reconnect |
| `assistant_text_start` | New text block started |
| `chunk` | Text content chunk |
| `assistant_text_end` | Text block completed |
| `action_streaming` | Tool call started |
| `action_args_chunk` | Tool arguments streaming |
| `tool_call_block` | Tool call persisted |
| `tool_result_block` | Tool result received |
| `cancelled` | Stream cancelled |
| `error` | Error occurred |

## Performance

- **Virtual scrolling** - Constant 60 FPS with thousands of messages
- **Memoized rendering** - Components only re-render on content change
- **Batched updates** - 30ms intervals prevent excessive re-renders
- **Code splitting** - Dynamic imports for routes

## Testing

```bash
# E2E tests
npm run test:e2e

# With UI
npm run test:e2e:ui

# Debug mode
npm run test:e2e:debug
```

## License

MIT License - see [LICENSE](../LICENSE) for details.
