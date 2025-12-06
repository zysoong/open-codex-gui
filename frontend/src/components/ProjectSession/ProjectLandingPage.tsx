import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { projectsAPI, chatSessionsAPI } from '@/services/api';
import { useChatStore } from '@/stores/chatStore';
import AgentConfigPanel from './AgentConfigPanel';
import FilePanel from './FilePanel';
import './ProjectLandingPage.css';

export default function ProjectLandingPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { setActiveSession } = useChatStore();
  const [message, setMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [showAgentConfig, setShowAgentConfig] = useState(false);
  const [showFiles, setShowFiles] = useState(false);

  // Fetch project
  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => projectsAPI.get(projectId!),
    enabled: !!projectId,
  });

  // Fetch chat sessions
  const { data: sessionsData } = useQuery({
    queryKey: ['chatSessions', projectId],
    queryFn: () => chatSessionsAPI.list(projectId!),
    enabled: !!projectId,
  });

  // Create session mutation
    useMutation({
        mutationFn: (name: string) => chatSessionsAPI.create(projectId!, { name }),
        onSuccess: (newSession) => {
            queryClient.invalidateQueries({ queryKey: ['chatSessions', projectId] });
            setActiveSession(newSession.id);
            // Navigate to chat session page
            navigate(`/projects/${projectId}/chat/${newSession.id}`);
        },
    });

    const handleQuickStart = async () => {
        if (!message.trim() || isSending) return;

        setIsSending(true);
        try {
            // Create new chat session with timestamp
            const sessionName = `Chat ${new Date().toLocaleString('en-US', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            })}`;

            const newSession = await chatSessionsAPI.create(projectId!, { name: sessionName });

            // Store the message to be sent
            sessionStorage.setItem('pendingMessage', message);

            // Navigate to chat session (message will be sent there)
            setActiveSession(newSession.id);
            navigate(`/projects/${projectId}/chat/${newSession.id}`);
        } catch (error) {
            console.error('Failed to create session:', error);
            setIsSending(false);
        }
    };
    const handleSessionClick = (sessionId: string) => {
    setActiveSession(sessionId);
    navigate(`/projects/${projectId}/chat/${sessionId}`);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleQuickStart();
    }
  };

  const sessions = sessionsData?.chat_sessions || [];

  return (
    <div className="project-landing">
      {/* Left side - 70% */}
      <div className="landing-main">
        <div className="landing-header">
          <button className="back-btn" onClick={() => navigate('/')}>
            ← Back to Projects
          </button>
          <h1>{project?.name || 'Project'}</h1>
          {project?.description && <p className="project-desc">{project.description}</p>}
        </div>

        {/* Quick Start Input */}
        <div className="quick-start-section">
          <div className="quick-start-container">
            <textarea
              className="quick-start-input"
              placeholder="How can I help you today?"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              rows={3}
              disabled={isSending}
            />
            <button
              className="send-btn"
              onClick={handleQuickStart}
              disabled={!message.trim() || isSending}
            >
              {isSending ? (
                <span className="spinner">⏳</span>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path
                    d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </button>
          </div>
          <p className="quick-start-hint">
            Press Enter to send, or Shift+Enter for new line
          </p>
        </div>

        {/* Chat Sessions List */}
        <div className="sessions-list-section">
          <h2>Recent Conversations</h2>
          {sessions.length === 0 ? (
            <div className="empty-sessions">
              <p>No conversations yet. Start one above!</p>
            </div>
          ) : (
            <div className="sessions-list">
              {sessions.map((session) => (
                <div
                  key={session.id}
                  className="session-card"
                  onClick={() => handleSessionClick(session.id)}
                >
                  <div className="session-header">
                    <h3>{session.name}</h3>
                    <span className="session-date">
                      {new Date(session.created_at).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                  {session.updated_at !== session.created_at && (
                    <p className="session-updated">
                      Last updated: {new Date(session.updated_at).toLocaleString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right side - 30% */}
      <div className="landing-sidebar">
        <div className="sidebar-section">
          <div
            className="sidebar-section-header"
            onClick={() => setShowAgentConfig(!showAgentConfig)}
          >
            <h3>Agent Configuration</h3>
            <span className="toggle-icon">{showAgentConfig ? '▼' : '▶'}</span>
          </div>
          {showAgentConfig && (
            <div className="sidebar-section-content">
              <AgentConfigPanel projectId={projectId!} />
            </div>
          )}
        </div>

        <div className="sidebar-section">
          <div
            className="sidebar-section-header"
            onClick={() => setShowFiles(!showFiles)}
          >
            <h3>Project Files</h3>
            <span className="toggle-icon">{showFiles ? '▼' : '▶'}</span>
          </div>
          {showFiles && (
            <div className="sidebar-section-content">
              <FilePanel projectId={projectId!} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
