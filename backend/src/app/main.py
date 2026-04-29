"""FastAPI application factory and configuration."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi import status
from sqlalchemy import select

from app.config import settings
from app.config.registry import initialize_registries
from app.db.session import close_db, init_db, AsyncSessionLocal
from app.logging import configure_logging, get_logger
from app.middleware.metrics import PrometheusMiddleware, get_metrics
from app.monitoring.sentry import init_sentry
from app.services.scheduler_service import SchedulerService
from app.schemas import IngestionTask, ScheduleType

# Configure logging on startup
configure_logging()
logger = get_logger(__name__)

# Initialize Sentry
init_sentry()


async def reschedule_tasks_from_db():
    """Load and reschedule all active ingestion tasks from the database on startup.

    This ensures that scheduled tasks persist across app restarts.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Fetch all active tasks with schedules
            stmt = select(IngestionTask).where(
                (IngestionTask.status == 'active') &
                (IngestionTask.schedule_type.in_([ScheduleType.ONCE, ScheduleType.RECURRING]))
            )
            result = await session.execute(stmt)
            tasks = result.scalars().all()

            logger.info(f"Found {len(tasks)} active scheduled tasks to reschedule")

            # Reschedule each task
            for task in tasks:
                try:
                    # Import here to avoid circular imports
                    from app.api.admin_ingestion import run_ingestion_task_job

                    await SchedulerService.schedule_task(task, run_ingestion_task_job)
                    logger.info(f"Rescheduled task: {task.name} (ID: {task.id})")
                except Exception as e:
                    logger.warning(f"Failed to reschedule task {task.id}: {str(e)}")

    except Exception as e:
        logger.warning(f"Failed to reschedule tasks from database: {str(e)}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("Starting Agentic Beast API", version=settings.api_version)

   
    # Initialize registries (schema, intents, agent settings)
    try:
        initialize_registries(config_dir=settings.config_dir)
        logger.info("Registries initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize registries", error=str(e))
        raise
    
    try:
        await init_db()
        logger.info("Database connection established")
    except Exception as e:
        logger.warning("Database not available at startup — continuing without DB", error=str(e))

    # Start APScheduler if enabled
    if settings.apscheduler_enabled:
        try:
            await SchedulerService.start()
            logger.info("APScheduler started")

            # Reschedule tasks from database
            await reschedule_tasks_from_db()
            logger.info("Rescheduled tasks from database")
        except Exception as e:
            logger.error("Failed to start APScheduler", error=str(e))

    # Pre-warm on-device LiteRT engine (litert) if VOICE_LLM_PROVIDER=litert
    if (getattr(settings, "voice_llm_provider", "") or "").lower() == "litert":
        try:
            from app.services.multimodal.litert_engine_service import get_litert_engine
            await get_litert_engine()
            logger.info("LiteRT engine pre-warmed")
        except Exception as e:
            logger.warning("Failed to pre-warm LiteRT engine; will retry on first audio turn", error=str(e))

    yield

    # Shutdown
    logger.info("Shutting down Agentic Beast API")
    
    # Shutdown scheduler
    if settings.apscheduler_enabled:
        try:
            await SchedulerService.shutdown()
            logger.info("APScheduler shut down")
        except Exception as e:
            logger.error("Error shutting down APScheduler", error=str(e))
    
    # Close litert engine if it was initialized
    try:
        from app.services.multimodal.litert_engine_service import close_litert_engine
        await close_litert_engine()
        logger.info("LiteRT engine shut down")
    except Exception as e:
        logger.error("Error shutting down LiteRT engine", error=str(e))
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
        description="""
        ## Agentic AI Assistant Platform

        A multi-agent AI assistant platform with pluggable data adapters for analytics querying, 
        document Q&A, tag suggestions, and article recommendations.

        ### Key Features
        - 🤖 **Multi-Agent Architecture**: Specialized agents for different tasks
        - 📊 **Analytics Querying**: Natural language analytics questions
        - 📧 **Gmail Integration**: Automatic Excel report ingestion  
        - 🏷️ **Tag Suggestions**: AI-powered content tagging
        - 📄 **Document Q&A**: Company document knowledge base
        - 🔌 **Pluggable Adapters**: Extensible data source integration

        ### Authentication
        Include your JWT token in the Authorization header: `Bearer <token>`
        """,
        contact={
            "name": "TNN AI Project Team",
            "email": "team@example.com"
        },
        license_info={
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT"
        },
        openapi_tags=[
            {
                "name": "health",
                "description": "Health check endpoints for system monitoring"
            },
            {
                "name": "chat", 
                "description": "Conversational AI endpoints - send messages and manage conversations"
            },
            {
                "name": "ingestion",
                "description": "Data ingestion endpoints for processing Excel reports and external data"
            },
            {
                "name": "auth",
                "description": "Authentication and user management endpoints"
            },
            {
                "name": "documents",
                "description": "Company document upload and Q&A endpoints"
            },
            {
                "name": "analytics",
                "description": "Analytics query endpoints and metrics"
            }
        ],
        # Keep API docs always enabled for backend route discovery.
        openapi_url="/api/openapi.json",
        docs_url="/swagger",
        redoc_url="/redoc",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize rate limiter stores on app.state (used by RateLimiterMiddleware)
    app.state.rate_limit_store = {}
    app.state.rate_limit_locks = {}

    # Attach rate limiter middleware if enabled
    if settings.rate_limit_enabled:
        try:
            from app.middleware.rate_limiter import RateLimiterMiddleware
            app.add_middleware(RateLimiterMiddleware)
            logger.info("Rate limiter middleware enabled")
        except Exception as e:
            logger.warning("Failed to enable rate limiter middleware", error=str(e))

    # Attach auth middleware only when explicitly enabled
    if getattr(settings, "auth_middleware_enabled", False):
        try:
            from app.middleware.auth import AuthMiddleware

            app.add_middleware(AuthMiddleware)
            logger.info("Auth middleware enabled")
        except Exception as e:
            logger.warning("Failed to enable auth middleware", error=str(e))

    # Add error handling middleware
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Global exception handler for consistent error responses."""
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "code": "INTERNAL_ERROR", 
                "details": {
                    "path": request.url.path,
                    "method": request.method
                }
            }
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        """Handle value errors."""
        logger.warning(
            "Value error",
            path=request.url.path,
            method=request.method, 
            error=str(exc)
        )
        
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": str(exc),
                "code": "VALIDATION_ERROR",
                "details": {
                    "path": request.url.path,
                    "method": request.method
                }
            }
        )

    # Health check endpoint
    @app.get(
        "/health", 
        tags=["health"],
        summary="System Health Check",
        description="Check if the system is running and healthy. Returns service status and version.",
        responses={
            200: {
                "description": "System is healthy",
                "content": {
                    "application/json": {
                        "example": {
                            "status": "healthy",
                            "version": "0.1.0",
                            "environment": "development"
                        }
                    }
                }
            }
        }
    )
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "version": settings.api_version,
            "environment": settings.environment,
        }

    @app.get(
        "/api/v1/health",
        tags=["health"], 
        summary="API Health Check",
        description="Check if the API endpoints are running and healthy.",
        responses={
            200: {
                "description": "API is healthy",
                "content": {
                    "application/json": {
                        "example": {
                            "status": "healthy",
                            "version": "0.1.0", 
                            "environment": "development"
                        }
                    }
                }
            }
        }
    )
    async def api_health_check():
        """API health check endpoint."""
        return {
            "status": "healthy",
            "version": settings.api_version,
            "environment": settings.environment,
        }
    
    # Prometheus metrics endpoint
    @app.get(
        "/metrics",
        tags=["monitoring"],
        summary="Prometheus Metrics", 
        description="Expose Prometheus metrics for monitoring and alerting.",
        responses={
            200: {
                "description": "Prometheus metrics in text format",
                "content": {
                    "text/plain": {
                        "example": "# HELP http_requests_total Total HTTP requests\n# TYPE http_requests_total counter\nhttp_requests_total{method=\"GET\",endpoint=\"/health\",status_code=\"200\"} 1.0"
                    }
                }
            }
        }
    )
    async def metrics_endpoint():
        """Expose Prometheus metrics."""
        return get_metrics()

    # Register API routers
    from app.api import admin_ingestion, auth, chat, chat_stream, ingestion, users, webhooks
    app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(chat_stream.router, prefix="/api/v1", tags=["chat-stream"])
    app.include_router(ingestion.router, prefix="/api/v1", tags=["ingestion"])
    app.include_router(users.router, prefix="/api/v1", tags=["auth"])
    app.include_router(admin_ingestion.router, prefix="/api/v1", tags=["admin-ingestion"])
    app.include_router(webhooks.router, tags=["webhooks"])
    
    # TODO: Add other routers when implemented
    # from app.api import auth, health, documents
    # app.include_router(health.router, prefix="/api/v1", tags=["health"])
    # app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
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
