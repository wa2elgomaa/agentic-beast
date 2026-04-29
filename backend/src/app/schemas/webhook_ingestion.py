"""Pydantic schemas for webhook ingestion endpoints."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class WebhookPayload(BaseModel):
    """Generic webhook payload structure."""
    
    source: str = Field(..., description="Webhook source (e.g., 'cms')")
    event_type: str = Field(..., description="Event type (e.g., 'article.published')")
    event_id: Optional[str] = Field(None, description="Unique event ID for deduplication")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event-specific data")


class ArticleWebhookData(BaseModel):
    """Article-specific webhook data."""
    
    article_id: str = Field(..., description="Article ID from CMS")
    title: Optional[str] = Field(None, description="Article title")
    content: Optional[str] = Field(None, description="Article body/content")
    published_at: Optional[datetime] = Field(None, description="Publication timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class WebhookResult(BaseModel):
    """Webhook processing result."""
    
    event_id: Optional[str] = Field(None, description="Event ID from payload")
    routed_to: str = Field(..., description="Which agent/handler processed it")
    status: str = Field(..., description="Processing status (queued, processing, completed, failed)")
    message: Optional[str] = Field(None, description="Status message or error details")
