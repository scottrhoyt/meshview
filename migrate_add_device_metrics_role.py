#!/usr/bin/env python3
"""
One-time migration script to add 'role' column to device_metrics table
and backfill it from the node table.

This script is idempotent and safe to run multiple times.
"""

import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from meshview.config import CONFIG


async def column_exists(engine, dialect, table_name, column_name):
    """Check if a column exists in a table."""
    async with engine.begin() as conn:
        if dialect == "postgresql":
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = :table_name
                        AND column_name = :column_name
                    );
                """),
                {"table_name": table_name, "column_name": column_name},
            )
            return result.scalar()
        else:  # SQLite
            result = await conn.execute(
                text(f"PRAGMA table_info({table_name})")
            )
            columns = [row[1] for row in result.fetchall()]
            return column_name in columns


async def migrate_postgresql(engine):
    """Migrate PostgreSQL database."""
    print("\n=== Migrating PostgreSQL Database ===\n")

    async with engine.begin() as conn:
        # Step 1: Add column if it doesn't exist
        column_exists_flag = await column_exists(engine, "postgresql", "device_metrics", "role")

        if not column_exists_flag:
            print("Step 1: Adding 'role' column to device_metrics table...")
            await conn.execute(
                text("ALTER TABLE device_metrics ADD COLUMN role VARCHAR")
            )
            print("  ✓ Column added successfully")
        else:
            print("Step 1: Column 'role' already exists, skipping")

        # Step 2: Backfill existing records
        print("\nStep 2: Backfilling role data from node table...")
        print("  Running UPDATE query to backfill role data...")

        result = await conn.execute(
            text("""
                UPDATE device_metrics dm
                SET role = n.role
                FROM node n
                WHERE dm.node_id = n.node_id
                AND dm.role IS NULL
            """)
        )
        updated_count = result.rowcount

        if updated_count > 0:
            print(f"  ✓ Updated {updated_count:,} records with role data")
        else:
            print("  ✓ All records already have role data (0 updated)")

    print("\n=== PostgreSQL Migration Complete ===\n")


async def migrate_sqlite(engine):
    """Migrate SQLite database."""
    print("\n=== Migrating SQLite Database ===\n")

    async with engine.begin() as conn:
        # Step 1: Add column if it doesn't exist
        column_exists_flag = await column_exists(engine, "sqlite", "device_metrics", "role")

        if not column_exists_flag:
            print("Step 1: Adding 'role' column to device_metrics table...")
            await conn.execute(
                text("ALTER TABLE device_metrics ADD COLUMN role VARCHAR")
            )
            print("  ✓ Column added successfully")
        else:
            print("Step 1: Column 'role' already exists, skipping")

        # Step 2: Backfill existing records
        print("\nStep 2: Backfilling role data from node table...")
        print("  Running UPDATE query to backfill role data...")

        result = await conn.execute(
            text("""
                UPDATE device_metrics
                SET role = (
                    SELECT n.role
                    FROM node n
                    WHERE n.node_id = device_metrics.node_id
                )
                WHERE role IS NULL
                AND EXISTS (
                    SELECT 1 FROM node n
                    WHERE n.node_id = device_metrics.node_id
                )
            """)
        )
        updated_count = result.rowcount

        if updated_count > 0:
            print(f"  ✓ Updated {updated_count:,} records with role data")
        else:
            print("  ✓ All records already have role data (0 updated)")

    print("\n=== SQLite Migration Complete ===\n")


async def main():
    """Main migration function."""
    print("=" * 60)
    print("Device Metrics 'role' Column Migration Script")
    print("=" * 60)
    print(f"Started at: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Get database connection string from config
    connection_string = CONFIG["database"]["connection_string"]
    print(f"\nDatabase: {connection_string.split('@')[-1] if '@' in connection_string else connection_string.split('///')[0]}")

    # Create async engine
    engine = create_async_engine(connection_string, echo=False)

    try:
        # Detect database dialect
        dialect_name = engine.dialect.name
        print(f"Detected dialect: {dialect_name}")

        if dialect_name == "postgresql":
            await migrate_postgresql(engine)
        elif dialect_name == "sqlite":
            await migrate_sqlite(engine)
        else:
            print(f"\nERROR: Unsupported database dialect: {dialect_name}")
            print("This script supports PostgreSQL and SQLite only.")
            sys.exit(1)

        print(f"\nCompleted at: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Migration failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
