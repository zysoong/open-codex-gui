import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { projectsAPI } from '@/services/api';
import './AgentConfigPanel.css';

interface AgentConfigPanelProps {
  projectId: string;
}

interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  agent_type: string;
  enabled_tools: string[];
}

interface AgentConfig {
  agent_type: string;
  system_instructions: string | null;
  enabled_tools: string[];
  llm_provider: string;
  llm_model: string;
  llm_config: Record<string, any>;
}

const AVAILABLE_TOOLS = [
  { id: 'bash', name: 'Bash', description: 'Execute shell commands' },
  { id: 'file_read', name: 'File Read', description: 'Read file contents' },
  { id: 'file_write', name: 'File Write', description: 'Create/overwrite files' },
  { id: 'file_edit', name: 'File Edit', description: 'Edit existing files' },
  { id: 'search', name: 'Search', description: 'Search for files and content' },
];

const LLM_PROVIDERS = [
  {
    id: 'openai',
    name: 'OpenAI',
    models: [
      // GPT-5 Series (August 2025 - Latest)
      'gpt-5-2025-08-07',              // GPT-5 flagship
      'gpt-5-mini-2025-08-07',         // GPT-5 mini
      // GPT-4.1 Series (April 2025)
      'gpt-4.1-2025-04-14',            // GPT-4.1 flagship
      'gpt-4.1-mini-2025-04-14',       // GPT-4.1 mini
      'gpt-4.1-nano-2025-04-14',       // GPT-4.1 nano (smallest)
      // Reasoning Models (o-series)
      'o3-2025-04-16',                 // o3 reasoning
      'o3-mini',                       // o3 mini reasoning
      'o4-mini-2025-04-16',            // o4-mini reasoning
      // GPT-4o Series (Still available)
      'gpt-4o',                        // GPT-4o multimodal
      'gpt-4o-mini',                   // GPT-4o mini
      'gpt-4-turbo',                   // GPT-4 Turbo (legacy)
    ]
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    models: [
      // Claude 4.5 Series (Latest - Nov 2025)
      'claude-sonnet-4-5-20250929',    // Sonnet 4.5 (most capable)
      'claude-haiku-4-5-20251001',     // Haiku 4.5 (fast)
      // Claude 4.1 Series (Aug 2025)
      'claude-opus-4-1-20250805',      // Opus 4.1 (agentic tasks)
      // Aliases (auto-update to latest)
      'claude-sonnet-4-5',             // Sonnet 4.5 alias
      'claude-haiku-4-5',              // Haiku 4.5 alias
      'claude-opus-4-1',               // Opus 4.1 alias
    ]
  },
  {
    id: 'azure',
    name: 'Azure OpenAI',
    models: [
      'gpt-5-2025-08-07',
      'gpt-4.1-2025-04-14',
      'gpt-4o',
      'gpt-4-turbo',
      'gpt-4',
      'gpt-35-turbo'
    ]
  },
];

export default function AgentConfigPanel({ projectId }: AgentConfigPanelProps) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'general' | 'tools' | 'instructions' | 'templates'>('general');
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Local state for form
  const [formData, setFormData] = useState<Partial<AgentConfig>>({});
  const [hasChanges, setHasChanges] = useState(false);

  // Fetch agent configuration
  const { data: config, isLoading } = useQuery({
    queryKey: ['agentConfig', projectId],
    queryFn: () => projectsAPI.getAgentConfig(projectId),
  });

  // Fetch templates
  const { data: templates } = useQuery({
    queryKey: ['agentTemplates'],
    queryFn: () => projectsAPI.listAgentTemplates(),
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: Partial<AgentConfig>) =>
      projectsAPI.updateAgentConfig(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agentConfig', projectId] });
      setHasChanges(false);
    },
  });

  // Apply template mutation
  const applyTemplateMutation = useMutation({
    mutationFn: (templateId: string) =>
      projectsAPI.applyAgentTemplate(projectId, templateId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agentConfig', projectId] });
      setHasChanges(false);
    },
  });

  // Initialize form data from config
  useEffect(() => {
    if (config) {
      setFormData({
        agent_type: config.agent_type,
        system_instructions: config.system_instructions,
        enabled_tools: config.enabled_tools || [],
        llm_provider: config.llm_provider,
        llm_model: config.llm_model,
        llm_config: config.llm_config || {},
      });
    }
  }, [config]);

  const handleFieldChange = (field: keyof AgentConfig, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  const handleToolToggle = (toolId: string) => {
    const currentTools = formData.enabled_tools || [];
    const newTools = currentTools.includes(toolId)
      ? currentTools.filter(t => t !== toolId)
      : [...currentTools, toolId];
    handleFieldChange('enabled_tools', newTools);
  };

  const handleSave = () => {
    updateMutation.mutate(formData);
  };

  const handleReset = () => {
    if (config) {
      setFormData({
        agent_type: config.agent_type,
        system_instructions: config.system_instructions,
        enabled_tools: config.enabled_tools || [],
        llm_provider: config.llm_provider,
        llm_model: config.llm_model,
        llm_config: config.llm_config || {},
      });
      setHasChanges(false);
    }
  };

  const handleApplyTemplate = (templateId: string) => {
    if (confirm(`Apply template? This will override current configuration.`)) {
      applyTemplateMutation.mutate(templateId);
    }
  };

  const getSelectedProviderModels = () => {
    const provider = LLM_PROVIDERS.find(p => p.id === formData.llm_provider);
    return provider?.models || [];
  };

  if (isLoading) {
    return <div className="agent-config-panel loading">Loading configuration...</div>;
  }

  return (
    <div className="agent-config-panel">
      {hasChanges && (
        <div className="panel-header">
          <div className="unsaved-indicator">
            <span className="dot"></span>
            Unsaved changes
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="config-tabs">
        <button
          className={`tab ${activeTab === 'general' ? 'active' : ''}`}
          onClick={() => setActiveTab('general')}
        >
          General
        </button>
        <button
          className={`tab ${activeTab === 'tools' ? 'active' : ''}`}
          onClick={() => setActiveTab('tools')}
        >
          Tools
        </button>
        <button
          className={`tab ${activeTab === 'instructions' ? 'active' : ''}`}
          onClick={() => setActiveTab('instructions')}
        >
          Instructions
        </button>
        <button
          className={`tab ${activeTab === 'templates' ? 'active' : ''}`}
          onClick={() => setActiveTab('templates')}
        >
          Templates
        </button>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'general' && (
          <div className="general-tab">
            <p className="tab-description">
              Configure the LLM provider and model for your agent. The agent will automatically set up the appropriate sandbox environment based on your tasks.
            </p>

            {/* LLM Provider */}
            <div className="form-section">
              <label className="section-label">LLM Provider</label>
              <select
                className="select-input"
                value={formData.llm_provider || 'openai'}
                onChange={(e) => {
                  handleFieldChange('llm_provider', e.target.value);
                  // Reset model when provider changes
                  const provider = LLM_PROVIDERS.find(p => p.id === e.target.value);
                  if (provider) {
                    handleFieldChange('llm_model', provider.models[0]);
                  }
                }}
              >
                {LLM_PROVIDERS.map(provider => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
              </select>
            </div>

            {/* LLM Model */}
            <div className="form-section">
              <label className="section-label">Model</label>
              <select
                className="select-input"
                value={formData.llm_model || 'gpt-4'}
                onChange={(e) => handleFieldChange('llm_model', e.target.value)}
              >
                {getSelectedProviderModels().map(model => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            </div>

            {/* Advanced Settings (Collapsible) */}
            <div className="form-section advanced-section">
              <button
                type="button"
                className="advanced-toggle"
                onClick={() => setShowAdvanced(!showAdvanced)}
              >
                <span>{showAdvanced ? '▼' : '▶'}</span>
                Advanced Settings
              </button>

              {showAdvanced && (
                <div className="advanced-content">
                  <div className="form-section">
                    <label className="section-label">Temperature</label>
                    <div className="slider-container">
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.1"
                        value={formData.llm_config?.temperature ?? 1.0}
                        onChange={(e) => handleFieldChange('llm_config', {
                          ...formData.llm_config,
                          temperature: parseFloat(e.target.value)
                        })}
                        className="slider"
                      />
                      <span className="slider-value">
                        {formData.llm_config?.temperature ?? 1.0}
                      </span>
                    </div>
                    <p className="field-description">
                      Lower values make output more focused, higher values more creative. Default: 1.0
                    </p>
                  </div>

                  <div className="form-section">
                    <label className="section-label">Max Tokens</label>
                    <input
                      type="number"
                      className="text-input"
                      value={formData.llm_config?.max_tokens ?? 8192}
                      onChange={(e) => handleFieldChange('llm_config', {
                        ...formData.llm_config,
                        max_tokens: parseInt(e.target.value)
                      })}
                      min="256"
                      max="200000"
                      step="256"
                    />
                    <p className="field-description">
                      Maximum response length (higher values = longer responses). Default: 8192
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'tools' && (
          <div className="tools-tab">
            <p className="tab-description">
              Enable or disable tools that the agent can use. More tools give more capabilities but may increase costs.
            </p>
            <div className="tools-grid">
              {AVAILABLE_TOOLS.map(tool => (
                <div
                  key={tool.id}
                  className={`tool-card ${formData.enabled_tools?.includes(tool.id) ? 'enabled' : 'disabled'}`}
                  onClick={() => handleToolToggle(tool.id)}
                >
                  <div className="tool-header">
                    <input
                      type="checkbox"
                      checked={formData.enabled_tools?.includes(tool.id) || false}
                      onChange={() => handleToolToggle(tool.id)}
                      onClick={(e) => e.stopPropagation()}
                    />
                    <span className="tool-name">{tool.name}</span>
                  </div>
                  <p className="tool-description">{tool.description}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'instructions' && (
          <div className="instructions-tab">
            <label className="section-label">System Instructions</label>
            <p className="tab-description">
              Custom instructions that guide the agent's behavior and personality.
            </p>
            <textarea
              className="instructions-textarea"
              value={formData.system_instructions || ''}
              onChange={(e) => handleFieldChange('system_instructions', e.target.value)}
              placeholder="Enter custom system instructions for the agent..."
              rows={15}
            />
            <p className="field-description">
              Examples: "You are a senior Python developer", "Focus on performance optimization", "Write detailed comments"
            </p>
          </div>
        )}

        {activeTab === 'templates' && (
          <div className="templates-tab">
            <p className="tab-description">
              Quick-start templates with pre-configured settings for common use cases.
            </p>
            <div className="templates-grid">
              {templates?.map((template: AgentTemplate) => (
                <div key={template.id} className="template-card">
                  <div className="template-header">
                    <h4>{template.name}</h4>
                  </div>
                  <p className="template-description">{template.description}</p>
                  <div className="template-tools">
                    {template.enabled_tools.map(tool => (
                      <span key={tool} className="tool-badge">{tool}</span>
                    ))}
                  </div>
                  <button
                    className="apply-template-btn"
                    onClick={() => handleApplyTemplate(template.id)}
                    disabled={applyTemplateMutation.isPending}
                  >
                    {applyTemplateMutation.isPending ? 'Applying...' : 'Apply Template'}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="panel-footer">
        <button
          className="btn-secondary"
          onClick={handleReset}
          disabled={!hasChanges}
        >
          Reset
        </button>
        <button
          className="btn-primary"
          onClick={handleSave}
          disabled={!hasChanges || updateMutation.isPending}
        >
          {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
}
