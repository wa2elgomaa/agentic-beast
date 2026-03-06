# Quickstart: Agentic AI Assistant Platform

**Feature**: 001-agentic-ai-assistant
**Date**: 2026-03-05

## Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Gmail account with API access (for ingestion)
- OpenAI API key (or AWS Bedrock credentials)

## Setup

### 1. Clone and Install

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Start Infrastructure

```bash
docker-compose up -d  # PostgreSQL, Redis
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys:
# OPENAI_API_KEY=sk-...
# GMAIL_CREDENTIALS_PATH=./credentials.json
# DATABASE_URL=postgresql+asyncpg://beast:beast@localhost:5432/beast
# REDIS_URL=redis://localhost:6379/0
```

### 4. Run Database Migrations

```bash
alembic upgrade head
```

### 5. Start the Application

```bash
# Terminal 1: FastAPI server
uvicorn backend.src.app.main:app --reload --port 8000

# Terminal 2: Celery worker (for background tasks)
celery -A backend.src.app.tasks.celery_app worker --loglevel=info

# Terminal 3: Celery beat (for scheduled email monitoring)
celery -A backend.src.app.tasks.celery_app beat --loglevel=info
```

## Verification Scenarios

### V1: Health Check

```bash
curl http://localhost:8000/api/v1/health
# Expected: {"status": "healthy", "agents": {...}, "services": {...}}
```

### V2: Authentication

```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin", "provider": "local"}'
# Expected: {"access_token": "eyJ...", "token_type": "bearer", ...}
```

### V3: Analytics Query (US1)

```bash
# Ask an analytics question (requires data in documents table)
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What was our total reach on Instagram last week?"}'
# Expected: Assistant responds with aggregated reach data
```

### V4: Manual Ingestion Trigger (US2)

```bash
# Trigger Gmail inbox check
curl -X POST http://localhost:8000/api/v1/ingest/trigger \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"task_id": "...", "status": "queued"}

# Check status
curl http://localhost:8000/api/v1/ingest/status/$TASK_ID \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"status": "completed", "result": {"rows_inserted": ...}}
```

### V5: Tag Suggestion (US3)

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Suggest 5 tags for article abc123"}'
# Expected: 5 tags from tags table ranked by relevance
```

### V6: Article Recommendation (US4)

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Find 3 similar articles to abc123"}'
# Expected: 3 related articles with titles and relevance explanation
```

### V7: Document Upload (US5)

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@hr-policy.pdf" \
  -F "category=hr"
# Expected: {"task_id": "...", "status": "processing"}

# Then ask about the document
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the vacation policy?"}'
# Expected: Answer with source citation from hr-policy.pdf
```

### V8: General Assistant (US6)

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the capital of France?"}'
# Expected: "Paris" without querying internal databases
```

## Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests (requires Docker services running)
pytest tests/integration/

# Contract tests
pytest tests/contract/

# With coverage
pytest --cov=backend.src.app --cov-report=term-missing
```
