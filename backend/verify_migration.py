#!/usr/bin/env python3
import asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
import os

async def verify_migration():
    # Get database URL
    db_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@localhost:5432/agentic_beast')
    
    engine = create_async_engine(db_url, echo=False)
    
    async with engine.begin() as conn:
        # Get inspector for sync engine
        sync_inspector = inspect(conn.sync_engine)
        tables = sync_inspector.get_table_names()
        
        print("✅ Database Migration Verification")
        print("=" * 50)
        print(f"\nTotal tables in database: {len(tables)}\n")
        
        # Check new ingestion tables
        new_tables = [
            'ingestion_tasks',
            'ingestion_task_runs', 
            'schema_mapping_templates',
            'task_schema_mappings',
            'uploaded_files'
        ]
        
        print("📊 New Ingestion Module Tables:")
        print("-" * 50)
        
        all_created = True
        for table_name in new_tables:
            if table_name in tables:
                columns = sync_inspector.get_columns(table_name)
                print(f"✅ {table_name:30} ({len(columns)} columns)")
            else:
                print(f"❌ {table_name:30} (NOT FOUND)")
                all_created = False
        
        # Show APScheduler job store table if it exists
        if 'apscheduler_jobs' in tables:
            print(f"\n✅ APScheduler job store: apscheduler_jobs")
        
        print("\n" + "=" * 50)
        if all_created:
            print("✅ Migration completed successfully!")
        else:
            print("❌ Some tables are missing!")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(verify_migration())
