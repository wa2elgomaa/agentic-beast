#!/usr/bin/env python3
"""
Seed data script for development environment.

Creates sample tags with embeddings and a default admin user.
"""

import asyncio
import sys
from pathlib import Path
from typing import List

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings
from app.schemas import Document, Summary
from app.services.embedding_service import EmbeddingService
from app.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


def load_tags_from_csv(csv_path: str = None) -> List[dict]:
    """Load tags from CSV file."""
    if csv_path is None:
        csv_path = Path(__file__).parent.parent / "data" / "tags.csv"
    
    try:
        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(df)} tags from {csv_path}")
        
        tags = []
        for _, row in df.iterrows():
            # Parse variations from string to list
            variations = [v.strip() for v in str(row['variations']).split(',') if v.strip()] if pd.notna(row['variations']) else []
            
            tag_data = {
                'name': row['name'],
                'slug': row['slug'],
                'description': row['description'],
                'variations': variations,
                'is_primary': bool(row['isPrimary']) if pd.notna(row['isPrimary']) else False
            }
            tags.append(tag_data)
        
        return tags
    except Exception as e:
        logger.error(f"Error loading tags from CSV: {e}")
        return []


async def create_engine_and_session():
    """Create database engine and session."""
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


async def create_sample_tags(session: AsyncSession, embedding_service: EmbeddingService):
    """Create sample tags with embeddings from CSV file."""
    logger.info("Creating sample tags with embeddings from CSV")
    
    # Check if tags already exist using count instead of select to avoid column issues
    try:
        # Use a simple count query that works even if timestamp columns are missing
        result = await session.execute(text("SELECT COUNT(*) FROM tags LIMIT 1"))
        tag_count = result.scalar()
        if tag_count and tag_count > 0:
            logger.info(f"Tags already exist ({tag_count} found), skipping tag creation")
            return
    except Exception as e:
        # If table doesn't exist or there are other issues, continue with creation
        logger.info(f"Could not check existing tags ({str(e)}), proceeding with creation")
    
    # Load tags from CSV
    seed_tags = load_tags_from_csv()
    if not seed_tags:
        logger.warning("No tags loaded from CSV, skipping tag creation")
        return
    
    created_count = 0
    for tag_data in seed_tags:
        try:
            # Generate embedding for tag (name + description + variations)
            tag_text = f"{tag_data['name']} {tag_data['description']} {' '.join(tag_data['variations'])}"
            embedding = embedding_service.embed_text(tag_text)
            
            # Create tag object without timestamps (let database handle them)
            tag = Tag(
                slug=tag_data["slug"],
                name=tag_data["name"],
                description=tag_data["description"],
                variations=tag_data["variations"],  # Will be stored as JSONB
                is_primary=tag_data["is_primary"],
                embedding=embedding  # Store as vector
            )
            session.add(tag)
            created_count += 1
            
            if created_count % 100 == 0:  # Log progress every 100 tags
                logger.info(f"Created {created_count} tags so far...")
            
        except Exception as e:
            logger.error(f"Error creating tag {tag_data['name']}: {str(e)}")
            continue
    
    try:
        await session.commit()
        logger.info(f"Successfully created {created_count} sample tags from CSV")
    except Exception as e:
        await session.rollback()
        logger.error(f"Error committing tags to database: {str(e)}")
        raise


async def create_admin_user(session: AsyncSession):
    """Create default admin user for development."""
    logger.info("Creating default admin user")
    
    # Check if admin user already exists using raw SQL to avoid potential column issues
    try:
        result = await session.execute(text("SELECT COUNT(*) FROM users WHERE email = 'admin@example.com' LIMIT 1"))
        user_count = result.scalar()
        if user_count and user_count > 0:
            logger.info("Admin user already exists, skipping user creation")
            return
    except Exception as e:
        # If table doesn't exist, continue with creation
        logger.info(f"Could not check existing admin user ({str(e)}), proceeding with creation")
    
    # Create admin user
    from passlib.context import CryptContext
    
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed_password = pwd_context.hash("admin123")  # Default password for development
    
    try:
        admin_user = User(
            email="admin@example.com",
            username="admin",
            full_name="System Administrator",
            hashed_password=hashed_password,
            is_active=True,
            is_admin=True
        )
        session.add(admin_user)
        await session.commit()
        
        logger.info("Created admin user: admin@example.com (password: admin123)")
    except Exception as e:
        await session.rollback()
        logger.error(f"Error creating admin user: {str(e)}")
        # Don't raise - this is not critical for tag loading


async def main():
    """Main seed data function."""
    logger.info("Starting seed data population")
    
    try:
        # Create engine and session
        engine, session_factory = await create_engine_and_session()
        
        # Create embedding service
        embedding_service = EmbeddingService()
        
        async with session_factory() as session:
            # Import models here to avoid circular imports
            global Tag, User
            from app.schemas.tag import Tag
            from app.schemas.user import User
            
            # Create sample data
            await create_sample_tags(session, embedding_service)
            await create_admin_user(session)
        
        await engine.dispose()
        logger.info("Seed data population completed successfully")
        
    except Exception as e:
        logger.error("Error during seed data population", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())