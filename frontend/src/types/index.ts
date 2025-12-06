// Project types
export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
}

export interface ProjectListResponse {
  projects: Project[];
  total: number;
}

// Agent Configuration types
export interface AgentConfiguration {
  id: string;
  project_id: string;
  agent_type: string;
  system_instructions: string | null;
  enabled_tools: string[];
  llm_provider: string;
  llm_model: string;
  llm_config: Record<string, any>;
}

export interface AgentConfigurationUpdate {
  agent_type?: string;
  system_instructions?: string | null;
  enabled_tools?: string[];
  llm_provider?: string;
  llm_model?: string;
  llm_config?: Record<string, any>;
}

// Chat Session types
export interface ChatSession {
  id: string;
  project_id: string;
  name: string;
  updated_at: string;
  created_at: string;
  container_id: string | null;
  status: 'active' | 'archived';
  environment_type?: string | null; // Set by agent when environment is configured
}

export interface ChatSessionCreate {
  name: string;
}

export interface ChatSessionListResponse {
  chat_sessions: ChatSession[];
  total: number;
}

// ContentBlock types (unified message model)
export type ContentBlockType = 'user_text' | 'assistant_text' | 'tool_call' | 'tool_result' | 'system';
export type ContentBlockAuthor = 'user' | 'assistant' | 'system' | 'tool';

export interface ContentBlock {
  id: string;
  chat_session_id: string;
  sequence_number: number;
  block_type: ContentBlockType;
  author: ContentBlockAuthor;
  content: Record<string, any>;  // Structure varies by block_type
  parent_block_id?: string | null;
  block_metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface ContentBlockListResponse {
  blocks: ContentBlock[];
  total: number;
}

// Content payload structures for different block types
export interface TextContent {
  text: string;
}

export interface ToolCallContent {
  tool_name: string;
  arguments: Record<string, any>;
  status: 'pending' | 'running' | 'complete' | 'error';
}

export interface ToolResultContent {
  tool_name: string;
  result?: string;
  success: boolean;
  error?: string;
  is_binary?: boolean;
  binary_type?: string;
  binary_data?: string;
}

// WebSocket streaming events
export interface StreamEvent {
  type: 'chunk' | 'action' | 'action_streaming' | 'action_args_chunk' |
        'user_text_block' | 'assistant_text_start' | 'assistant_text_end' |
        'tool_call_block' | 'tool_result_block' | 'stream_sync';
  content?: string;
  tool?: string;
  args?: any;
  partial_args?: string;
  step?: number;
  success?: boolean;
  status?: string;
  metadata?: any;
  block?: ContentBlock;
  block_id?: string;
  accumulated_content?: string;  // For stream_sync
  streaming?: boolean;           // For stream_sync
  sequence_number?: number;      // For stream_sync
}

// Legacy types for backward compatibility during migration
export interface Message {
  id: string;
  chat_session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  agent_actions?: any[];
  message_metadata: Record<string, any>;
}

export interface MessageCreate {
  content: string;
  role?: 'user' | 'assistant' | 'system';
  message_metadata?: Record<string, any>;
}

export interface MessageListResponse {
  messages: Message[];
  total: number;
}

// Legacy AgentAction interface for backward compatibility
export interface AgentAction {
  type: 'thought' | 'action' | 'action_streaming' | 'observation';
  content: string;
  tool?: string;
  args?: any;
  success?: boolean;
  status?: string;
  step?: number;
}
