"""File upload/download API routes."""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File as FastAPIFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.core.storage.database import get_db
from app.models.database import File, FileType, Project
from app.models.schemas.file import FileResponse as FileSchema, FileListResponse
from app.core.storage.file_manager import get_file_manager
from app.core.storage.project_volume_storage import get_project_volume_storage
from app.core.sandbox import is_allowed_file


router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload/{project_id}", response_model=FileSchema, status_code=status.HTTP_201_CREATED)
async def upload_file(
    project_id: str,
    file: UploadFile = FastAPIFile(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file to a project."""
    # Verify project exists
    project_query = select(Project).where(Project.id == project_id)
    project_result = await db.execute(project_query)
    project = project_result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Validate file type
    if not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed: {file.filename}",
        )

    # Read file content for both local and volume storage
    file_content = await file.read()
    await file.seek(0)  # Reset for file_manager

    # Save file locally (for API downloads and tracking)
    file_manager = get_file_manager()
    try:
        file_path, size, file_hash = file_manager.save_file(
            project_id=project_id,
            filename=file.filename,
            content=file.file,
        )

        # Also write to project Docker volume (for container access)
        project_storage = get_project_volume_storage()
        await project_storage.write_file(
            project_id=project_id,
            filename=file.filename,
            content=file_content,
        )

        # Create database record
        db_file = File(
            project_id=project_id,
            filename=file.filename,
            file_path=file_path,
            file_type=FileType.INPUT,
            size=size,
            mime_type=file.content_type,
            hash=file_hash,
        )
        db.add(db_file)
        await db.commit()
        await db.refresh(db_file)

        return FileSchema.model_validate(db_file)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}",
        )


@router.get("/project/{project_id}", response_model=FileListResponse)
async def list_project_files(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all files for a project."""
    # Get files from database
    query = select(File).where(File.project_id == project_id).order_by(File.uploaded_at.desc())
    result = await db.execute(query)
    files = result.scalars().all()

    from sqlalchemy import func
    count_query = select(func.count()).select_from(File).where(File.project_id == project_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    return FileListResponse(
        files=[FileSchema.model_validate(f) for f in files],
        total=total,
    )


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Download a file."""
    # Get file record
    query = select(File).where(File.id == file_id)
    result = await db.execute(query)
    file_record = result.scalar_one_or_none()

    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found",
        )

    # Get file path
    file_manager = get_file_manager()
    file_path = file_manager.get_file_path(file_record.file_path)

    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk",
        )

    return FileResponse(
        path=str(file_path),
        filename=file_record.filename,
        media_type=file_record.mime_type or "application/octet-stream",
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a file."""
    # Get file record
    query = select(File).where(File.id == file_id)
    result = await db.execute(query)
    file_record = result.scalar_one_or_none()

    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found",
        )

    # Delete file from local disk
    file_manager = get_file_manager()
    file_manager.delete_file(file_record.file_path)

    # Delete file from project Docker volume
    project_storage = get_project_volume_storage()
    await project_storage.delete_file(
        project_id=file_record.project_id,
        filename=file_record.filename,
    )

    # Delete database record
    await db.delete(file_record)
    await db.commit()
