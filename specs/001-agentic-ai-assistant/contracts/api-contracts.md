# API Contracts: Agentic AI Assistant Platform

**Feature**: 001-agentic-ai-assistant
**Date**: 2026-03-05

## Chat API

### POST /api/v1/chat

Send a message and receive an assistant response.

**Request**:
```json
{
  "message": "What was our total reach on Instagram last week?",
  "conversation_id": "uuid-optional",
  "options": {
    "max_tokens": 1000
  }
}
```

**Response** (200):
```json
{
  "message": {
    "id": "uuid",
    "role": "assistant",
    "content": "Your total reach on Instagram last week was 125,430...",
    "operation": "query_analytics",
    "operation_data": {
      "query": {"metric": "total_reach", "platform": "instagram", "date_range": {"start": "2026-02-26", "end": "2026-03-04"}},
      "results": [{"total_reach": 125430}]
    },
    "operation_metadata": {
      "duration_ms": 2340,
      "model": "gpt-4",
      "tokens_used": 450
    }
  },
  "conversation_id": "uuid"
}
```

### GET /api/v1/conversations

List user conversations.

**Query params**: `limit` (int, default 20), `offset` (int, default 0)

**Response** (200):
```json
{
  "conversations": [
    {
      "id": "uuid",
      "title": "Instagram Analytics",
      "updated_at": "2026-03-05T10:30:00Z",
      "message_count": 5
    }
  ],
  "total": 42
}
```

### GET /api/v1/conversations/{id}/messages

Get messages for a conversation.

**Response** (200):
```json
{
  "messages": [
    {
      "id": "uuid",
      "role": "user",
      "content": "What was our reach last week?",
      "created_at": "2026-03-05T10:30:00Z",
      "sequence_number": 1
    },
    {
      "id": "uuid",
      "role": "assistant",
      "content": "Your total reach last week was...",
      "operation": "query_analytics",
      "operation_data": {},
      "created_at": "2026-03-05T10:30:02Z",
      "sequence_number": 2
    }
  ]
}
```

## Ingestion API

### POST /api/v1/ingest/trigger

Manually trigger Gmail inbox check and ingestion.

**Request**: (empty body)

**Response** (202):
```json
{
  "task_id": "celery-task-uuid",
  "status": "queued",
  "message": "Ingestion task queued"
}
```

### GET /api/v1/ingest/status/{task_id}

Check ingestion task status.

**Response** (200):
```json
{
  "task_id": "celery-task-uuid",
  "status": "completed",
  "result": {
    "emails_processed": 3,
    "rows_inserted": 1250,
    "rows_updated": 0,
    "rows_failed": 5,
    "errors": [
      {"row": 42, "error": "Missing required field: platform"}
    ],
    "duration_ms": 45000
  }
}
```

## Document API

### POST /api/v1/documents/upload

Upload a company document for processing.

**Request**: `multipart/form-data`
- `file`: The document file (PDF, XLSX, TXT, images)
- `title`: Optional document title
- `category`: Optional category (e.g., "hr", "policy", "operations")

**Response** (202):
```json
{
  "task_id": "celery-task-uuid",
  "status": "processing",
  "document_name": "hr-policy-2026.pdf",
  "message": "Document queued for processing"
}
```

## Authentication API

### POST /api/v1/auth/login

Authenticate and receive JWT token.

**Request**:
```json
{
  "username": "john.doe",
  "password": "***",
  "provider": "local"
}
```

**Response** (200):
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "uuid",
    "username": "john.doe",
    "full_name": "John Doe",
    "is_admin": false
  }
}
```

## Health API

### GET /api/v1/health

System health check.

**Response** (200):
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "agents": {
    "analytics": "healthy",
    "ingestion": "healthy",
    "tagging": "healthy",
    "recommendation": "healthy",
    "document": "healthy",
    "general": "healthy"
  },
  "services": {
    "postgresql": "connected",
    "redis": "connected",
    "celery": "connected"
  }
}
```

## Internal Contracts

### DataAdapter Interface

```python
class DataAdapter(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def fetch_data(self, **kwargs) -> list[dict]: ...

    @abstractmethod
    async def get_status(self) -> AdapterStatus: ...

    @property
    @abstractmethod
    def adapter_name(self) -> str: ...
```

### AI Provider Interface

```python
class AIProvider(ABC):
    @abstractmethod
    async def complete(self, messages: list[Message], **kwargs) -> CompletionResponse: ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...
```

### Structured Query Schema

```python
class AnalyticsQuery(BaseModel):
    metric: str  # e.g., "total_reach", "total_interactions"
    aggregation: str = "sum"  # "sum", "avg", "max", "min", "count"
    platform: str | None = None
    profile_name: str | None = None
    date_range: DateRange | None = None
    group_by: list[str] = []  # e.g., ["platform", "date"]
    order_by: str | None = None
    limit: int = 10

class DateRange(BaseModel):
    start: date
    end: date
```

## Error Response Format

All error responses follow a consistent format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable error description",
    "details": {}
  }
}
```

Standard error codes: `VALIDATION_ERROR`, `NOT_FOUND`, `UNAUTHORIZED`, `RATE_LIMITED`, `PROVIDER_ERROR`, `INGESTION_ERROR`, `INTERNAL_ERROR`
