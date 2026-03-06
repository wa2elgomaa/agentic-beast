# Start local environment
cd backend
docker-compose up -d  # PostgreSQL, Redis, MongoDB, Prometheus, Grafana

# Run migrations
alembic upgrade head

# Start app
uvicorn src.app.main:app --reload

# Start Celery worker & beat
celery -A src.app.tasks.celery_app worker --loglevel=info
celery -A src.app.tasks.celery_app beat --loglevel=info

# Test analytics query via API
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What was our reach on Instagram last week?"}'

# Trigger Gmail ingestion
curl -X POST http://localhost:8000/api/v1/ingest/trigger \
  -H "Content-Type: application/json" \
  -d '{"source": "gmail"}'