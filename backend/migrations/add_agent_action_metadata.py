"""Add metadata column to agent_actions table."""

import sqlite3
import sys
import os

# Add parent directory to path to import database config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings


def migrate():
    """Add metadata column to agent_actions table."""
    # Extract path from async database URL (sqlite+aiosqlite:///./data/app.db -> ./data/app.db)
    db_url = settings.database_url
    db_path = db_url.replace('sqlite+aiosqlite:///', '')

    print(f"Migrating database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(agent_actions)")
        columns = [row[1] for row in cursor.fetchall()]

        # Check if old 'metadata' column exists and rename it
        if 'metadata' in columns and 'action_metadata' not in columns:
            # SQLite doesn't support RENAME COLUMN directly in older versions
            # So we need to create new column and copy data
            print("Renaming 'metadata' to 'action_metadata'...")
            cursor.execute("ALTER TABLE agent_actions ADD COLUMN action_metadata JSON")
            cursor.execute("UPDATE agent_actions SET action_metadata = metadata")
            # Note: We can't easily drop columns in SQLite, so we'll leave the old one
            print("✓ Renamed 'metadata' column to 'action_metadata'")
        elif 'action_metadata' in columns:
            print("✓ Column 'action_metadata' already exists in agent_actions table")
        else:
            # Add action_metadata column
            cursor.execute("""
                ALTER TABLE agent_actions
                ADD COLUMN action_metadata JSON
            """)
            conn.commit()
            print("✓ Added 'action_metadata' column to agent_actions table")

        conn.commit()
        print("Migration completed successfully!")

    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
