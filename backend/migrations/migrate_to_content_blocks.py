"""
Migration script to convert existing Message + AgentAction data to unified ContentBlock model.

This script:
1. Creates the content_blocks table if it doesn't exist
2. Migrates existing messages to content blocks (user_text, assistant_text)
3. Migrates existing agent_actions to content blocks (tool_call, tool_result)
4. Maintains correct sequence_number ordering using created_at timestamps

Usage:
    cd backend
    poetry run python migrations/migrate_to_content_blocks.py

The old tables (messages, agent_actions) are kept for backward compatibility.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.storage.database import Base
from app.models.database import (
    ContentBlock, ContentBlockType, ContentBlockAuthor,
    Message, MessageRole, AgentAction
)


DATABASE_URL = "sqlite+aiosqlite:///./data/open_codex.db"


async def create_content_blocks_table(engine):
    """Create the content_blocks table if it doesn't exist."""
    async with engine.begin() as conn:
        # Check if table exists
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='content_blocks'"
        ))
        exists = result.scalar() is not None

        if exists:
            print("content_blocks table already exists")
            return False

        # Create table
        await conn.execute(text("""
            CREATE TABLE content_blocks (
                id VARCHAR(36) PRIMARY KEY,
                chat_session_id VARCHAR(36) NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                sequence_number INTEGER NOT NULL,
                block_type VARCHAR(20) NOT NULL,
                author VARCHAR(20) NOT NULL,
                content JSON NOT NULL DEFAULT '{}',
                parent_block_id VARCHAR(36) REFERENCES content_blocks(id) ON DELETE SET NULL,
                block_metadata JSON NOT NULL DEFAULT '{}',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create indexes
        await conn.execute(text(
            "CREATE INDEX ix_content_blocks_chat_session_id ON content_blocks(chat_session_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX ix_content_blocks_sequence_number ON content_blocks(sequence_number)"
        ))

        print("Created content_blocks table with indexes")
        return True


async def migrate_session_data(session: AsyncSession, chat_session_id: str):
    """Migrate all messages and agent_actions for a single chat session."""
    import json
    import uuid

    # Get all messages for this session
    result = await session.execute(text("""
        SELECT id, role, content, created_at, message_metadata
        FROM messages
        WHERE chat_session_id = :session_id
        ORDER BY created_at ASC
    """), {"session_id": chat_session_id})
    messages = result.fetchall()

    if not messages:
        return 0

    # Collect all content items with timestamps for proper ordering
    content_items = []

    for msg in messages:
        msg_id, role, content, created_at, message_metadata = msg

        # Parse created_at if it's a string
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))

        # Determine block type and author based on role
        if role == "USER" or role == "user":
            block_type = ContentBlockType.USER_TEXT
            author = ContentBlockAuthor.USER
        elif role == "ASSISTANT" or role == "assistant":
            block_type = ContentBlockType.ASSISTANT_TEXT
            author = ContentBlockAuthor.ASSISTANT
        else:
            block_type = ContentBlockType.SYSTEM
            author = ContentBlockAuthor.SYSTEM

        # Add text message block
        content_items.append({
            "id": str(uuid.uuid4()),
            "block_type": block_type,
            "author": author,
            "content": {"text": content or ""},
            "block_metadata": json.loads(message_metadata) if isinstance(message_metadata, str) else (message_metadata or {}),
            "created_at": created_at,
            "parent_block_id": None,
            "original_message_id": msg_id,
        })

        # Get agent_actions for this message
        actions_result = await session.execute(text("""
            SELECT id, action_type, action_input, action_output, status, action_metadata, created_at
            FROM agent_actions
            WHERE message_id = :message_id
            ORDER BY created_at ASC
        """), {"message_id": msg_id})
        actions = actions_result.fetchall()

        for action in actions:
            action_id, action_type, action_input, action_output, status, action_metadata, action_created_at = action

            # Parse created_at if it's a string
            if isinstance(action_created_at, str):
                action_created_at = datetime.fromisoformat(action_created_at.replace('Z', '+00:00'))

            # Parse JSON fields
            if isinstance(action_input, str):
                action_input = json.loads(action_input)
            if isinstance(action_output, str):
                action_output = json.loads(action_output)
            if isinstance(action_metadata, str):
                action_metadata = json.loads(action_metadata)

            # Create tool_call block
            tool_call_id = str(uuid.uuid4())
            content_items.append({
                "id": tool_call_id,
                "block_type": ContentBlockType.TOOL_CALL,
                "author": ContentBlockAuthor.ASSISTANT,
                "content": {
                    "tool_name": action_type,
                    "arguments": action_input or {},
                    "status": "complete" if status in ("SUCCESS", "success") else "error",
                },
                "block_metadata": {"original_action_id": action_id},
                "created_at": action_created_at,
                "parent_block_id": None,
            })

            # Create tool_result block (immediately after tool_call)
            # Add a tiny time delta to ensure it comes after the tool_call
            from datetime import timedelta
            result_created_at = action_created_at + timedelta(microseconds=1)

            content_items.append({
                "id": str(uuid.uuid4()),
                "block_type": ContentBlockType.TOOL_RESULT,
                "author": ContentBlockAuthor.TOOL,
                "content": {
                    "tool_name": action_type,
                    "result": json.dumps(action_output) if action_output else None,
                    "success": status in ("SUCCESS", "success"),
                    "error": None if status in ("SUCCESS", "success") else "Error occurred",
                    "is_binary": bool(action_metadata and action_metadata.get("is_binary")),
                    "binary_type": action_metadata.get("type") if action_metadata else None,
                    "binary_data": action_metadata.get("image_data") if action_metadata else None,
                },
                "block_metadata": action_metadata or {},
                "created_at": result_created_at,
                "parent_block_id": tool_call_id,
            })

    # Sort all items by created_at
    content_items.sort(key=lambda x: x["created_at"])

    # Assign sequence numbers and insert blocks
    for seq_num, item in enumerate(content_items):
        await session.execute(text("""
            INSERT INTO content_blocks (
                id, chat_session_id, sequence_number, block_type, author,
                content, parent_block_id, block_metadata, created_at, updated_at
            ) VALUES (
                :id, :session_id, :seq_num, :block_type, :author,
                :content, :parent_id, :block_metadata, :created_at, :updated_at
            )
        """), {
            "id": item["id"],
            "session_id": chat_session_id,
            "seq_num": seq_num,
            "block_type": item["block_type"].value,
            "author": item["author"].value,
            "content": json.dumps(item["content"]),
            "parent_id": item.get("parent_block_id"),
            "block_metadata": json.dumps(item["block_metadata"]),
            "created_at": item["created_at"].isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        })

    return len(content_items)


async def run_migration():
    """Run the full migration."""
    print("=" * 60)
    print("Content Blocks Migration")
    print("=" * 60)

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Step 1: Create table
    print("\n[1/3] Creating content_blocks table...")
    table_created = await create_content_blocks_table(engine)

    if not table_created:
        # Check if migration already happened
        async with async_session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM content_blocks"))
            count = result.scalar()
            if count > 0:
                print(f"\nMigration already completed. Found {count} existing content blocks.")
                print("To re-run, manually drop the content_blocks table first.")
                return

    # Step 2: Get all chat sessions
    print("\n[2/3] Finding chat sessions to migrate...")
    async with async_session() as session:
        result = await session.execute(text(
            "SELECT DISTINCT chat_session_id FROM messages"
        ))
        session_ids = [row[0] for row in result.fetchall()]

    print(f"Found {len(session_ids)} chat sessions with messages")

    # Step 3: Migrate each session
    print("\n[3/3] Migrating messages and agent_actions to content_blocks...")
    total_blocks = 0

    async with async_session() as session:
        for i, session_id in enumerate(session_ids):
            blocks_created = await migrate_session_data(session, session_id)
            total_blocks += blocks_created
            print(f"  [{i+1}/{len(session_ids)}] Session {session_id[:8]}... -> {blocks_created} blocks")

        await session.commit()

    print("\n" + "=" * 60)
    print(f"Migration complete! Created {total_blocks} content blocks.")
    print("=" * 60)

    # Verify
    async with async_session() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM content_blocks"))
        final_count = result.scalar()
        print(f"\nVerification: {final_count} total content blocks in database")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_migration())
