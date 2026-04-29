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


async def seed_app_settings(session: AsyncSession) -> None:
    """Seed default application settings for Phase 2 admin dashboard (SC-002).
    
    Creates app_settings rows for:
    - Model provider configuration (orchestrator, agents)
    - API keys (OpenAI, etc.) — marked as_secret
    - Monitoring intervals
    
    These can be updated at runtime via PUT /admin/settings without restart.
    """
    from app.models.phase2 import AppSettingModel
    from app.config import settings
    
    # Default settings to seed
    default_settings = [
        # Model configuration
        ("ORCHESTRATOR_MODEL", settings.main_agent.get("model_id", "gpt-4"), False),
        ("ANALYTICS_AGENT_MODEL", settings.analytics_agent.get("model_id", "gpt-4"), False),
        ("CHAT_AGENT_MODEL", settings.chat_agent.get("model_id", "gpt-4"), False),
        ("TAGGING_AGENT_MODEL", settings.tagging_agent.get("model_id", "gpt-4"), False),
        ("RECOMMENDATION_AGENT_MODEL", settings.recommendation_agent.get("model_id", "gpt-4"), False),
        ("DOCUMENT_AGENT_MODEL", settings.document_agent.get("model_id", "gpt-4"), False),
        ("SEARCH_AGENT_MODEL", settings.search_agent.get("model_id", "gpt-4") if hasattr(settings, "search_agent") else "gpt-4", False),
        
        # API keys (secrets)
        ("OPENAI_API_KEY", settings.openai_api_key or "sk-placeholder", True),
        ("GMAIL_API_KEY", getattr(settings, "gmail_api_key", ""), True),
        ("GOOGLE_CSE_API_KEY", settings.google_cse_api_key or "cse-api-key-placeholder", True),
        
        # Google Custom Search configuration
        ("GOOGLE_CSE_ID", settings.google_cse_id or "cse-id-placeholder", False),
        ("GOOGLE_CSE_SITE", settings.google_cse_site or "thenationalnews.com", False),
        
        # Monitoring & intervals
        ("GMAIL_MONITOR_INTERVAL_SECONDS", str(settings.gmail_monitor_interval_seconds or 300), False),
        ("CMS_WEBHOOK_RETRY_INTERVAL_SECONDS", "60", False),
        
        # Phase 2 defaults
        ("GOOGLE_CSE_DAILY_LIMIT", str(settings.google_cse_daily_limit or 100), False),
        ("CMS_SCRAPE_BATCH_SIZE", str(settings.cms_scrape_batch_size or 50), False),
    ]
    
    try:
        for key, value, is_secret in default_settings:
            # Skip if setting already exists
            stmt = select(AppSettingModel).where(AppSettingModel.key == key)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                logger.info(f"Settings key already exists, skipping: {key}")
                continue
            
            # Create new setting (will be encrypted if is_secret)
            setting = AppSettingModel(
                key=key,
                value=value,
                is_secret=is_secret,
            )
            session.add(setting)
            logger.info(f"Seeded setting: {key} (is_secret={is_secret})")
        
        await session.commit()
        logger.info("App settings seeding completed successfully")
        
    except Exception as exc:
        await session.rollback()
        logger.error(f"Error seeding app settings: {str(exc)}")
        # Don't raise - continue with other seeding


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
            await seed_app_settings(session)  # Phase 2: Seed admin settings
        
        await engine.dispose()
        logger.info("Seed data population completed successfully")
        
    except Exception as e:
        logger.error("Error during seed data population", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())