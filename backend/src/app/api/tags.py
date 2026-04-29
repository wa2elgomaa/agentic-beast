"""Tags API router for admin CRUD operations (Phase 2).

Endpoints for managing tags:
- GET /admin/tags — list all tags
- POST /admin/tags — create tag
- PUT /admin/tags/{slug} — update tag
- DELETE /admin/tags/{slug} — delete tag
- POST /admin/tags/bulk-upload — upload multiple tags
- POST /admin/tags/re-embed — trigger re-embedding
- GET /admin/tags/embed-status/{task_id} — check embedding progress

All endpoints protected by admin JWT role claim.
"""

from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
import structlog
import csv
import io

from app.schemas.tags_api import (
    TagCreateRequest,
    TagUpdateRequest,
    TagResponse,
    TagListResponse,
    TagBulkUploadRequest,
    TagBulkUploadResponse,
    TagReEmbedRequest,
    TagReEmbedResponse,
    TagReEmbedStatusResponse,
    TagFeedbackRequest,
    TagFeedbackResponse,
)
from app.auth import verify_admin
from app.db.session import AsyncSessionLocal
from app.schemas.tag import Tag as TagModel
from sqlalchemy import select, delete, func

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/admin/tags", response_model=TagListResponse, tags=["admin-tags"])
async def list_tags(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin=Depends(verify_admin),
) -> TagListResponse:
    """List all tags with pagination.

    **Required**: Admin role

    Useful for admin dashboard tag management page.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Get total count
            count_result = await session.execute(select(func.count(TagModel.slug)))
            total = count_result.scalar() or 0

            # Fetch paginated results
            stmt = select(TagModel).offset(offset).limit(limit)
            result = await session.execute(stmt)
            tags = result.scalars().all()

            items = [
                TagResponse(
                    slug=tag.slug,
                    name=tag.name,
                    description=tag.description,
                    variations=tag.variations,
                    is_primary=tag.is_primary,
                    embedding_dim=384 if tag.embedding else None,
                    created_at=tag.created_at,
                    updated_at=tag.updated_at,
                )
                for tag in tags
            ]

            return TagListResponse(
                items=items,
                total=total,
                limit=limit,
                offset=offset,
            )

    except Exception as exc:
        logger.error("Failed to list tags", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list tags",
        ) from exc


@router.post("/admin/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED, tags=["admin-tags"])
async def create_tag(
    request: TagCreateRequest,
    admin=Depends(verify_admin),
) -> TagResponse:
    """Create a new tag.

    **Required**: Admin role

    Returns the created tag with response schema.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Check if tag already exists
            stmt = select(TagModel).where(TagModel.slug == request.slug)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Tag with slug '{request.slug}' already exists",
                )

            # Create new tag (without embedding for now — can be added via re-embed)
            tag = TagModel(
                slug=request.slug,
                name=request.name,
                description=request.description,
                variations=request.variations,
                is_primary=request.is_primary,
            )
            session.add(tag)
            await session.commit()
            await session.refresh(tag)

            logger.info("Tag created", slug=tag.slug, name=tag.name)

            return TagResponse(
                slug=tag.slug,
                name=tag.name,
                description=tag.description,
                variations=tag.variations,
                is_primary=tag.is_primary,
                embedding_dim=None,
                created_at=tag.created_at,
                updated_at=tag.updated_at,
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to create tag", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create tag",
        ) from exc


@router.put("/admin/tags/{slug}", response_model=TagResponse, tags=["admin-tags"])
async def update_tag(
    slug: str,
    request: TagUpdateRequest,
    admin=Depends(verify_admin),
) -> TagResponse:
    """Update an existing tag.

    **Required**: Admin role

    If re_embed=true, triggers async embedding task for this tag.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Fetch tag
            stmt = select(TagModel).where(TagModel.slug == slug)
            result = await session.execute(stmt)
            tag = result.scalar_one_or_none()

            if not tag:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tag '{slug}' not found",
                )

            # Update fields
            if request.name is not None:
                tag.name = request.name
            if request.description is not None:
                tag.description = request.description
            if request.variations is not None:
                tag.variations = request.variations
            if request.is_primary is not None:
                tag.is_primary = request.is_primary

            await session.commit()
            await session.refresh(tag)

            logger.info("Tag updated", slug=tag.slug)

            # Trigger re-embedding if requested
            if request.re_embed:
                from app.tasks.tag_embedding import re_embed_tags_task
                re_embed_tags_task.delay(tag_slugs=[slug])
                logger.info("Re-embedding task triggered", slug=slug)

            return TagResponse(
                slug=tag.slug,
                name=tag.name,
                description=tag.description,
                variations=tag.variations,
                is_primary=tag.is_primary,
                embedding_dim=384 if tag.embedding else None,
                created_at=tag.created_at,
                updated_at=tag.updated_at,
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update tag", slug=slug, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update tag",
        ) from exc


@router.delete("/admin/tags/{slug}", status_code=status.HTTP_204_NO_CONTENT, tags=["admin-tags"])
async def delete_tag(
    slug: str,
    admin=Depends(verify_admin),
) -> None:
    """Delete a tag by slug.

    **Required**: Admin role
    """
    try:
        async with AsyncSessionLocal() as session:
            # Fetch tag
            stmt = select(TagModel).where(TagModel.slug == slug)
            result = await session.execute(stmt)
            tag = result.scalar_one_or_none()

            if not tag:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tag '{slug}' not found",
                )

            await session.delete(tag)
            await session.commit()

            logger.info("Tag deleted", slug=slug)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to delete tag", slug=slug, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete tag",
        ) from exc


@router.post("/admin/tags/bulk-upload", response_model=TagBulkUploadResponse, tags=["admin-tags"])
async def bulk_upload_tags(
    file: Annotated[UploadFile, File(description="CSV or XLSX file with tags")],
    auto_embed: bool = Query(default=True),
    skip_duplicates: bool = Query(default=True),
    admin=Depends(verify_admin),
) -> TagBulkUploadResponse:
    """Bulk upload tags from a CSV or XLSX file.

    **Required**: Admin role

    Expected columns: slug, name, description (optional), variations (semicolon-separated, optional), is_primary (Y/N, optional)

    If auto_embed=true, triggers async embedding task after upload.
    """
    try:
        contents = await file.read()
        filename = (file.filename or "").lower()

        # Parse rows from CSV or XLSX
        rows: list[dict] = []
        if filename.endswith(".xlsx") or file.content_type in (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ):
            try:
                import openpyxl
                from io import BytesIO

                wb = openpyxl.load_workbook(BytesIO(contents), read_only=True, data_only=True)
                ws = wb.active
                headers = None
                for row in ws.iter_rows(values_only=True):
                    if headers is None:
                        headers = [str(c).strip() if c is not None else "" for c in row]
                    else:
                        rows.append({headers[i]: (str(v).strip() if v is not None else "") for i, v in enumerate(row)})
            except ImportError:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="openpyxl not installed; upload a CSV file instead")
        else:
            csv_reader = csv.DictReader(io.StringIO(contents.decode("utf-8")))
            rows = list(csv_reader)

        created_count = 0
        skipped_count = 0
        failed_count = 0
        errors = []

        async with AsyncSessionLocal() as session:
            for row_num, row in enumerate(rows, start=2):  # Start at 2 (skip header)
                try:
                    slug = row.get("slug", "").strip()
                    name = row.get("name", "").strip()

                    if not slug or not name:
                        errors.append(f"Row {row_num}: Missing slug or name")
                        failed_count += 1
                        continue

                    # Check for duplicate
                    stmt = select(TagModel).where(TagModel.slug == slug)
                    result = await session.execute(stmt)
                    if result.scalar_one_or_none():
                        if skip_duplicates:
                            skipped_count += 1
                            continue
                        else:
                            errors.append(f"Row {row_num}: Slug '{slug}' already exists")
                            failed_count += 1
                            continue

                    # Parse variations
                    variations_str = row.get("variations", "").strip()
                    variations = [v.strip() for v in variations_str.split(";") if v.strip()] if variations_str else None

                    # Parse is_primary
                    is_primary_str = row.get("is_primary", "N").strip().upper()
                    is_primary = is_primary_str in ("Y", "YES", "TRUE", "1")

                    # Create tag
                    tag = TagModel(
                        slug=slug,
                        name=name,
                        description=row.get("description", "").strip() or None,
                        variations=variations,
                        is_primary=is_primary,
                    )
                    session.add(tag)
                    created_count += 1

                except Exception as exc:
                    errors.append(f"Row {row_num}: {str(exc)}")
                    failed_count += 1

            await session.commit()

        logger.info(
            "Bulk upload completed",
            created=created_count,
            skipped=skipped_count,
            failed=failed_count,
        )

        # Trigger re-embedding if requested
        embedding_task_id = None
        if auto_embed and created_count > 0:
            from app.tasks.tag_embedding import re_embed_tags_task
            task = re_embed_tags_task.delay()
            embedding_task_id = task.id
            logger.info("Re-embedding task triggered after bulk upload", task_id=embedding_task_id)

        return TagBulkUploadResponse(
            created_count=created_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            errors=errors,
            embedding_task_id=embedding_task_id,
        )

    except Exception as exc:
        logger.error("Bulk upload failed", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bulk upload failed",
        ) from exc


@router.post("/admin/tags/re-embed", response_model=TagReEmbedResponse, tags=["admin-tags"])
async def trigger_tag_re_embedding(
    request: TagReEmbedRequest,
    admin=Depends(verify_admin),
) -> TagReEmbedResponse:
    """Trigger re-embedding (vector generation) for tags.

    **Required**: Admin role

    If tag_slugs is provided, re-embeds only those tags.
    If tag_slugs is None, re-embeds all tags.

    Uses Celery for async processing.
    """
    try:
        from app.tasks.tag_embedding import re_embed_tags_task

        # If specific slugs provided, use them; otherwise None (all tags)
        tag_slugs = request.tag_slugs if request.tag_slugs else None

        # Submit task
        task = re_embed_tags_task.delay(
            tag_slugs=tag_slugs,
            batch_size=request.batch_size,
        )

        # Calculate batch count
        if tag_slugs:
            tags_to_embed = len(tag_slugs)
        else:
            # Count all tags in DB
            async with AsyncSessionLocal() as session:
                count_result = await session.execute(select(func.count(TagModel.slug)))
                tags_to_embed = count_result.scalar() or 0

        batch_count = (tags_to_embed + request.batch_size - 1) // request.batch_size

        logger.info(
            "Re-embedding task submitted",
            task_id=task.id,
            tags_to_embed=tags_to_embed,
            batch_count=batch_count,
        )

        return TagReEmbedResponse(
            task_id=task.id,
            tags_to_embed=tags_to_embed,
            batch_count=batch_count,
        )

    except Exception as exc:
        logger.error("Failed to submit re-embedding task", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit re-embedding task",
        ) from exc


@router.get("/admin/tags/embed-status/{task_id}", response_model=TagReEmbedStatusResponse, tags=["admin-tags"])
async def get_embedding_status(
    task_id: str,
    admin=Depends(verify_admin),
) -> TagReEmbedStatusResponse:
    """Get status of a tag re-embedding task.

    **Required**: Admin role

    Check progress of async embedding via Celery task ID.
    """
    from app.tasks.celery_app import celery_app

    try:
        task = celery_app.AsyncResult(task_id)

        if task.state == "PENDING":
            return TagReEmbedStatusResponse(
                task_id=task_id,
                status="pending",
                embedded_count=0,
                failed_count=0,
                total_count=0,
                progress_percent=0,
            )
        elif task.state == "PROGRESS":
            info = task.info or {}
            return TagReEmbedStatusResponse(
                task_id=task_id,
                status="in_progress",
                embedded_count=info.get("embedded", 0),
                failed_count=info.get("failed", 0),
                total_count=info.get("total", 0),
                progress_percent=int((info.get("embedded", 0) / max(info.get("total", 1), 1)) * 100),
            )
        elif task.state == "SUCCESS":
            result = task.result or {}
            return TagReEmbedStatusResponse(
                task_id=task_id,
                status="completed",
                embedded_count=result.get("embedded", 0),
                failed_count=result.get("failed", 0),
                total_count=result.get("total", 0),
                progress_percent=100,
            )
        elif task.state == "FAILURE":
            return TagReEmbedStatusResponse(
                task_id=task_id,
                status="failed",
                embedded_count=0,
                failed_count=0,
                total_count=0,
                progress_percent=0,
                error=str(task.info),
            )
        else:
            return TagReEmbedStatusResponse(
                task_id=task_id,
                status=task.state.lower(),
                embedded_count=0,
                failed_count=0,
                total_count=0,
                progress_percent=0,
            )

    except Exception as exc:
        logger.error("Failed to get embedding status", task_id=task_id, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get embedding status",
        ) from exc


@router.post("/api/tags/feedback", response_model=TagFeedbackResponse, tags=["tags"])
async def record_tag_feedback(
    request: TagFeedbackRequest,
) -> TagFeedbackResponse:
    """Record tag feedback from CMS editor.

    CMS calls this after editor saves tag selections for an article.
    Compares suggested_tags vs. kept_tags to measure tag acceptance rate (SC-003).

    Args:
        article_id: Article being tagged
        suggested_tags: Tags suggested by ML model (slugs)
        kept_tags: Tags kept by editor (slugs)

    Returns:
        Number of feedback records created (one per suggested tag).
    """
    try:
        async with AsyncSessionLocal() as session:
            feedback_records = 0

            # Record feedback for each tag that was suggested
            for tag_slug in request.suggested_tags:
                was_kept = tag_slug in request.kept_tags

                # Insert into tag_feedback table
                # Use raw SQL since we may not have an ORM model defined
                from sqlalchemy import text

                await session.execute(
                    text("""
                        INSERT INTO tag_feedback (article_id, tag_slug, was_kept)
                        VALUES (:article_id, :tag_slug, :was_kept)
                    """),
                    {
                        "article_id": request.article_id,
                        "tag_slug": tag_slug,
                        "was_kept": was_kept,
                    },
                )
                feedback_records += 1

            await session.commit()

            logger.info(
                "Tag feedback recorded",
                article_id=request.article_id,
                suggested_count=len(request.suggested_tags),
                kept_count=len(request.kept_tags),
                feedback_records=feedback_records,
            )

            return TagFeedbackResponse(
                article_id=request.article_id,
                feedback_records=feedback_records,
                message="Tag feedback recorded successfully",
            )

    except Exception as exc:
        logger.error("Failed to record tag feedback", article_id=request.article_id, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record tag feedback",
        ) from exc
