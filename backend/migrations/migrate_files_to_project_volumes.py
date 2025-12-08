#!/usr/bin/env python3
"""Migration script to copy existing project files to Docker volumes.

This script copies files from the local filesystem (data/project_files/)
to project-level Docker volumes so containers can access them.

Usage:
    python migrations/migrate_files_to_project_volumes.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.core.storage.database import AsyncSessionLocal
from app.core.storage.file_manager import get_file_manager
from app.core.storage.project_volume_storage import get_project_volume_storage
from app.models.database import Project, File


async def migrate_project_files():
    """Migrate all project files to Docker volumes."""
    file_manager = get_file_manager()
    project_storage = get_project_volume_storage()

    migrated_count = 0
    error_count = 0

    async with AsyncSessionLocal() as db:
        # Get all projects
        projects_query = select(Project)
        projects_result = await db.execute(projects_query)
        projects = projects_result.scalars().all()

        print(f"Found {len(projects)} projects to process")

        for project in projects:
            print(f"\nProcessing project: {project.id} ({project.name})")

            # Get all files for this project
            files_query = select(File).where(File.project_id == project.id)
            files_result = await db.execute(files_query)
            files = files_result.scalars().all()

            if not files:
                print(f"  No files found for project {project.id}")
                continue

            print(f"  Found {len(files)} files")

            # Ensure project volume exists
            await project_storage.ensure_volume(project.id)

            for file_record in files:
                try:
                    # Get file path from file manager
                    file_path = file_manager.get_file_path(file_record.file_path)

                    if not file_path or not file_path.exists():
                        print(f"  ⚠ File not found on disk: {file_record.filename}")
                        error_count += 1
                        continue

                    # Read file content
                    content = file_path.read_bytes()

                    # Write to project volume
                    success = await project_storage.write_file(
                        project_id=project.id,
                        filename=file_record.filename,
                        content=content,
                    )

                    if success:
                        print(f"  ✓ Migrated: {file_record.filename} ({len(content)} bytes)")
                        migrated_count += 1
                    else:
                        print(f"  ✗ Failed to write: {file_record.filename}")
                        error_count += 1

                except Exception as e:
                    print(f"  ✗ Error migrating {file_record.filename}: {e}")
                    error_count += 1

    print(f"\n{'='*50}")
    print(f"Migration complete!")
    print(f"  Successfully migrated: {migrated_count} files")
    print(f"  Errors: {error_count} files")


if __name__ == "__main__":
    print("Starting file migration to project Docker volumes...")
    print("=" * 50)
    asyncio.run(migrate_project_files())
