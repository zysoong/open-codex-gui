# assistant-ui Integration Exploration

## Overview

**assistant-ui** is a YC W25-backed open source React library specifically designed for AI chat interfaces with:
- ✅ **Built-in auto-scrolling** (handles streaming properly)
- ✅ **Tool calling UI support** (custom components for agent actions)
- ✅ **Composable primitives** (use only what you need)
- ✅ **Custom backend support** (works with your existing WebSocket)

## Architecture

### Component-Based Approach (Like Radix UI)

Instead of one monolithic chat component, assistant-ui provides primitives:

```tsx
<AssistantRuntimeProvider runtime={runtime}>
  <Thread>
    <Thread.Viewport>
      <Thread.Messages />
    </Thread.Viewport>
    <Thread.Input />
  </Thread>
</AssistantRuntimeProvider>
```

### Runtime Layer

The runtime handles:
- Message state management
- Streaming
- Backend communication
- Tool execution

**Available Runtimes**:
1. **AI SDK Runtime** - For Vercel AI SDK
2. **LangGraph Runtime** - For LangGraph backends
3. **ExternalStore Runtime** ← **Perfect for your existing WebSocket backend!**
4. **Local Runtime** - For custom stateless APIs

## Integration Strategy for Your Project

### Option 1: Full Integration (Recommended)

Replace your entire ChatSessionPage with assistant-ui components while keeping:
- ✅ Your existing backend/API
- ✅ Project management
- ✅ Agent configuration
- ✅ WebSocket infrastructure

**Steps**:
1. Install assistant-ui
2. Create ExternalStoreRuntime adapter for your WebSocket
3. Replace VirtualizedChatList with assistant-ui Thread components
4. Create custom ToolUI components for file_edit, file_write, etc.

### Option 2: Partial Integration (Cherry-pick Components)

Use only specific components:
- `Thread.Messages` - Message list with auto-scroll
- `Thread.Viewport` - Scrollable container
- Tool UI system - For agent action blocks

**Trade-offs**:
- More control, but you handle more yourself
- May still have auto-scroll issues

## Custom Backend Integration (ExternalStoreRuntime)

### How It Works

```tsx
import { useExternalStoreRuntime } from "@assistant-ui/react";

const runtime = useExternalStoreRuntime({
  // Your adapter
  messages: yourMessagesState,
  isRunning: yourStreamingState,
  convertMessage: (msg) => ({
    // Convert your message format to assistant-ui format
    id: msg.id,
    role: msg.role,
    content: [{ type: "text", text: msg.content }],
  }),
  onNew: (message) => {
    // Send new message via your WebSocket
    yourWebSocket.send(JSON.stringify({
      type: 'message',
      content: message.content[0].text
    }));
  },
});
```

### Integration with Your WebSocket Hook

You can wrap your existing `useOptimizedStreaming` hook:

```tsx
const { messages, isStreaming, sendMessage } = useOptimizedStreaming({
  sessionId,
  initialMessages
});

const runtime = useExternalStoreRuntime({
  messages,
  isRunning: isStreaming,
  convertMessage: (msg) => ({
    id: msg.id,
    role: msg.role,
    content: [
      { type: "text", text: msg.content }
    ],
  }),
  onNew: (message) => {
    sendMessage(message.content[0].text);
  },
});
```

## Tool UI for Agent Actions

### Current Challenge

Your current issue:
- file_edit and file_write don't show streaming progress reliably
- Auto-scroll interferes with user scrolling

### assistant-ui Solution

Create custom ToolUI components:

```tsx
import { makeAssistantToolUI } from "@assistant-ui/react";

// For file_write
const FileWriteUI = makeAssistantToolUI({
  toolName: "file_write",
  render: ({ args, result, status }) => (
    <div className="tool-call file-write">
      <div className="tool-header">
        <span>📝</span>
        <strong>Writing {args.filename}</strong>
      </div>

      {status === "running" && (
        <div className="tool-progress">
          {/* Show streaming args */}
          <pre>{args.content}</pre>
        </div>
      )}

      {status === "complete" && result && (
        <div className="tool-result success">
          ✅ {result}
        </div>
      )}
    </div>
  ),
});

// For file_edit
const FileEditUI = makeAssistantToolUI({
  toolName: "file_edit",
  render: ({ args, result, status }) => (
    <div className="tool-call file-edit">
      <div className="tool-header">
        <span>✏️</span>
        <strong>Editing {args.path}</strong>
      </div>

      {status === "running" && (
        <div className="tool-progress">
          {/* Show diff preview */}
          <div className="diff">
            <div className="old">- {args.old_content}</div>
            <div className="new">+ {args.new_content}</div>
          </div>
        </div>
      )}

      {status === "complete" && result && (
        <div className="tool-result success">
          ✅ {result}
        </div>
      )}
    </div>
  ),
});
```

### Register Tools

```tsx
<AssistantRuntimeProvider runtime={runtime}>
  <FileWriteUI />
  <FileEditUI />
  <BashUI />
  <SearchUI />

  <Thread>
    {/* Chat UI */}
  </Thread>
</AssistantRuntimeProvider>
```

## Benefits Over Current Implementation

### 1. Auto-Scroll (Solved ✅)
- **Current**: Custom logic with `autoScrollingRef`, timing issues
- **assistant-ui**: Battle-tested auto-scroll that handles user intent properly

### 2. Tool Streaming (Solved ✅)
- **Current**: Manual buffering, timing delays, inconsistent display
- **assistant-ui**: Built-in tool UI with status tracking, no buffering issues

### 3. Maintenance (Improved ✅)
- **Current**: Custom components, manual testing, edge cases
- **assistant-ui**: >400k downloads/month, community-tested, active development

### 4. Accessibility (Bonus ✅)
- **Current**: Basic accessibility
- **assistant-ui**: WAI-ARIA compliant, keyboard navigation, screen reader support

## Migration Path

### Phase 1: Proof of Concept (1-2 hours)
1. Install assistant-ui: `npm install @assistant-ui/react`
2. Create a new `ChatSessionPageAssistantUI.tsx` alongside existing
3. Implement ExternalStoreRuntime adapter
4. Test with one tool (file_write)

### Phase 2: Full Chat Integration (2-4 hours)
1. Migrate all tool UIs (file_edit, bash, search, etc.)
2. Style to match your design
3. Add custom features (cancel button, error handling)

### Phase 3: Polish & Replace (1-2 hours)
1. Add tests
2. Replace old ChatSessionPage
3. Remove custom VirtualizedChatList and streaming logic

**Total Estimated Time: 4-8 hours**

## Keeping Your Existing Features

✅ **Keep**:
- Your backend (FastAPI + WebSocket)
- Project management UI
- Agent configuration panel
- Session history sidebar
- All API endpoints

🔄 **Replace**:
- VirtualizedChatList → Thread components
- Custom streaming logic → ExternalStoreRuntime
- Manual tool rendering → makeAssistantToolUI

## Alternative: Minimal Integration

If full migration is too much, you can:

### Option A: Use only auto-scroll
Import assistant-ui's scroll logic (they use Intersection Observer):
```tsx
import { useThreadViewportAutoScroll } from "@assistant-ui/react";
```

### Option B: Use only Tool UI system
Keep your VirtualizedChatList, but use assistant-ui's ToolUI for agent actions.

## Decision Matrix

| Approach | Effort | Auto-Scroll | Tool Streaming | Maintenance |
|----------|--------|-------------|----------------|-------------|
| **Current + Fixes** | Low | ⚠️ Fragile | ⚠️ Fragile | ⚠️ High |
| **Full assistant-ui** | Medium | ✅ Stable | ✅ Stable | ✅ Low |
| **Partial (Components)** | Low-Medium | ⚠️ Maybe | ✅ Stable | ⚠️ Medium |

## Recommendation

**Go with Full Integration (Option 1)** because:

1. **Your current auto-scroll is fundamentally fragile**
   - Timing-dependent (50ms, 500ms delays)
   - Difficult to get right with streaming
   - Hard to maintain edge cases

2. **assistant-ui is purpose-built for this**
   - 400k+ downloads/month = battle-tested
   - YC-backed = will be maintained
   - Active community = bugs get fixed

3. **Migration is straightforward**
   - ExternalStoreRuntime works with your WebSocket
   - Keep all your backend code
   - 4-8 hours of work vs. weeks of debugging

4. **Future-proof**
   - New features (attachments, voice, etc.) come free
   - Accessibility improvements
   - Performance optimizations

## Next Steps

1. **Review**: Check assistant-ui docs at https://www.assistant-ui.com/docs
2. **Prototype**: Create a branch and try ExternalStoreRuntime
3. **Evaluate**: Test auto-scroll and tool streaming
4. **Decide**: Full migration or partial integration

## Resources

- **Docs**: https://www.assistant-ui.com/docs
- **GitHub**: https://github.com/assistant-ui/assistant-ui
- **ExternalStore**: https://www.assistant-ui.com/docs/runtimes/custom/external-store
- **Tool UI**: https://www.assistant-ui.com/docs/guides/ToolUI
- **YC Launch**: https://www.ycombinator.com/launches/Mnc-assistant-ui-open-source-typescript-react-library-for-ai-chat
