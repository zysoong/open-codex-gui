"""Chat session and message API routes."""

import io
import zipfile
import base64
import mimetypes
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.core.storage.database import get_db
from app.models.database import ChatSession, Project, ContentBlock, File
from app.core.storage.file_manager import get_file_manager
from app.models.schemas import (
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatSessionResponse,
    ChatSessionListResponse,
    ContentBlockResponse,
    ContentBlockListResponse,
)
from app.api.websocket import ChatWebSocketHandler
from app.core.sandbox import get_container_manager
from app.core.storage.storage_factory import get_storage

router = APIRouter(prefix="/chats", tags=["chat"])


# Workspace file models
class WorkspaceFile(BaseModel):
    """Model for a file in the workspace."""
    name: str
    path: str
    size: int
    type: str  # 'uploaded' or 'output'
    mime_type: Optional[str] = None


class WorkspaceFilesResponse(BaseModel):
    """Response model for workspace files."""
    uploaded: List[WorkspaceFile]
    output: List[WorkspaceFile]


# Chat Session endpoints
@router.get("", response_model=ChatSessionListResponse)
async def list_chat_sessions(
    project_id: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """List chat sessions, optionally filtered by project."""
    query = select(ChatSession)

    if project_id:
        query = query.where(ChatSession.project_id == project_id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Get chat sessions
    query = query.offset(skip).limit(limit).order_by(ChatSession.created_at.desc())
    result = await db.execute(query)
    sessions = result.scalars().all()

    return ChatSessionListResponse(
        chat_sessions=[ChatSessionResponse.model_validate(s) for s in sessions],
        total=total,
    )


@router.post("", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    project_id: str,
    session_data: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new chat session."""
    # Verify project exists
    project_query = select(Project).where(Project.id == project_id)
    project_result = await db.execute(project_query)
    project = project_result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with id {project_id} not found",
        )

    # Create chat session
    session = ChatSession(
        project_id=project_id,
        name=session_data.name,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return ChatSessionResponse.model_validate(session)


@router.get("/{session_id}", response_model=ChatSessionResponse)
async def get_chat_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a chat session by ID."""
    query = select(ChatSession).where(ChatSession.id == session_id)
    result = await db.execute(query)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session with id {session_id} not found",
        )

    return ChatSessionResponse.model_validate(session)


@router.put("/{session_id}", response_model=ChatSessionResponse)
async def update_chat_session(
    session_id: str,
    session_data: ChatSessionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a chat session."""
    query = select(ChatSession).where(ChatSession.id == session_id)
    result = await db.execute(query)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session with id {session_id} not found",
        )

    # Update fields
    update_data = session_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(session, field, value)

    await db.commit()
    await db.refresh(session)

    return ChatSessionResponse.model_validate(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a chat session."""
    query = select(ChatSession).where(ChatSession.id == session_id)
    result = await db.execute(query)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session with id {session_id} not found",
        )

    await db.delete(session)
    await db.commit()


# Content Blocks endpoints (unified model)
@router.get("/{session_id}/blocks", response_model=ContentBlockListResponse)
async def list_content_blocks(
    session_id: str,
    skip: int = 0,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
):
    """
    List content blocks in a chat session, ordered by sequence_number.

    This is the new unified API that replaces the separate messages + agent_actions model.
    Each content block represents a single piece of content (text, tool call, or tool result)
    with guaranteed ordering via sequence_number.
    """
    # Verify session exists
    session_query = select(ChatSession).where(ChatSession.id == session_id)
    session_result = await db.execute(session_query)
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session with id {session_id} not found",
        )

    # Get total count
    count_query = select(func.count()).select_from(ContentBlock).where(
        ContentBlock.chat_session_id == session_id
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Get content blocks ordered by sequence_number
    query = (
        select(ContentBlock)
        .where(ContentBlock.chat_session_id == session_id)
        .order_by(ContentBlock.sequence_number.asc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    blocks = result.scalars().all()

    return ContentBlockListResponse(
        blocks=[ContentBlockResponse.model_validate(b) for b in blocks],
        total=total,
    )


@router.get("/{session_id}/blocks/{block_id}", response_model=ContentBlockResponse)
async def get_content_block(
    session_id: str,
    block_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific content block by ID."""
    query = select(ContentBlock).where(
        ContentBlock.id == block_id,
        ContentBlock.chat_session_id == session_id
    )
    result = await db.execute(query)
    block = result.scalar_one_or_none()

    if not block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Content block with id {block_id} not found in session {session_id}",
        )

    return ContentBlockResponse.model_validate(block)


# WebSocket endpoint for streaming chat
@router.websocket("/{session_id}/stream")
async def chat_stream(
    websocket: WebSocket,
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """WebSocket endpoint for streaming chat responses."""
    handler = ChatWebSocketHandler(websocket, db)
    await handler.handle_connection(session_id)


# Workspace file endpoints
async def _get_container_for_session(session_id: str, raise_if_not_found: bool = True):
    """Helper to get container for a session."""
    manager = get_container_manager()
    container = await manager.get_container(session_id)
    if not container and raise_if_not_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sandbox not running. The environment must be set up first.",
        )
    return container


async def _list_files_from_storage(session_id: str, directory: str, file_type: str) -> List[WorkspaceFile]:
    """List files using storage backend (works even when container is stopped)."""
    files = []
    storage = get_storage()

    try:
        file_infos = await storage.list_files(session_id, directory)
        for info in file_infos:
            # info.path is full path like /workspace/out/file.py
            name = info.path.split('/')[-1]
            mime_type, _ = mimetypes.guess_type(name)
            files.append(WorkspaceFile(
                name=name,
                path=info.path,
                size=info.size,
                type=file_type,
                mime_type=mime_type,
            ))
    except Exception as e:
        print(f"Error listing files from storage: {e}")

    return files


async def _list_files_in_directory(container, directory: str, file_type: str) -> List[WorkspaceFile]:
    """List files in a directory within the container."""
    files = []

    # Use find command to list files with size
    cmd = f"find {directory} -maxdepth 1 -type f -printf '%f\\t%s\\n' 2>/dev/null || true"
    exit_code, stdout, stderr = await container.execute(cmd, workdir="/workspace", timeout=10)

    if stdout.strip():
        for line in stdout.strip().split('\n'):
            if '\t' in line:
                parts = line.split('\t')
                name = parts[0]
                size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                path = f"{directory}/{name}"
                mime_type, _ = mimetypes.guess_type(name)
                files.append(WorkspaceFile(
                    name=name,
                    path=path,
                    size=size,
                    type=file_type,
                    mime_type=mime_type,
                ))

    return files


@router.get("/{session_id}/workspace/files", response_model=WorkspaceFilesResponse)
async def list_workspace_files(session_id: str, db: AsyncSession = Depends(get_db)):
    """List all files in the workspace (uploaded and output)."""
    # Get session to find project_id
    session_query = select(ChatSession).where(ChatSession.id == session_id)
    session_result = await db.execute(session_query)
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Get project files from database (always up-to-date, not dependent on container)
    files_query = select(File).where(File.project_id == session.project_id)
    files_result = await db.execute(files_query)
    project_files = files_result.scalars().all()

    uploaded = [
        WorkspaceFile(
            name=f.filename,
            path=f"/workspace/project_files/{f.filename}",  # Virtual path for display
            size=f.size,
            type="uploaded",
            mime_type=f.mime_type,
        )
        for f in project_files
    ]

    # Get output files from container or storage
    container = await _get_container_for_session(session_id, raise_if_not_found=False)

    if container:
        output = await _list_files_in_directory(container, "/workspace/out", "output")
    else:
        output = await _list_files_from_storage(session_id, "/workspace/out", "output")

    return WorkspaceFilesResponse(uploaded=uploaded, output=output)


async def _read_file_content(session_id: str, path: str, db: AsyncSession = None) -> str:
    """Read file content from container, storage backend, or project file storage."""
    # Validate path is within workspace
    if not path.startswith("/workspace/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path must be within /workspace/",
        )

    # Handle project files (uploaded files) - read from file manager on disk
    if path.startswith("/workspace/project_files/") and db:
        filename = path.split("/")[-1]

        # Get session to find project_id
        session_query = select(ChatSession).where(ChatSession.id == session_id)
        session_result = await db.execute(session_query)
        session = session_result.scalar_one_or_none()

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )

        # Find file in database
        file_query = select(File).where(
            File.project_id == session.project_id,
            File.filename == filename
        )
        file_result = await db.execute(file_query)
        file_record = file_result.scalar_one_or_none()

        if not file_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {path}",
            )

        # Read from file manager
        file_manager = get_file_manager()
        file_path = file_manager.get_file_path(file_record.file_path)

        if not file_path or not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found on disk: {path}",
            )

        # Read file content
        mime_type = file_record.mime_type or mimetypes.guess_type(filename)[0]
        content_bytes = file_path.read_bytes()

        if mime_type and mime_type.startswith('image/'):
            b64_content = base64.b64encode(content_bytes).decode('utf-8')
            return f"data:{mime_type};base64,{b64_content}"
        else:
            return content_bytes.decode('utf-8')

    # Try container first for output files
    container = await _get_container_for_session(session_id, raise_if_not_found=False)

    if container:
        # Check if file exists
        exit_code, _, _ = await container.execute(f"test -f '{path}'", workdir="/workspace", timeout=5)
        if exit_code != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {path}",
            )

        content = await container.read_file(path)
        if content is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to read file content",
            )
        return content
    else:
        # Fall back to storage backend
        storage = get_storage()
        try:
            content_bytes = await storage.read_file(session_id, path)
            # Check if it's binary (image, etc.)
            mime_type, _ = mimetypes.guess_type(path)
            if mime_type and mime_type.startswith('image/'):
                # Return as base64 data URI
                import base64 as b64
                b64_content = b64.b64encode(content_bytes).decode('utf-8')
                return f"data:{mime_type};base64,{b64_content}"
            else:
                # Return as text
                return content_bytes.decode('utf-8')
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {path}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to read file: {str(e)}",
            )


@router.get("/{session_id}/workspace/files/content")
async def get_workspace_file_content(session_id: str, path: str, db: AsyncSession = Depends(get_db)):
    """Get the content of a workspace file."""
    content = await _read_file_content(session_id, path, db)

    # Determine if it's a binary file (data URI)
    is_binary = content.startswith('data:')
    mime_type, _ = mimetypes.guess_type(path)

    return {
        "path": path,
        "content": content,
        "is_binary": is_binary,
        "mime_type": mime_type,
    }


@router.get("/{session_id}/workspace/files/download")
async def download_workspace_file(session_id: str, path: str, db: AsyncSession = Depends(get_db)):
    """Download a single workspace file."""
    content = await _read_file_content(session_id, path, db)

    # Get filename and mime type
    filename = path.split('/')[-1]
    mime_type, _ = mimetypes.guess_type(filename)
    mime_type = mime_type or 'application/octet-stream'

    # Handle binary files (data URIs)
    if content.startswith('data:'):
        # Extract base64 content
        try:
            header, b64_data = content.split(',', 1)
            file_bytes = base64.b64decode(b64_data)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to decode file content",
            )
    else:
        file_bytes = content.encode('utf-8')

    return Response(
        content=file_bytes,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/{session_id}/workspace/download-all")
async def download_all_workspace_files(session_id: str, type: str = "output", db: AsyncSession = Depends(get_db)):
    """Download all files of a type as a zip archive."""
    if type == "uploaded":
        # Get uploaded files from database (project files)
        session_query = select(ChatSession).where(ChatSession.id == session_id)
        session_result = await db.execute(session_query)
        session = session_result.scalar_one_or_none()

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        files_query = select(File).where(File.project_id == session.project_id)
        files_result = await db.execute(files_query)
        project_files = files_result.scalars().all()

        files = [
            WorkspaceFile(
                name=f.filename,
                path=f"/workspace/project_files/{f.filename}",
                size=f.size,
                type="uploaded",
                mime_type=f.mime_type,
            )
            for f in project_files
        ]
    elif type == "output":
        directory = "/workspace/out"
        # Try to get running container
        container = await _get_container_for_session(session_id, raise_if_not_found=False)

        if container:
            files = await _list_files_in_directory(container, directory, type)
        else:
            files = await _list_files_from_storage(session_id, directory, type)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Type must be 'uploaded' or 'output'",
        )

    if not files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {type} files found",
        )

    # Create zip file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file in files:
            try:
                content = await _read_file_content(session_id, file.path, db)
                if content:
                    # Handle binary files (data URIs)
                    if content.startswith('data:'):
                        try:
                            header, b64_data = content.split(',', 1)
                            file_bytes = base64.b64decode(b64_data)
                        except Exception:
                            continue
                    else:
                        file_bytes = content.encode('utf-8')

                    zip_file.writestr(file.name, file_bytes)
            except HTTPException:
                # Skip files that can't be read
                continue

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{type}_files.zip"',
        },
    )
