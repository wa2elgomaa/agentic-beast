"""Admin ingestion API endpoints."""

import secrets
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, Query
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.users import get_current_user
from app.db.session import get_db_session
from app.config import settings
from app.logging import get_logger
from app.models.user import User
from app.models import AdaptorType, ScheduleType
from app.schemas.ingestion import (
    IngestionTaskCreate,
    IngestionTaskUpdate,
    IngestionTaskResponse,
    IngestionTaskRunResponse,
    SchemaDetectResponse,
    SchemaMappingUpdate,
    SchemaMappingTemplateCreate,
    SchemaMappingTemplateResponse,
    TaskSchemaMappingResponse,
    SaveAsTemplateRequest,
    GmailAuthUrlRequest,
    GmailAuthUrlResponse,
    GmailExchangeCodeRequest,
    GmailExchangeCodeResponse,
    CredentialStatusResponse,
    CredentialAuditLogResponse,
)
from app.services.ingestion_task_service import get_ingestion_task_service
from app.services.schema_mapping_service import get_schema_mapping_service
from app.services.file_storage_service import get_file_storage_service
from app.services.scheduler_service import SchedulerService
from app.services.gmail_credential_service import (
    get_gmail_credential_service,
    GmailCredentialHealthStatus,
)
from app.adapters.gmail_adapter import GMAIL_SCOPES
from app.tasks.celery_app import celery_app

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/ingestion", tags=["admin-ingestion"])


async def get_current_admin(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Dependency to require admin role."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


@router.get("/tasks", response_model=list[IngestionTaskResponse])
async def list_tasks(
    adaptor_type: str | None = None,
    status: str | None = None,
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> list[IngestionTaskResponse]:
    """List all ingestion tasks."""
    try:
        service = get_ingestion_task_service(db)
        tasks, _total = await service.list_tasks(adaptor_type, status, limit, offset)
        return [IngestionTaskResponse.model_validate(t) for t in tasks]
    except Exception as e:
        logger.error("Failed to list tasks", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks", response_model=IngestionTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    req: IngestionTaskCreate,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> IngestionTaskResponse:
    """Create a new ingestion task."""
    try:
        service = get_ingestion_task_service(db)
        task = await service.create_task(
            name=req.name,
            adaptor_type=req.adaptor_type,
            description=req.description,
            adaptor_config=req.adaptor_config,
            schedule_type=req.schedule_type,
            cron_expression=req.cron_expression,
            run_at=req.run_at,
            created_by=_admin.id,
        )
        await db.commit()
        await db.refresh(task)

        # Schedule if needed
        if task.schedule_type in [ScheduleType.ONCE, ScheduleType.RECURRING]:
            try:
                await SchedulerService.schedule_task(task, run_ingestion_task_job)
            except Exception as e:
                logger.warning("Failed to schedule task", error=str(e))

        return IngestionTaskResponse.model_validate(task)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error("Database error creating task", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to save the task due to a database error. Please try again or contact an administrator.")
    except Exception as e:
        logger.error("Failed to create task", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", response_model=IngestionTaskResponse)
async def get_task(
    task_id: UUID,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> IngestionTaskResponse:
    """Get task details."""
    try:
        service = get_ingestion_task_service(db)
        task = await service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return IngestionTaskResponse.model_validate(task)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get task", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/tasks/{task_id}", response_model=IngestionTaskResponse)
async def update_task(
    task_id: UUID,
    req: IngestionTaskUpdate,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> IngestionTaskResponse:
    """Update a task."""
    try:
        service = get_ingestion_task_service(db)
        task = await service.update_task(
            task_id,
            name=req.name,
            description=req.description,
            adaptor_config=req.adaptor_config,
            schedule_type=req.schedule_type,
            cron_expression=req.cron_expression,
            run_at=req.run_at,
            status=req.status,
        )
        await db.commit()
        await db.refresh(task)

        # Reschedule if schedule changed
        if task.schedule_type in [ScheduleType.ONCE, ScheduleType.RECURRING]:
            try:
                await SchedulerService.schedule_task(task, run_ingestion_task_job)
            except Exception as e:
                logger.warning("Failed to reschedule task", error=str(e))

        return IngestionTaskResponse.model_validate(task)
    except Exception as e:
        logger.error("Failed to update task", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
):
    """Delete a task."""
    try:
        service = get_ingestion_task_service(db)
        await service.delete_task(task_id)
        await db.commit()

        # Unschedule
        try:
            await SchedulerService.unschedule_task(task_id)
        except Exception as e:
            logger.warning("Failed to unschedule task", error=str(e))

    except Exception as e:
        logger.error("Failed to delete task", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/run", response_model=IngestionTaskRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_run(
    task_id: UUID,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> IngestionTaskRunResponse:
    """Manually trigger a task run."""
    try:
        service = get_ingestion_task_service(db)
        run = await service.create_run(task_id)
        await db.commit()

        # Queue Celery task
        celery_app.send_task("app.tasks.ingestion_tasks.run_ingestion_task", args=[str(task_id), str(run.id)])

        return IngestionTaskRunResponse.model_validate(run)
    except Exception as e:
        logger.error("Failed to trigger run", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/runs", response_model=list[IngestionTaskRunResponse])
async def list_runs(
    task_id: UUID,
    status: str | None = None,
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> list[IngestionTaskRunResponse]:
    """List task runs."""
    try:
        service = get_ingestion_task_service(db)
        runs, _total = await service.list_runs(task_id, status, limit, offset)
        return [IngestionTaskRunResponse.model_validate(r) for r in runs]
    except Exception as e:
        logger.error("Failed to list runs", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/runs/{run_id}", response_model=IngestionTaskRunResponse)
async def get_run(
    task_id: UUID,
    run_id: UUID,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> IngestionTaskRunResponse:
    """Get a run's details."""
    try:
        service = get_ingestion_task_service(db)
        run = await service.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return IngestionTaskRunResponse.model_validate(run)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get run", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/runs/{run_id}/cancel", response_model=IngestionTaskRunResponse)
async def cancel_run(
    task_id: UUID,
    run_id: UUID,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> IngestionTaskRunResponse:
    """Stop a task run immediately if pending, or request a cooperative stop if running."""
    try:
        service = get_ingestion_task_service(db)
        run = await service.get_run(run_id)
        if not run or run.task_id != task_id:
            raise HTTPException(status_code=404, detail="Run not found")

        canceled_run = await service.request_run_cancellation(run_id)
        await db.commit()
        await db.refresh(canceled_run)
        return IngestionTaskRunResponse.model_validate(canceled_run)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error("Failed to cancel run", error=str(e), task_id=task_id, run_id=run_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detect-columns", response_model=SchemaDetectResponse)
async def detect_columns(
    file: UploadFile,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> SchemaDetectResponse:
    """Upload a sample file and detect/auto-map columns."""
    try:
        file_data = await file.read()
        schema_service = get_schema_mapping_service(db)

        source_columns = schema_service.detect_columns_from_file(file_data, file.filename)
        auto_mapped, unmatched = schema_service.auto_map_columns(source_columns)

        return SchemaDetectResponse(
            source_columns=source_columns,
            auto_mapped=auto_mapped,
            unmatched=unmatched,
        )
    except Exception as e:
        logger.error("Failed to detect columns", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tasks/{task_id}/schema-mapping", response_model=Optional[TaskSchemaMappingResponse])
async def get_schema_mapping(
    task_id: UUID,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> Optional[TaskSchemaMappingResponse]:
    """Get task's schema mapping. Returns null if none configured yet."""
    try:
        schema_service = get_schema_mapping_service(db)
        mapping = await schema_service.get_task_mapping(task_id)
        if not mapping:
            return None
        return TaskSchemaMappingResponse.model_validate(mapping)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get schema mapping", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tasks/{task_id}/schema-mapping", response_model=TaskSchemaMappingResponse)
async def save_schema_mapping(
    task_id: UUID,
    req: SchemaMappingUpdate,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> TaskSchemaMappingResponse:
    """Save/update task schema mapping."""
    try:
        schema_service = get_schema_mapping_service(db)
        mapping = await schema_service.save_task_mapping(
            task_id,
            req.source_columns,
            req.field_mappings,
            req.template_id,
            req.identifier_column,
            req.dedup_config,
        )
        await db.commit()
        await db.refresh(mapping)
        return TaskSchemaMappingResponse.model_validate(mapping)
    except Exception as e:
        logger.error("Failed to save schema mapping", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/schema-mapping/save-template", response_model=SchemaMappingTemplateResponse)
async def save_as_template(
    task_id: UUID,
    req: SaveAsTemplateRequest,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> SchemaMappingTemplateResponse:
    """Promote task mapping to a reusable template."""
    try:
        schema_service = get_schema_mapping_service(db)
        template = await schema_service.save_as_template(task_id, req.name, req.description, _admin.id)
        await db.commit()
        await db.refresh(template)
        return SchemaMappingTemplateResponse.model_validate(template)
    except Exception as e:
        logger.error("Failed to save as template", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema-templates", response_model=list[SchemaMappingTemplateResponse])
async def list_templates(
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> list[SchemaMappingTemplateResponse]:
    """List schema mapping templates."""
    try:
        schema_service = get_schema_mapping_service(db)
        templates, _total = await schema_service.list_templates(limit, offset)
        return [SchemaMappingTemplateResponse.model_validate(t) for t in templates]
    except Exception as e:
        logger.error("Failed to list templates", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/schema-templates", response_model=SchemaMappingTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    req: SchemaMappingTemplateCreate,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> SchemaMappingTemplateResponse:
    """Create a new schema mapping template."""
    try:
        schema_service = get_schema_mapping_service(db)
        template = await schema_service.create_template(
            req.name,
            req.description,
            req.source_columns,
            req.field_mappings,
            _admin.id,
        )
        await db.commit()
        return SchemaMappingTemplateResponse.model_validate(template)
    except Exception as e:
        logger.error("Failed to create template", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema-templates/{template_id}", response_model=SchemaMappingTemplateResponse)
async def get_template(
    template_id: UUID,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> SchemaMappingTemplateResponse:
    """Get a schema template."""
    try:
        schema_service = get_schema_mapping_service(db)
        template = await schema_service.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        return SchemaMappingTemplateResponse.model_validate(template)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get template", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/schema-templates/{template_id}", response_model=SchemaMappingTemplateResponse)
async def update_template(
    template_id: UUID,
    req: SchemaMappingTemplateCreate,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> SchemaMappingTemplateResponse:
    """Update a schema template."""
    try:
        schema_service = get_schema_mapping_service(db)
        template = await schema_service.update_template(
            template_id,
            req.name,
            req.description,
            req.source_columns,
            req.field_mappings,
        )
        await db.commit()
        return SchemaMappingTemplateResponse.model_validate(template)
    except Exception as e:
        logger.error("Failed to update template", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/schema-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
):
    """Delete a schema template."""
    try:
        schema_service = get_schema_mapping_service(db)
        await schema_service.delete_template(template_id)
        await db.commit()
    except Exception as e:
        logger.error("Failed to delete template", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


async def run_ingestion_task_job(task_id: str):
    """Callback for APScheduler to run an ingestion task."""
    logger.info("Scheduled ingestion job triggered", task_id=task_id)
    celery_app.send_task("app.tasks.ingestion_tasks.run_ingestion_task", args=[task_id])


def _build_google_client_config() -> dict:
    """Build OAuth client config from settings."""
    if not settings.gmail_oauth_client_id or not settings.gmail_oauth_client_secret:
        raise HTTPException(
            status_code=500,
            detail="Gmail OAuth client credentials not configured",
        )

    return {
        "web": {
            "client_id": settings.gmail_oauth_client_id,
            "client_secret": settings.gmail_oauth_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": settings.gmail_oauth_token_uri,
        }
    }


@router.post("/tasks/{task_id}/gmail/auth-url", response_model=GmailAuthUrlResponse)
async def get_gmail_auth_url(
    task_id: UUID,
    req: GmailAuthUrlRequest,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> GmailAuthUrlResponse:
    """Generate Google OAuth URL for a Gmail task."""
    try:
        service = get_ingestion_task_service(db)
        task = await service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.adaptor_type != AdaptorType.GMAIL:
            raise HTTPException(status_code=400, detail="Task is not a Gmail adaptor")

        # Embed task_id into state so the fixed callback page can identify the task
        nonce = secrets.token_urlsafe(32)
        combined_state = f"{task_id}:{nonce}"

        flow = Flow.from_client_config(_build_google_client_config(), scopes=GMAIL_SCOPES, redirect_uri=req.redirect_uri)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=combined_state,
        )

        config = dict(task.adaptor_config or {})
        config["oauth_state"] = combined_state
        config["oauth_redirect_uri"] = req.redirect_uri
        # Persist PKCE code_verifier — autogenerated by the library (autogenerate_code_verifier=True default)
        # Must be restored on the exchange flow or Google returns "Missing code verifier"
        if flow.code_verifier:
            config["oauth_code_verifier"] = flow.code_verifier
        task.adaptor_config = config
        db.add(task)
        await db.commit()

        return GmailAuthUrlResponse(auth_url=auth_url, state=combined_state)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate Gmail auth URL", error=str(e), task_id=task_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/gmail/exchange-code", response_model=GmailExchangeCodeResponse)
async def exchange_gmail_code(
    task_id: UUID,
    req: GmailExchangeCodeRequest,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> GmailExchangeCodeResponse:
    """Exchange OAuth code and persist task-scoped Gmail user credentials."""
    try:
        service = get_ingestion_task_service(db)
        task = await service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.adaptor_type != AdaptorType.GMAIL:
            raise HTTPException(status_code=400, detail="Task is not a Gmail adaptor")

        config = dict(task.adaptor_config or {})
        saved_state = config.get("oauth_state")
        if not saved_state or saved_state != req.state:
            raise HTTPException(status_code=400, detail="Invalid OAuth state")

        # Use the redirect_uri saved during auth URL generation to guarantee exact match
        saved_redirect_uri = config.get("oauth_redirect_uri", req.redirect_uri)
        code_verifier = config.get("oauth_code_verifier")

        try:
            flow = Flow.from_client_config(
                _build_google_client_config(),
                scopes=GMAIL_SCOPES,
                redirect_uri=saved_redirect_uri,
                code_verifier=code_verifier,
                autogenerate_code_verifier=False,
            )
            flow.fetch_token(code=req.code)
        except Exception as token_err:
            err_str = str(token_err).lower()
            if "invalid_grant" in err_str:
                raise HTTPException(
                    status_code=400,
                    detail="Authorization code expired or already used. Please click Connect Gmail again to start a new authorization.",
                )
            raise
        creds = flow.credentials

        oauth_config = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token or config.get("gmail_oauth", {}).get("refresh_token"),
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret or settings.gmail_oauth_client_secret,
            "scopes": list(creds.scopes or []),
        }

        gmail_service = build("gmail", "v1", credentials=creds)
        profile = gmail_service.users().getProfile(userId="me").execute()
        connected_email = profile.get("emailAddress", "")

        config["gmail_oauth"] = oauth_config
        config["gmail_account_email"] = connected_email
        config.pop("oauth_state", None)
        config.pop("oauth_code_verifier", None)
        config["oauth_redirect_uri"] = req.redirect_uri
        task.adaptor_config = config
        db.add(task)
        await db.commit()

        return GmailExchangeCodeResponse(task_id=task_id, connected_email=connected_email)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to exchange Gmail OAuth code", error=str(e), task_id=task_id)
        raise HTTPException(status_code=500, detail=str(e))


# Test Execution Endpoints

class TestRunResponse(BaseModel):
    """Response model for test run."""
    id: str
    task_id: str
    executed_at: str
    status: str  # 'success', 'failed', 'running'
    duration_ms: int
    error_message: Optional[str] = None
    logs: Optional[str] = None


class TestConfigUpdate(BaseModel):
    """Request model for updating test configuration."""
    test_execution_enabled: bool
    test_execution_interval_minutes: int


@router.post("/tasks/{task_id}/test-run", status_code=status.HTTP_202_ACCEPTED)
async def run_test_now(
    task_id: UUID,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
):
    """Queue a test run for a specific ingestion task.

    This will execute the ingestion task immediately, regardless of schedule,
    to verify the configuration is working correctly.
    """
    try:
        service = get_ingestion_task_service(db)
        task = await service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Queue task for immediate execution
        celery_app.send_task(
            "app.tasks.ingestion_tasks.run_ingestion_task",
            args=[str(task_id)],
        )

        logger.info("Test run queued", task_id=task_id, triggered_by=_admin.id)
        return {"task_id": task_id, "status": "queued"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to queue test run", error=str(e), task_id=task_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/test-runs")
async def get_test_runs(
    task_id: UUID,
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
):
    """Get test execution history for a task."""
    try:
        from sqlalchemy import select, desc
        from app.models import CronTestRun

        stmt = (
            select(CronTestRun)
            .where(CronTestRun.task_id == task_id)
            .order_by(desc(CronTestRun.executed_at))
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        test_runs = result.scalars().all()

        return {
            "test_runs": [
                {
                    "id": str(run.id),
                    "task_id": str(run.task_id),
                    "executed_at": run.executed_at.isoformat(),
                    "status": run.status,
                    "duration_ms": run.duration_ms or 0,
                    "error_message": run.error_message,
                    "logs": run.logs,
                }
                for run in test_runs
            ],
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error("Failed to get test runs", error=str(e), task_id=task_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/tasks/{task_id}/test-config")
async def update_test_config(
    task_id: UUID,
    req: TestConfigUpdate,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
):
    """Update test execution configuration for a task."""
    try:
        service = get_ingestion_task_service(db)
        task = await service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Update test configuration
        task.test_execution_enabled = req.test_execution_enabled
        task.test_execution_interval_minutes = req.test_execution_interval_minutes

        db.add(task)
        await db.commit()

        logger.info(
            "Test configuration updated",
            task_id=task_id,
            enabled=req.test_execution_enabled,
            interval_minutes=req.test_execution_interval_minutes,
        )

        return {
            "task_id": task_id,
            "test_execution_enabled": task.test_execution_enabled,
            "test_execution_interval_minutes": task.test_execution_interval_minutes,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update test config", error=str(e), task_id=task_id)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Gmail Credential Management Endpoints
# ============================================================================


@router.get("/tasks/{task_id}/gmail/credential-status", response_model=CredentialStatusResponse)
async def get_credential_status(
    task_id: UUID,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> CredentialStatusResponse:
    """Get current Gmail credential status and health for a task."""
    try:
        from app.models import GmailCredentialStatus
        from sqlalchemy import select

        # Verify task exists
        service = get_ingestion_task_service(db)
        task = await service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Get credential status
        credential_service = get_gmail_credential_service(db)
        status = await credential_service.get_credential_status(task_id)

        if not status:
            # Return default pending status if none exists yet
            status = await credential_service.get_or_create_credential_status(task_id)

        return CredentialStatusResponse(
            task_id=status.task_id,
            status=status.status,
            health_score=status.health_score,
            account_email=status.account_email,
            consecutive_failures=status.consecutive_failures,
            max_consecutive_failures=status.max_consecutive_failures,
            last_used_at=status.last_used_at.isoformat() if status.last_used_at else None,
            auth_established_at=status.auth_established_at.isoformat() if status.auth_established_at else None,
            token_refreshed_at=status.token_refreshed_at.isoformat() if status.token_refreshed_at else None,
            last_error_code=status.last_error_code,
            last_error_message=status.last_error_message,
            created_at=status.created_at.isoformat(),
            updated_at=status.updated_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get credential status", error=str(e), task_id=task_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/gmail/audit-log", response_model=CredentialAuditLogResponse)
async def get_credential_audit_log(
    task_id: UUID,
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> CredentialAuditLogResponse:
    """Get Gmail credential audit log for a task."""
    try:
        from app.models import GmailCredentialAuditLog
        from sqlalchemy import select, desc, func

        # Verify task exists
        service = get_ingestion_task_service(db)
        task = await service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Get audit logs with total count
        credential_service = get_gmail_credential_service(db)

        # Get paginated logs
        logs = await credential_service.get_audit_log(task_id, limit=limit)
        
        # Get total count
        count_stmt = select(func.count(GmailCredentialAuditLog.id)).where(
            GmailCredentialAuditLog.task_id == task_id
        )
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0

        return CredentialAuditLogResponse(
            audit_log=[
                {
                    "id": log.id,
                    "task_id": log.task_id,
                    "event_type": log.event_type,
                    "account_email": log.account_email,
                    "error_code": log.error_code,
                    "error_message": log.error_message,
                    "action_by": log.action_by,
                    "created_at": log.created_at.isoformat(),
                }
                for log in logs
            ],
            limit=limit,
            offset=offset,
            total=total,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get audit log", error=str(e), task_id=task_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/gmail/re-authenticate")
async def re_authenticate_gmail(
    task_id: UUID,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
):
    """Trigger Gmail re-authentication by returning OAuth URL."""
    try:
        # Verify task exists and is Gmail type
        service = get_ingestion_task_service(db)
        task = await service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.adaptor_type != AdaptorType.GMAIL:
            raise HTTPException(
                status_code=400,
                detail="Task is not a Gmail ingestion task"
            )

        # Generate new OAuth URL using the same flow as initial auth
        # Embed task_id into state so callback page can identify the task
        nonce = secrets.token_urlsafe(32)
        combined_state = f"{task_id}:{nonce}"
        
        # Use stored redirect URI from task config, or default to configured one
        redirect_uri = (task.adaptor_config or {}).get("oauth_redirect_uri") or settings.gmail_oauth_redirect_uri

        flow = Flow.from_client_config(
            _build_google_client_config(),
            scopes=GMAIL_SCOPES,
            state=combined_state,
            redirect_uri=redirect_uri
        )
        auth_uri, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )

        # Update task config with state and code_verifier for callback
        config = dict(task.adaptor_config or {})
        config["oauth_state"] = combined_state
        config["oauth_redirect_uri"] = redirect_uri
        if flow.code_verifier:
            config["oauth_code_verifier"] = flow.code_verifier
        task.adaptor_config = config
        db.add(task)
        await db.commit()

        logger.info("Gmail re-authentication initiated", task_id=task_id, initiated_by=_admin.id)

        return {
            "task_id": str(task_id),
            "auth_url": auth_uri,
            "state": combined_state,
            "message": "Complete the authentication to re-authorize Gmail access",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to initiate re-authentication", error=str(e), task_id=task_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}/gmail/credentials")
async def clear_gmail_credentials(
    task_id: UUID,
    _admin: Annotated[User, Depends(get_current_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
):
    """Clear stored Gmail credentials (admin action)."""
    try:
        # Verify task exists and is Gmail type
        service = get_ingestion_task_service(db)
        task = await service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.adaptor_type != AdaptorType.GMAIL:
            raise HTTPException(
                status_code=400,
                detail="Task is not a Gmail ingestion task"
            )

        # Clear credentials from adaptor_config
        task.adaptor_config = task.adaptor_config or {}
        if "gmail_oauth" in task.adaptor_config:
            del task.adaptor_config["gmail_oauth"]

        db.add(task)
        await db.commit()

        # Clear credential status
        credential_service = get_gmail_credential_service(db)
        await credential_service.clear_credentials(task_id, cleared_by=_admin.id)
        await db.commit()

        logger.info("Gmail credentials cleared", task_id=task_id, cleared_by=_admin.id)

        return {
            "task_id": str(task_id),
            "status": "cleared",
            "message": "Gmail credentials have been cleared. Re-authentication required for next run.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to clear credentials", error=str(e), task_id=task_id)
        raise HTTPException(status_code=500, detail=str(e))
