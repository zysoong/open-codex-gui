import axios from 'axios';
import type {
  Project,
  ProjectCreate,
  ProjectUpdate,
  ProjectListResponse,
  AgentConfiguration,
  AgentConfigurationUpdate,
  ChatSession,
  ChatSessionCreate,
  ChatSessionListResponse,
  ContentBlock,
  ContentBlockListResponse,
} from '@/types';

const API_BASE_URL = 'http://127.0.0.1:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Project API
export const projectsAPI = {
  list: async (): Promise<ProjectListResponse> => {
    const { data } = await api.get<ProjectListResponse>('/projects');
    return data;
  },

  create: async (project: ProjectCreate): Promise<Project> => {
    const { data } = await api.post<Project>('/projects', project);
    return data;
  },

  get: async (id: string): Promise<Project> => {
    const { data } = await api.get<Project>(`/projects/${id}`);
    return data;
  },

  update: async (id: string, project: ProjectUpdate): Promise<Project> => {
    const { data } = await api.put<Project>(`/projects/${id}`, project);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/projects/${id}`);
  },

  getAgentConfig: async (projectId: string): Promise<AgentConfiguration> => {
    const { data } = await api.get<AgentConfiguration>(`/projects/${projectId}/agent-config`);
    return data;
  },

  updateAgentConfig: async (
    projectId: string,
    config: AgentConfigurationUpdate
  ): Promise<AgentConfiguration> => {
    const { data } = await api.put<AgentConfiguration>(
      `/projects/${projectId}/agent-config`,
      config
    );
    return data;
  },

  listAgentTemplates: async (): Promise<any[]> => {
    const { data } = await api.get<any[]>('/projects/templates/list');
    return data;
  },

  getAgentTemplate: async (templateId: string): Promise<any> => {
    const { data } = await api.get<any>(`/projects/templates/${templateId}`);
    return data;
  },

  applyAgentTemplate: async (projectId: string, templateId: string): Promise<AgentConfiguration> => {
    const { data } = await api.post<AgentConfiguration>(
      `/projects/${projectId}/agent-config/apply-template/${templateId}`
    );
    return data;
  },
};

// Chat Sessions API
export const chatSessionsAPI = {
  list: async (projectId?: string): Promise<ChatSessionListResponse> => {
    const params = projectId ? { project_id: projectId } : {};
    const { data } = await api.get<ChatSessionListResponse>('/chats', { params });
    return data;
  },

  create: async (projectId: string, session: ChatSessionCreate): Promise<ChatSession> => {
    const { data } = await api.post<ChatSession>(`/chats?project_id=${projectId}`, session);
    return data;
  },

  get: async (sessionId: string): Promise<ChatSession> => {
    const { data } = await api.get<ChatSession>(`/chats/${sessionId}`);
    return data;
  },

  update: async (sessionId: string, session: Partial<ChatSessionCreate>): Promise<ChatSession> => {
    const { data } = await api.put<ChatSession>(`/chats/${sessionId}`, session);
    return data;
  },

  delete: async (sessionId: string): Promise<void> => {
    await api.delete(`/chats/${sessionId}`);
  },
};

// Content Blocks API (unified message model)
export const contentBlocksAPI = {
  list: async (chatSessionId: string): Promise<ContentBlockListResponse> => {
    const { data } = await api.get<ContentBlockListResponse>(`/chats/${chatSessionId}/blocks`);
    return data;
  },

  get: async (chatSessionId: string, blockId: string): Promise<ContentBlock> => {
    const { data } = await api.get<ContentBlock>(`/chats/${chatSessionId}/blocks/${blockId}`);
    return data;
  },
};

// File API
export const filesAPI = {
  upload: async (projectId: string, file: File): Promise<any> => {
    const formData = new FormData();
    formData.append('file', file);

    const { data } = await api.post(`/files/upload/${projectId}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return data;
  },

  list: async (projectId: string): Promise<any> => {
    const { data } = await api.get(`/files/project/${projectId}`);
    return data;
  },

  download: async (fileId: string): Promise<Blob> => {
    const { data } = await api.get(`/files/${fileId}/download`, {
      responseType: 'blob',
    });
    return data;
  },

  delete: async (fileId: string): Promise<void> => {
    await api.delete(`/files/${fileId}`);
  },
};

// Workspace Files API (for chat session file sidebar)
export interface WorkspaceFile {
  name: string;
  path: string;
  size: number;
  type: 'uploaded' | 'output';
  mime_type: string | null;
}

export interface WorkspaceFilesResponse {
  uploaded: WorkspaceFile[];
  output: WorkspaceFile[];
}

export interface WorkspaceFileContent {
  path: string;
  content: string;
  is_binary: boolean;
  mime_type: string | null;
}

export const workspaceAPI = {
  listFiles: async (sessionId: string): Promise<WorkspaceFilesResponse> => {
    const { data } = await api.get<WorkspaceFilesResponse>(`/chats/${sessionId}/workspace/files`);
    return data;
  },

  getFileContent: async (sessionId: string, path: string): Promise<WorkspaceFileContent> => {
    const { data } = await api.get<WorkspaceFileContent>(`/chats/${sessionId}/workspace/files/content`, {
      params: { path },
    });
    return data;
  },

  downloadFile: async (sessionId: string, path: string): Promise<Blob> => {
    const { data } = await api.get(`/chats/${sessionId}/workspace/files/download`, {
      params: { path },
      responseType: 'blob',
    });
    return data;
  },

  downloadAll: async (sessionId: string, type: 'uploaded' | 'output'): Promise<Blob> => {
    const { data } = await api.get(`/chats/${sessionId}/workspace/download-all`, {
      params: { type },
      responseType: 'blob',
    });
    return data;
  },

  // Upload a workspace file to the project (makes it available to other sessions)
  uploadToProject: async (sessionId: string, path: string, projectId: string): Promise<any> => {
    const { data } = await api.post(`/chats/${sessionId}/workspace/files/upload-to-project`, {
      path,
      project_id: projectId,
    });
    return data;
  },
};

// Sandbox API
export const sandboxAPI = {
  start: async (sessionId: string): Promise<any> => {
    const { data } = await api.post(`/sandbox/${sessionId}/start`);
    return data;
  },

  stop: async (sessionId: string): Promise<any> => {
    const { data } = await api.post(`/sandbox/${sessionId}/stop`);
    return data;
  },

  reset: async (sessionId: string): Promise<any> => {
    const { data} = await api.post(`/sandbox/${sessionId}/reset`);
    return data;
  },

  status: async (sessionId: string): Promise<any> => {
    const { data } = await api.get(`/sandbox/${sessionId}/status`);
    return data;
  },

  execute: async (sessionId: string, command: string, workdir?: string): Promise<any> => {
    const { data } = await api.post(`/sandbox/${sessionId}/execute`, {
      command,
      workdir: workdir || '/workspace',
    });
    return data;
  },
};

// Settings API
export interface ApiKeyStatus {
  provider: string;
  is_configured: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyListResponse {
  api_keys: ApiKeyStatus[];
}

export interface ApiKeyCreate {
  provider: string;
  api_key: string;
}

export interface ApiKeyTestResult {
  valid: boolean;
  message: string;
}

export const settingsAPI = {
  listApiKeys: async (): Promise<ApiKeyListResponse> => {
    const { data } = await api.get<ApiKeyListResponse>('/settings/api-keys');
    return data;
  },

  setApiKey: async (keyData: ApiKeyCreate): Promise<{ message: string }> => {
    const { data } = await api.post('/settings/api-keys', keyData);
    return data;
  },

  deleteApiKey: async (provider: string): Promise<void> => {
    await api.delete(`/settings/api-keys/${provider}`);
  },

  testApiKey: async (provider: string, apiKey: string): Promise<ApiKeyTestResult> => {
    const { data } = await api.post<ApiKeyTestResult>('/settings/api-keys/test', {
      provider,
      api_key: apiKey,
    });
    return data;
  },
};

export default api;
