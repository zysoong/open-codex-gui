/**
 * DefaultToolFallback - Default component for rendering tool calls
 *
 * This component properly handles streaming of tool arguments and results
 * using assistant-ui's ToolCallMessagePartComponent interface.
 */

import React from 'react';
import type { ToolCallMessagePartProps } from '@assistant-ui/react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';

const getFileExtension = (filePath: string): string => {
  const match = filePath.match(/\.([^.]+)$/);
  return match ? match[1].toLowerCase() : '';
};

const getLanguageFromExtension = (ext: string): string => {
  const langMap: { [key: string]: string } = {
    'js': 'javascript', 'jsx': 'javascript', 'ts': 'typescript', 'tsx': 'typescript',
    'py': 'python', 'rb': 'ruby', 'java': 'java', 'cpp': 'cpp', 'c': 'c',
    'cs': 'csharp', 'go': 'go', 'rs': 'rust', 'php': 'php', 'swift': 'swift',
    'kt': 'kotlin', 'scala': 'scala', 'sh': 'bash', 'bash': 'bash', 'zsh': 'bash',
    'yml': 'yaml', 'yaml': 'yaml', 'json': 'json', 'xml': 'xml', 'html': 'html',
    'css': 'css', 'scss': 'scss', 'sass': 'sass', 'sql': 'sql',
    'md': 'markdown', 'markdown': 'markdown',
  };
  return langMap[ext] || ext;
};

const formatValue = (value: any): string => {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch (e) {
    // Handle circular references or other stringify errors
    return String(value);
  }
};

export const DefaultToolFallback: React.FC<ToolCallMessagePartProps> = ({
  toolName,
  args,
  argsText,
  result,
  isError,
  status,
}) => {
  const isRunning = status?.type === 'running';
  const isComplete = status?.type === 'complete';
  const hasResult = result !== undefined;

  // Special handling for file write operations
  const isFileWrite = toolName && (
    toolName.toLowerCase().includes('file_write') ||
    toolName.toLowerCase().includes('write_file') ||
    toolName.toLowerCase().includes('writefile')
  );

  // Parse args for file operations
  let filePath = '';
  let content = '';
  if (isFileWrite && args) {
    try {
      const parsedArgs = typeof args === 'string' ? JSON.parse(args) : args;
      filePath = parsedArgs.file_path || parsedArgs.path || parsedArgs.filename || '';
      content = parsedArgs.content || parsedArgs.data || '';
    } catch (e) {
      // During streaming, args might be incomplete JSON - that's ok
      // We'll just not show the special file rendering until args are complete
    }
  }

  return (
    <div className="tool-call-container" style={{
      marginTop: '12px',
      marginBottom: '12px',
      borderRadius: '8px',
      overflow: 'hidden',
      border: '1px solid #e5e7eb',
    }}>
      {/* Tool Header */}
      <div className="tool-call-header" style={{
        padding: '12px 16px',
        background: isRunning
          ? 'linear-gradient(to right, #fef3c7, #fde68a)'
          : '#f9fafb',
        borderBottom: '1px solid #e5e7eb',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
      }}>
        <span className="tool-icon" style={{ fontSize: '16px' }}>
          {isRunning ? '⚙️' : '🔧'}
        </span>
        <strong style={{ color: '#111827' }}>
          {toolName}
        </strong>
        {isRunning && (
          <span className="tool-status" style={{
            fontSize: '12px',
            color: '#92400e',
            marginLeft: 'auto',
            animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
          }}>
            Running...
          </span>
        )}
      </div>

      {/* Tool Arguments */}
      {(args || argsText) && (
        <div className="tool-call-args" style={{
          padding: '16px',
          background: '#ffffff',
          borderBottom: hasResult ? '1px solid #e5e7eb' : 'none',
        }}>
          <div style={{
            marginBottom: '8px',
            fontSize: '12px',
            fontWeight: 600,
            color: '#6b7280',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}>
            Arguments {isRunning && !hasResult && '(streaming...)'}
          </div>

          {isFileWrite && filePath ? (
            <div>
              <div style={{
                marginBottom: '8px',
                fontSize: '14px',
                color: '#374151',
              }}>
                <strong>File:</strong>{' '}
                <code style={{
                  padding: '2px 6px',
                  background: '#f3f4f6',
                  borderRadius: '4px',
                  fontFamily: 'monospace',
                }}>{filePath}</code>
              </div>
              {content && (
                <SyntaxHighlighter
                  language={getLanguageFromExtension(getFileExtension(filePath))}
                  style={oneLight}
                  customStyle={{
                    margin: '8px 0',
                    borderRadius: '6px',
                    fontSize: '13px',
                    maxHeight: '400px',
                  }}
                >
                  {content}
                </SyntaxHighlighter>
              )}
            </div>
          ) : (
            <pre style={{
              margin: 0,
              padding: '12px',
              background: '#f9fafb',
              borderRadius: '6px',
              fontSize: '13px',
              fontFamily: 'monospace',
              overflow: 'auto',
              maxHeight: '300px',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}>
              {argsText || formatValue(args)}
            </pre>
          )}
        </div>
      )}

      {/* Tool Result */}
      {hasResult && (
        <div className="tool-call-result" style={{
          padding: '16px',
          background: isError ? '#fef2f2' : '#f0fdf4',
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '8px',
          }}>
            <span style={{ fontSize: '16px' }}>
              {isError ? '❌' : '✅'}
            </span>
            <strong style={{
              color: isError ? '#991b1b' : '#166534',
              fontSize: '14px',
            }}>
              {isError ? 'Error' : 'Result'}
            </strong>
            {isRunning && (
              <span style={{
                fontSize: '12px',
                color: isError ? '#991b1b' : '#166534',
                marginLeft: '8px',
              }}>
                (streaming...)
              </span>
            )}
          </div>
          <pre style={{
            margin: 0,
            padding: '12px',
            background: '#ffffff',
            border: `1px solid ${isError ? '#fca5a5' : '#86efac'}`,
            borderRadius: '6px',
            fontSize: '13px',
            fontFamily: 'monospace',
            overflow: 'auto',
            maxHeight: '300px',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            color: isError ? '#7f1d1d' : '#14532d',
          }}>
            {formatValue(result)}
          </pre>
        </div>
      )}

      {/* Incomplete Status */}
      {status?.type === 'incomplete' && (
        <div style={{
          padding: '16px',
          background: '#fef2f2',
          borderTop: '1px solid #fca5a5',
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            color: '#991b1b',
          }}>
            <span>⚠️</span>
            <strong>Incomplete:</strong>
            <span>{status.reason}</span>
          </div>
        </div>
      )}

      {/* Requires Action Status */}
      {status?.type === 'requires-action' && (
        <div style={{
          padding: '16px',
          background: '#fef3c7',
          borderTop: '1px solid #fcd34d',
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            color: '#92400e',
          }}>
            <span>⏸️</span>
            <strong>Action Required:</strong>
            <span>{status.reason}</span>
          </div>
        </div>
      )}
    </div>
  );
};