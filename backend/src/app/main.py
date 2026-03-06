"""FastAPI application factory and configuration."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import close_db, init_db
from app.logging import configure_logging, get_logger

# Configure logging on startup
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("Starting Agentic Beast API", version=settings.api_version)
    try:
        await init_db()
        logger.info("Database connection established")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise

    yield

    # Shutdown
    logger.info("Shutting down Agentic Beast API")
    try:
        await close_db()
        logger.info("Database connection closed")
    except Exception as e:
        logger.error("Error during shutdown", error=str(e))


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        debug=settings.api_debug,
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "version": settings.api_version,
            "environment": settings.environment,
        }

    @app.get("/api/v1/health")
    async def api_health_check():
        """API health check endpoint."""
        return {
            "status": "healthy",
            "version": settings.api_version,
            "environment": settings.environment,
        }

    # Register API routers
    from app.api import chat, ingestion
    app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(ingestion.router, prefix="/api/v1", tags=["ingestion"])
    
    # TODO: Add other routers when implemented
    # from app.api import auth, health, documents
    # app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    # app.include_router(health.router, prefix="/api/v1", tags=["health"])
    # app.include_router(documents.router, prefix="/api/v1", tags=["documents"])

    logger.info("FastAPI application created successfully")
    return app


# Create the application instance
app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
    )
