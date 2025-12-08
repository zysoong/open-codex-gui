/**
 * ChatFileSidebar - File browser sidebar for chat sessions
 *
 * Displays uploaded files and output files from the sandbox workspace.
 * Features:
 * - Drag-and-drop file upload
 * - Collapsible sections for uploaded/output files
 * - File preview with viewer mode
 * - Download individual files or all as zip
 * - Real-time updates when LLM creates new files
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { workspaceAPI, filesAPI, WorkspaceFile, WorkspaceFileContent } from '@/services/api';
import { FileDropZone } from '@/components/common';
import {
  ChevronDown,
  ChevronRight,
  File,
  FileText,
  FileCode,
  Image,
  Download,
  ArrowLeft,
  FolderOpen,
  Package,
  X,
  Upload,
  Check,
} from 'lucide-react';
import './ChatFileSidebar.css';

// Local storage key for sidebar width
const SIDEBAR_WIDTH_KEY = 'chatFileSidebarWidth';

interface ChatFileSidebarProps {
  sessionId: string;
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
  onFileUpdate?: () => void;
}

type ViewMode = 'list' | 'file';

export default function ChatFileSidebar({
  sessionId,
  projectId,
  isOpen,
  onClose,
  onFileUpdate,
}: ChatFileSidebarProps) {
  const queryClient = useQueryClient();
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [selectedFile, setSelectedFile] = useState<WorkspaceFile | null>(null);
  const [uploadedExpanded, setUploadedExpanded] = useState(true);
  const [outputExpanded, setOutputExpanded] = useState(true);

  // Resize state
  const sidebarRef = useRef<HTMLDivElement>(null);
  const [isResizing, setIsResizing] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    const saved = localStorage.getItem(SIDEBAR_WIDTH_KEY);
    return saved ? parseInt(saved, 10) : 25; // Default to 1/4
  });

  // Close animation state
  const [isClosing, setIsClosing] = useState(false);
  const [shouldRender, setShouldRender] = useState(isOpen);

  // Handle open/close with animation
  useEffect(() => {
    if (isOpen) {
      setShouldRender(true);
      setIsClosing(false);
    } else if (shouldRender) {
      // Start closing animation
      setIsClosing(true);
      const timer = setTimeout(() => {
        setShouldRender(false);
        setIsClosing(false);
      }, 200); // Match animation duration
      return () => clearTimeout(timer);
    }
  }, [isOpen, shouldRender]);

  // Handle close with animation
  const handleClose = useCallback(() => {
    setIsClosing(true);
    setTimeout(() => {
      onClose();
    }, 200);
  }, [onClose]);

  // Resize handlers
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!sidebarRef.current) return;

      const containerWidth = window.innerWidth;
      const newWidth = ((containerWidth - e.clientX) / containerWidth) * 100;

      // Clamp between min and max (20% to 50%)
      const clampedWidth = Math.min(Math.max(newWidth, 20), 50);
      setSidebarWidth(clampedWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      // Save to localStorage
      localStorage.setItem(SIDEBAR_WIDTH_KEY, sidebarWidth.toString());
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    // Prevent text selection while resizing
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [isResizing, sidebarWidth]);

  // Fetch workspace files
  const {
    data: filesData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['workspaceFiles', sessionId],
    queryFn: () => workspaceAPI.listFiles(sessionId),
    enabled: !!sessionId && isOpen,
    staleTime: 30000, // 30 seconds
    retry: 1,
  });

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: (file: File) => filesAPI.upload(projectId, file),
    onSuccess: () => {
      // Invalidate both project files and workspace files
      queryClient.invalidateQueries({ queryKey: ['files', projectId] });
      queryClient.invalidateQueries({ queryKey: ['workspaceFiles', sessionId] });
    },
  });

  const handleUpload = useCallback(async (file: File) => {
    await uploadMutation.mutateAsync(file);
  }, [uploadMutation]);

  // Fetch selected file content
  const {
    data: fileContent,
    isLoading: isLoadingContent,
  } = useQuery({
    queryKey: ['workspaceFileContent', sessionId, selectedFile?.path],
    queryFn: () => workspaceAPI.getFileContent(sessionId, selectedFile!.path),
    enabled: !!sessionId && !!selectedFile && viewMode === 'file',
    staleTime: 60000, // 1 minute
  });

  // Expose refetch method for parent to call on WebSocket events
  useEffect(() => {
    if (onFileUpdate) {
      // Store refetch in a ref that parent can access
      (window as any).__chatFileSidebarRefetch = refetch;
    }
    return () => {
      delete (window as any).__chatFileSidebarRefetch;
    };
  }, [refetch, onFileUpdate]);

  const handleFileClick = useCallback((file: WorkspaceFile) => {
    setSelectedFile(file);
    setViewMode('file');
  }, []);

  const handleBackToList = useCallback(() => {
    setViewMode('list');
    setSelectedFile(null);
  }, []);

  const handleDownloadFile = useCallback(async (file: WorkspaceFile, e?: React.MouseEvent) => {
    e?.stopPropagation();
    try {
      const blob = await workspaceAPI.downloadFile(sessionId, file.path);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.name;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Download failed:', err);
    }
  }, [sessionId]);

  const handleDownloadAll = useCallback(async (type: 'uploaded' | 'output') => {
    try {
      const blob = await workspaceAPI.downloadAll(sessionId, type);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${type}_files.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Download all failed:', err);
    }
  }, [sessionId]);

  const getFileIcon = (file: WorkspaceFile) => {
    const ext = file.name.split('.').pop()?.toLowerCase();
    const mimeType = file.mime_type || '';

    if (mimeType.startsWith('image/')) {
      return <Image size={16} />;
    }
    if (['py', 'js', 'ts', 'tsx', 'jsx', 'json', 'html', 'css', 'md'].includes(ext || '')) {
      return <FileCode size={16} />;
    }
    if (['txt', 'log', 'csv'].includes(ext || '')) {
      return <FileText size={16} />;
    }
    return <File size={16} />;
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const renderFileContent = (content: WorkspaceFileContent) => {
    if (content.is_binary && content.content.startsWith('data:image/')) {
      return (
        <div className="file-preview-image">
          <img src={content.content} alt={selectedFile?.name} />
        </div>
      );
    }

    // Text content
    return (
      <pre className="file-preview-text">
        <code>{content.content}</code>
      </pre>
    );
  };

  if (!shouldRender) return null;

  const uploadedFiles = filesData?.uploaded || [];
  const outputFiles = filesData?.output || [];

  return (
    <div
      ref={sidebarRef}
      className={`chat-file-sidebar ${isClosing ? 'closing' : ''}`}
      style={{ width: `${sidebarWidth}%` }}
    >
      {/* Resize handle */}
      <div
        className={`sidebar-resize-handle ${isResizing ? 'resizing' : ''}`}
        onMouseDown={handleMouseDown}
      />

      {/* Header */}
      <div className="sidebar-header">
        {viewMode === 'list' ? (
          <>
            <h3>Files</h3>
            <button className="sidebar-close-btn" onClick={handleClose} title="Close sidebar">
              <X size={18} />
            </button>
          </>
        ) : (
          <>
            <button className="back-to-list-btn" onClick={handleBackToList}>
              <ArrowLeft size={16} />
              Back
            </button>
            <button className="sidebar-close-btn" onClick={handleClose} title="Close sidebar">
              <X size={18} />
            </button>
          </>
        )}
      </div>

      {/* Content */}
      <div className="sidebar-content">
        {viewMode === 'list' ? (
          <>
            {isLoading && (
              <div className="sidebar-loading">Loading files...</div>
            )}

            {error && (
              <div className="sidebar-error">
                No files available. Start a conversation to create files.
              </div>
            )}

            {!isLoading && !error && (
              <>
                {/* Upload Drop Zone */}
                <div className="sidebar-upload-section">
                  <FileDropZone
                    onUpload={handleUpload}
                    isUploading={uploadMutation.isPending}
                    compact
                  />
                </div>

                {/* Uploaded Files Section */}
                <div className="file-section">
                  <button
                    className="section-header"
                    onClick={() => setUploadedExpanded(!uploadedExpanded)}
                  >
                    {uploadedExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    <FolderOpen size={16} />
                    <span>Uploaded Files</span>
                    <span className="file-count">{uploadedFiles.length}</span>
                    {uploadedFiles.length > 0 && (
                      <button
                        className="download-all-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDownloadAll('uploaded');
                        }}
                        title="Download all as ZIP"
                      >
                        <Package size={14} />
                      </button>
                    )}
                  </button>
                  {uploadedExpanded && (
                    <div className="file-list">
                      {uploadedFiles.length === 0 ? (
                        <div className="file-list-empty">No uploaded files</div>
                      ) : (
                        uploadedFiles.map((file) => (
                          <div
                            key={file.path}
                            className="file-item"
                            onClick={() => handleFileClick(file)}
                          >
                            <div className="file-icon">{getFileIcon(file)}</div>
                            <div className="file-info">
                              <div className="file-name">{file.name}</div>
                              <div className="file-size">{formatFileSize(file.size)}</div>
                            </div>
                            <button
                              className="file-download-btn"
                              onClick={(e) => handleDownloadFile(file, e)}
                              title="Download"
                            >
                              <Download size={14} />
                            </button>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>

                {/* Output Files Section */}
                <div className="file-section">
                  <button
                    className="section-header"
                    onClick={() => setOutputExpanded(!outputExpanded)}
                  >
                    {outputExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    <FolderOpen size={16} />
                    <span>Output Files</span>
                    <span className="file-count">{outputFiles.length}</span>
                    {outputFiles.length > 0 && (
                      <button
                        className="download-all-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDownloadAll('output');
                        }}
                        title="Download all as ZIP"
                      >
                        <Package size={14} />
                      </button>
                    )}
                  </button>
                  {outputExpanded && (
                    <div className="file-list">
                      {outputFiles.length === 0 ? (
                        <div className="file-list-empty">No output files yet</div>
                      ) : (
                        outputFiles.map((file) => (
                          <div
                            key={file.path}
                            className="file-item"
                            onClick={() => handleFileClick(file)}
                          >
                            <div className="file-icon">{getFileIcon(file)}</div>
                            <div className="file-info">
                              <div className="file-name">{file.name}</div>
                              <div className="file-size">{formatFileSize(file.size)}</div>
                            </div>
                            <button
                              className="file-download-btn"
                              onClick={(e) => handleDownloadFile(file, e)}
                              title="Download"
                            >
                              <Download size={14} />
                            </button>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
          </>
        ) : (
          /* File View Mode */
          <div className="file-viewer">
            <div className="file-viewer-header">
              <div className="file-viewer-path">{selectedFile?.path}</div>
              <button
                className="file-viewer-download"
                onClick={() => selectedFile && handleDownloadFile(selectedFile)}
                title="Download file"
              >
                <Download size={16} />
              </button>
            </div>
            <div className="file-viewer-content">
              {isLoadingContent ? (
                <div className="file-viewer-loading">Loading file content...</div>
              ) : fileContent ? (
                renderFileContent(fileContent)
              ) : (
                <div className="file-viewer-error">Failed to load file content</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Export a method to trigger refresh from outside
export function refreshWorkspaceFiles() {
  const refetch = (window as any).__chatFileSidebarRefetch;
  if (refetch) {
    refetch();
  }
}
