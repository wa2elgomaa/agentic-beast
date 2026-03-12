#!/usr/bin/env python3
"""
Seed analytics data from Excel files into documents table.

Reads excel files from data/analytics/ and maps columns to documents table.
Stores overflow columns as JSON metadata.
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd
from sqlalchemy import text, insert, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.services.embedding_service import EmbeddingService
from app.models.document import Document

logger = get_logger(__name__)

# Column mappings: Excel → Database
DIRECT_COLUMN_MAPPINGS = {
    # Profile & Post Information
    "Reported at": "reported_at",
    "Profile name": "profile_name",
    "Profile URL": "profile_url",
    "Profile ID": "profile_id",
    "Post detail URL": "post_detail_url",
    "Content ID": "content_id",
    
    # Platform & Content Classification
    "Platform": "platform",
    "Content type": "content_type",
    "Media type": "media_type",
    "Origin of the content": "origin_of_the_content",
    
    # Content Details
    "Title": "title",
    "Description": "description",
    "Author URL": "author_url",
    "Author ID": "author_id",
    "Author name": "author_name",
    "Content": "content",
    "Link URL": "link_url",
    "View on platform": "view_on_platform",
    
    # Engagement Metrics
    "Organic interactions": "organic_interactions",
    "Total interactions": "total_interactions",
    "Total reactions": "total_reactions",
    "Total comments": "total_comments",
    "Total shares": "total_shares",
    "Unpublished": "unpublished",
    "Engagements": "engagements",
    
    # Reach Metrics
    "Total reach": "total_reach",
    "Paid reach": "paid_reach",
    "Organic reach": "organic_reach",
    
    # Impression Metrics
    "Total impressions": "total_impressions",
    "Paid impressions": "paid_impressions",
    "Organic impressions": "organic_impressions",
    "Reach engagement rate": "reach_engagement_rate",
    
    # Video Metrics
    "Total likes": "total_likes",
    "Video length (sec)": "video_length_sec",
    "Video view count": "video_views",
    "Total video view time (sec)": "total_video_view_time_sec",
    "Completion rate": "completion_rate",
    
    # Labels
    "Labels": "labels",
    "Label groups": "label_groups",
}

# Columns to store in JSON metadata (everything else)
METADATA_COLUMNS = [
    "Created timezone",
    "Profile followers",
    "Mentioned profiles ID",
    "Collaborators",
    "Grade",
    "Last grade",
    "Sentiment",
    "Positive comments",
    "Positive comments (%)",
    "Negative comments",
    "Negative comments (%)",
    "Neutral comments",
    "Neutral comments (%)",
    "Organic likes",
    "Save rate",
    "Organic comments",
    "Deleted",
    "Hidden",
    "Spam",
    "Saves",
    "Promoted post detection",
    "Reactions - like",
    "Reactions - love",
    "Reactions - haha",
    "Reactions - wow",
    "Reactions - sad",
    "Reactions - angry",
    "Shared",
    "Crosspost",
    "Live",
    "Crosspostable",
    "Engaged users",
    "Negative feedback",
    "Lifetime post stories",
    "Post consumers",
    "Post clicks",
    "Photo views",
    "Link clicks",
    "Other clicks",
    "Media views",
    "Video play",
    "Insights reactions - like",
    "Insights reactions - love",
    "Insights reactions - haha",
    "Insights reactions - wow",
    "Insights reactions - sad",
    "Insights reactions - angry",
    "Insights reactions",
    "Recorded",
    "Views - auto-played",
    "Views - click to play",
    "Views - organic",
    "Views - paid",
    "Views - unique",
    "Initial video views",
    "10-second views",
    "10-second views - auto-played",
    "10-second views - click to play",
    "10-second views - organic",
    "10-second views - paid",
    "10-second views - unique",
    "30-second views",
    "30-second views - auto-played",
    "30-second views - click to play",
    "30-second views - organic",
    "30-second views - paid",
    "30-second views - unique",
    "Completed video views",
    "Average completion (%)",
    "Average time watched (sec)",
    "Exits",
    "Taps back",
    "Taps forward",
    "Media tags",
    "Insights video view count",
    "Insights comments",
    "Insights like count",
    "Insights dislike count",
    "Insights share count",
    "Engagements - YouTube insights",
    "Insights subscribers lost",
    "Insights subscribers gained",
    "Insights view time",
    "Swipe up",
    "Swipe down",
    "Screenshots",
    "Media view time",
    "Avg. Video Views per Video",
    "Interactions per 1000 followers",
    "Organic interactions per 1000 followers",
]


def convert_to_python_type(value: Any, target_type: Optional[str] = None) -> Any:
    """Convert pandas/numpy types to Python native types."""
    if pd.isna(value):
        return None
    
    if isinstance(value, (int, float)):
        if target_type == "int":
            return int(value)
        elif target_type == "float":
            return float(value)
        elif target_type == "bool":
            return bool(value)
    
    if isinstance(value, str):
        return value.strip() if value else None
    
    if isinstance(value, (pd.Timestamp, datetime)):
        if target_type == "date":
            return value.date() if hasattr(value, 'date') else value
        return value
    
    return value


def build_metadata_dict(row: pd.Series, skip_columns: set) -> Dict[str, Any]:
    """Build metadata JSON from remaining columns."""
    metadata = {}
    
    for col in METADATA_COLUMNS:
        if col in skip_columns or col not in row.index:
            continue
        
        val = row[col]
        if pd.notna(val):
            # Convert to native Python types for JSON serialization
            if isinstance(val, (pd.Timestamp, datetime)):
                metadata[col] = val.isoformat()
            elif isinstance(val, (float, int)):
                if pd.notna(val):
                    metadata[col] = convert_to_python_type(val)
            else:
                metadata[col] = convert_to_python_type(val)
    
    return metadata if metadata else None


def process_row(
    row: pd.Series,
    sheet_name: str,
    row_number: int,
) -> Dict[str, Any]:
    """Process a single row from Excel and map to document."""
    
    # Track which columns we've used
    used_columns = set(DIRECT_COLUMN_MAPPINGS.keys())
    
    # Build document dict with all required SQL columns initialized to None
    doc = {
        "sheet_name": sheet_name,
        "row_number": row_number,
        "text": None,
        "doc_metadata": None,
        "embedding": None,
        "reported_at": None,
        "profile_name": None,
        "profile_url": None,
        "profile_id": None,
        "post_detail_url": None,
        "content_id": None,
        "platform": None,
        "content_type": None,
        "media_type": None,
        "origin_of_the_content": None,
        "title": None,
        "description": None,
        "author_url": None,
        "author_id": None,
        "author_name": None,
        "content": None,
        "link_url": None,
        "view_on_platform": None,
        "organic_interactions": None,
        "total_interactions": None,
        "total_reactions": None,
        "total_comments": None,
        "total_shares": None,
        "unpublished": None,
        "engagements": None,
        "total_reach": None,
        "paid_reach": None,
        "organic_reach": None,
        "total_impressions": None,
        "paid_impressions": None,
        "organic_impressions": None,
        "reach_engagement_rate": None,
        "total_likes": None,
        "video_length_sec": None,
        "video_views": None,
        "total_video_view_time_sec": None,
        "completion_rate": None,
        "labels": None,
        "label_groups": None,
    }
    
    # Direct column mappings
    for excel_col, db_col in DIRECT_COLUMN_MAPPINGS.items():
        if excel_col not in row.index:
            continue
        
        value = row[excel_col]
        
        # Special handling for different types
        if db_col == "reported_at":
            # Convert to date only
            if pd.notna(value):
                doc[db_col] = (
                    value.date() if hasattr(value, 'date') else value
                )
        elif db_col in ["unpublished"]:
            # Boolean conversion
            if pd.notna(value):
                doc[db_col] = bool(convert_to_python_type(value))
        elif db_col in [
            "organic_interactions", "total_interactions", "total_reactions",
            "total_comments", "total_shares", "engagements", "total_reach",
            "paid_reach", "organic_reach", "total_impressions", "paid_impressions",
            "organic_impressions", "total_likes", "video_length_sec", "video_views",
            "total_video_view_time_sec"
        ]:
            # Integer conversion
            if pd.notna(value):
                doc[db_col] = int(convert_to_python_type(value))
        else:
            doc[db_col] = convert_to_python_type(value)
    
    # Build combined text field for embeddings and search
    text_parts = []
    if pd.notna(row.get("Title")):
        text_parts.append(str(row["Title"]))
    if pd.notna(row.get("Description")):
        text_parts.append(str(row["Description"]))
    if pd.notna(row.get("Content")):
        text_parts.append(str(row["Content"]))
    
    doc["text"] = " ".join(text_parts) if text_parts else ""
    
    # Build metadata from remaining columns
    doc["doc_metadata"] = build_metadata_dict(row, used_columns)
    
    # Embedding is NULL initially (will be generated by service)
    doc["embedding"] = None
    
    return doc


async def ingest_excel_file(
    file_path: str,
    sheet_name: str,
    db_session: AsyncSession,
    embedding_service: Optional[EmbeddingService],
) -> Dict[str, int]:
    """Ingest a single Excel file into database."""
    
    logger.info(f"Starting ingestion from {file_path}", sheet=sheet_name)
    
    # Read Excel file
    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
    except Exception as e:
        logger.error(f"Failed to read Excel file: {e}")
        raise
    
    logger.info(f"Loaded {len(df)} rows from {Path(file_path).name}")
    
    inserted = 0
    failed = 0
    
    # Process rows in batches
    batch_size = 100
    for batch_start in range(0, len(df), batch_size):
        batch_end = min(batch_start + batch_size, len(df))
        batch = df.iloc[batch_start:batch_end]
        
        for idx, (row_idx, row) in enumerate(batch.iterrows()):
            try:
                # Get file name without extension
                base_name = Path(file_path).stem  # "feb-2026" or "nov-2025"
                row_number = row_idx + 1  # Excel uses 1-based indexing
                
                # Process row
                doc_data = process_row(row, base_name, row_number)
                
                # Skip embedding generation for faster ingestion
                # Embeddings can be generated later as a batch job
                doc_data["embedding"] = None
                
                # Convert metadata to JSON string if present
                if doc_data["doc_metadata"]:
                    doc_data["doc_metadata"] = json.dumps(doc_data["doc_metadata"])
                
                # Build INSERT statement with proper parameter binding
                insert_sql = text("""
                INSERT INTO documents (
                    sheet_name, row_number, text, doc_metadata, embedding,
                    reported_at, profile_name, profile_url, profile_id, post_detail_url,
                    content_id, platform, content_type, media_type, origin_of_the_content,
                    title, description, author_url, author_id, author_name,
                    content, link_url, view_on_platform,
                    organic_interactions, total_interactions, total_reactions,
                    total_comments, total_shares, unpublished, engagements,
                    total_reach, paid_reach, organic_reach,
                    total_impressions, paid_impressions, organic_impressions,
                    reach_engagement_rate, total_likes, video_length_sec,
                    video_views, total_video_view_time_sec, completion_rate,
                    labels, label_groups
                ) VALUES (
                    :sheet_name, :row_number, :text, :doc_metadata, :embedding,
                    :reported_at, :profile_name, :profile_url, :profile_id, :post_detail_url,
                    :content_id, :platform, :content_type, :media_type, :origin_of_the_content,
                    :title, :description, :author_url, :author_id, :author_name,
                    :content, :link_url, :view_on_platform,
                    :organic_interactions, :total_interactions, :total_reactions,
                    :total_comments, :total_shares, :unpublished, :engagements,
                    :total_reach, :paid_reach, :organic_reach,
                    :total_impressions, :paid_impressions, :organic_impressions,
                    :reach_engagement_rate, :total_likes, :video_length_sec,
                    :video_views, :total_video_view_time_sec, :completion_rate,
                    :labels, :label_groups
                )
                ON CONFLICT (sheet_name, row_number) DO UPDATE SET
                    text = EXCLUDED.text,
                    doc_metadata = EXCLUDED.doc_metadata,
                    embedding = EXCLUDED.embedding,
                    updated_at = CURRENT_TIMESTAMP
                """)
                
                # Execute with named parameters (all keys must be present)
                await db_session.execute(insert_sql, doc_data)
                inserted += 1
                
                # Log progress every 500 rows
                if (inserted + failed) % 500 == 0:
                    logger.info(
                        f"Progress: {inserted + failed} rows processed "
                        f"({inserted} inserted, {failed} failed)"
                    )
                
            except Exception as e:
                failed += 1
                logger.error(f"Error processing row {row_number}: {e}")
                continue
        
        # Commit batch
        try:
            await db_session.commit()
        except Exception as e:
            logger.error(f"Error committing batch: {e}")
            await db_session.rollback()
            raise
    
    logger.info(
        f"Completed ingestion from {Path(file_path).name}",
        total_rows=inserted + failed,
        inserted=inserted,
        failed=failed,
    )
    
    return {
        "file": file_path,
        "sheet": sheet_name,
        "inserted": inserted,
        "failed": failed,
        "total": inserted + failed,
    }


async def main():
    """Main ingestion function."""
    
    logger.info("Starting analytics data ingestion")
    
    # Initialize embedding service (with lazy loading)
    logger.info("Initializing embedding service (this may take a moment)")
    try:
        embedding_service = EmbeddingService()
        logger.info("Embedding service loaded successfully")
    except Exception as e:
        logger.error(f"Failed to initialize embedding service: {e}")
        logger.info("Continuing without embeddings")
        embedding_service = None
    
    # Get analytics directory
    analytics_dir = Path("/app/data/analytics")
    if not analytics_dir.exists():
        logger.error(f"Analytics directory not found: {analytics_dir}")
        sys.exit(1)
    
    # Find Excel files
    excel_files = sorted(analytics_dir.glob("*.xlsx"))
    if not excel_files:
        logger.error(f"No Excel files found in {analytics_dir}")
        sys.exit(1)
    
    logger.info(f"Found {len(excel_files)} Excel files to ingest")
    
    # Process each Excel file
    results = []
    async with AsyncSessionLocal() as session:
        for excel_file in excel_files:
            try:
                # Get sheet names
                excel_file_obj = pd.ExcelFile(str(excel_file))
                
                for sheet_name in excel_file_obj.sheet_names:
                    result = await ingest_excel_file(
                        str(excel_file),
                        sheet_name,
                        session,
                        embedding_service,
                    )
                    results.append(result)
                    
            except Exception as e:
                logger.error(f"Failed to ingest {excel_file.name}: {e}")
                continue
    
    # Print summary
    print("\n" + "="*80)
    print("INGESTION SUMMARY")
    print("="*80)
    
    total_inserted = 0
    total_failed = 0
    
    for result in results:
        print(f"\n{result['file']} (Sheet: {result['sheet']})")
        print(f"  Inserted: {result['inserted']}")
        print(f"  Failed:   {result['failed']}")
        print(f"  Total:    {result['total']}")
        
        total_inserted += result["inserted"]
        total_failed += result["failed"]
    
    print("\n" + "-"*80)
    print(f"TOTAL INSERTED: {total_inserted}")
    print(f"TOTAL FAILED:   {total_failed}")
    print(f"GRAND TOTAL:    {total_inserted + total_failed}")
    print("="*80 + "\n")
    
    if total_failed > 0:
        logger.warning(f"Completed with {total_failed} errors")
        sys.exit(1)
    else:
        logger.info("Ingestion completed successfully")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
