"""Admin dataset management API router.

Endpoints:
- GET  /admin/datasets                        — list all datasets
- POST /admin/datasets                        — create dataset
- GET  /admin/datasets/{slug}                 — get dataset with files
- PUT  /admin/datasets/{slug}                 — update dataset metadata
- DELETE /admin/datasets/{slug}              — delete dataset (and files)
- POST /admin/datasets/{slug}/upload          — upload file to dataset
- POST /admin/datasets/{slug}/embed           — trigger embedding for all files
- GET  /admin/datasets/{slug}/files/{file_id}/status — check embed status

All endpoints require admin JWT role claim.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Annotated, List, Optional

import structlog
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    UploadFile,
    File,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete

from app.auth import verify_admin
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.phase2 import DatasetModel, DatasetFileModel

logger = structlog.get_logger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────── Pydantic schemas ──

class DatasetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9_-]+$")
    description: Optional[str] = None
    allowed_extensions: List[str] = Field(default=[".pdf", ".docx", ".txt"])


class DatasetUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    allowed_extensions: Optional[List[str]] = None


class DatasetFileResponse(BaseModel):
    id: str
    filename: str
    s3_key: str
    file_size_bytes: int
    content_type: Optional[str]
    embed_status: str
    embed_task_id: Optional[str]
    chunks_created: Optional[int]
    error: Optional[str]
    uploaded_at: datetime


class DatasetResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: Optional[str]
    allowed_extensions: List[str]
    file_count: int
    embedded_count: int
    created_at: datetime
    updated_at: datetime
    files: Optional[List[DatasetFileResponse]] = None


class DatasetListResponse(BaseModel):
    items: List[DatasetResponse]
    total: int


class DatasetUploadResponse(BaseModel):
    file_id: str
    filename: str
    file_size_bytes: int
    s3_key: str
    message: str


class DatasetEmbedResponse(BaseModel):
    task_id: str
    files_queued: int
    message: str


# ──────────────────────────────────────────────────────────────── Helpers ──

def _dataset_to_response(dataset: DatasetModel, include_files: bool = False) -> DatasetResponse:
    files = dataset.files or []
    file_responses = None
    if include_files:
        file_responses = [
            DatasetFileResponse(
                id=str(f.id),
                filename=f.filename,
                s3_key=f.s3_key,
                file_size_bytes=f.file_size_bytes,
                content_type=f.content_type,
                embed_status=f.embed_status,
                embed_task_id=f.embed_task_id,
                chunks_created=f.chunks_created,
                error=f.error,
                uploaded_at=f.uploaded_at,
            )
            for f in files
        ]

    return DatasetResponse(
        id=str(dataset.id),
        slug=dataset.slug,
        name=dataset.name,
        description=dataset.description,
        allowed_extensions=dataset.allowed_extensions or [],
        file_count=len(files),
        embedded_count=sum(1 for f in files if f.embed_status == "embedded"),
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        files=file_responses,
    )


# ──────────────────────────────────────────────────────────────── Routes ──

@router.get("/admin/datasets", response_model=DatasetListResponse, tags=["admin-datasets"])
async def list_datasets(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin=Depends(verify_admin),
) -> DatasetListResponse:
    """List all datasets."""
    async with AsyncSessionLocal() as session:
        count_result = await session.execute(select(func.count(DatasetModel.id)))
        total = count_result.scalar() or 0

        stmt = select(DatasetModel).offset(offset).limit(limit).order_by(DatasetModel.created_at.desc())
        result = await session.execute(stmt)
        datasets = result.scalars().unique().all()

        # Load files for each dataset (for counts)
        items = []
        for ds in datasets:
            await session.refresh(ds, ["files"])
            items.append(_dataset_to_response(ds, include_files=False))

    return DatasetListResponse(items=items, total=total)


@router.post("/admin/datasets", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED, tags=["admin-datasets"])
async def create_dataset(
    body: DatasetCreateRequest,
    admin=Depends(verify_admin),
) -> DatasetResponse:
    """Create a new dataset."""
    async with AsyncSessionLocal() as session:
        # Check slug uniqueness
        existing = await session.execute(select(DatasetModel).where(DatasetModel.slug == body.slug))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Slug '{body.slug}' already exists")

        dataset = DatasetModel(
            id=uuid.uuid4(),
            slug=body.slug,
            name=body.name,
            description=body.description,
            allowed_extensions=body.allowed_extensions,
        )
        session.add(dataset)
        await session.commit()
        await session.refresh(dataset, ["files"])

    logger.info("Dataset created", slug=dataset.slug)
    return _dataset_to_response(dataset, include_files=True)


@router.get("/admin/datasets/{slug}", response_model=DatasetResponse, tags=["admin-datasets"])
async def get_dataset(slug: str, admin=Depends(verify_admin)) -> DatasetResponse:
    """Get a dataset with its file list."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(DatasetModel).where(DatasetModel.slug == slug))
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
        await session.refresh(dataset, ["files"])
        return _dataset_to_response(dataset, include_files=True)


@router.put("/admin/datasets/{slug}", response_model=DatasetResponse, tags=["admin-datasets"])
async def update_dataset(slug: str, body: DatasetUpdateRequest, admin=Depends(verify_admin)) -> DatasetResponse:
    """Update dataset metadata."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(DatasetModel).where(DatasetModel.slug == slug))
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        if body.name is not None:
            dataset.name = body.name
        if body.description is not None:
            dataset.description = body.description
        if body.allowed_extensions is not None:
            dataset.allowed_extensions = body.allowed_extensions
        dataset.updated_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(dataset, ["files"])
        return _dataset_to_response(dataset, include_files=True)


@router.delete("/admin/datasets/{slug}", status_code=status.HTTP_204_NO_CONTENT, tags=["admin-datasets"])
async def delete_dataset(slug: str, admin=Depends(verify_admin)) -> None:
    """Delete a dataset, its DB records, and all associated S3 objects."""
    from app.services.s3_service import S3Service

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DatasetModel).where(DatasetModel.slug == slug)
        )
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        # Collect S3 keys before cascade-deleting the records
        await session.refresh(dataset, ["files"])
        s3_keys = [f.s3_key for f in dataset.files if f.s3_key]

        await session.delete(dataset)
        await session.commit()

    # Best-effort S3 cleanup after DB records are gone (avoids orphaned objects)
    if s3_keys:
        s3 = S3Service(
            bucket=settings.aws_s3_bucket,
            region=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url or None,
        )
        for key in s3_keys:
            try:
                await s3.delete_file(key)
            except Exception:
                logger.warning("Failed to delete S3 object during dataset cleanup", s3_key=key, slug=slug)

    logger.info("Dataset deleted", slug=slug, s3_objects_removed=len(s3_keys))


@router.post("/admin/datasets/{slug}/upload", response_model=DatasetUploadResponse, tags=["admin-datasets"])
async def upload_file_to_dataset(
    slug: str,
    file: Annotated[UploadFile, File(description="File to upload to this dataset")],
    admin=Depends(verify_admin),
) -> DatasetUploadResponse:
    """Upload a file into a dataset and store it in S3."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(DatasetModel).where(DatasetModel.slug == slug))
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        # Validate extension
        if not file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided")

        _, ext = os.path.splitext(file.filename.lower())
        allowed = dataset.allowed_extensions or []
        if allowed and ext not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type '{ext}' not allowed for this dataset. Allowed: {', '.join(allowed)}",
            )

        contents = await file.read()
        size = len(contents)

        max_bytes = settings.document_max_file_size_mb * 1024 * 1024
        if size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds {settings.document_max_file_size_mb} MB limit",
            )

        # Upload to S3
        from app.services.s3_service import S3Service

        s3 = S3Service(
            bucket=settings.aws_s3_bucket,
            region=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url or None,
        )
        date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        s3_key = f"datasets/{slug}/{date_prefix}/{file.filename}"
        await s3.upload_file(contents, s3_key, content_type=file.content_type or "application/octet-stream")

        # Persist record
        file_record = DatasetFileModel(
            id=uuid.uuid4(),
            dataset_id=dataset.id,
            filename=file.filename,
            s3_key=s3_key,
            file_size_bytes=size,
            content_type=file.content_type,
            embed_status="pending",
        )
        session.add(file_record)
        await session.commit()

    logger.info("File uploaded to dataset", slug=slug, filename=file.filename, s3_key=s3_key)
    return DatasetUploadResponse(
        file_id=str(file_record.id),
        filename=file.filename,
        file_size_bytes=size,
        s3_key=s3_key,
        message="File uploaded successfully. Run embed to prepare for search.",
    )


@router.post("/admin/datasets/{slug}/embed", response_model=DatasetEmbedResponse, tags=["admin-datasets"])
async def embed_dataset(slug: str, admin=Depends(verify_admin)) -> DatasetEmbedResponse:
    """Trigger document ingestion + embedding for all pending/failed files in the dataset."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(DatasetModel).where(DatasetModel.slug == slug))
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        await session.refresh(dataset, ["files"])
        files_to_embed = [f for f in dataset.files if f.embed_status in ("pending", "failed")]

        if not files_to_embed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No pending or failed files to embed",
            )

        from app.tasks.document_ingest import ingest_document_from_s3

        task_ids = []
        for f in files_to_embed:
            task = ingest_document_from_s3.delay(
                s3_key=f.s3_key,
                bucket=settings.aws_s3_bucket,
                filename=f.filename,
            )
            f.embed_status = "processing"
            f.embed_task_id = task.id
            task_ids.append(task.id)

        await session.commit()

    # Return the first task_id for polling convenience
    logger.info("Embedding triggered", slug=slug, files=len(files_to_embed))
    return DatasetEmbedResponse(
        task_id=task_ids[0] if task_ids else "",
        files_queued=len(files_to_embed),
        message=f"Embedding started for {len(files_to_embed)} file(s)",
    )


@router.get("/admin/datasets/{slug}/files/{file_id}/status", tags=["admin-datasets"])
async def get_file_embed_status(slug: str, file_id: str, admin=Depends(verify_admin)) -> dict:
    """Get embedding status for a single file."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DatasetFileModel).where(DatasetFileModel.id == uuid.UUID(file_id))
        )
        file_record = result.scalar_one_or_none()
        if not file_record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

        # If task is running, check Celery for status updates
        if file_record.embed_status == "processing" and file_record.embed_task_id:
            from app.tasks.document_ingest import ingest_document_from_s3
            task_result = ingest_document_from_s3.AsyncResult(file_record.embed_task_id)
            if task_result.state == "SUCCESS":
                info = task_result.result or {}
                file_record.embed_status = "embedded"
                file_record.chunks_created = info.get("chunks_created")
                await session.commit()
            elif task_result.state in ("FAILURE", "REVOKED"):
                file_record.embed_status = "failed"
                file_record.error = str(task_result.result)
                await session.commit()

        return {
            "file_id": str(file_record.id),
            "filename": file_record.filename,
            "embed_status": file_record.embed_status,
            "chunks_created": file_record.chunks_created,
            "error": file_record.error,
        }
