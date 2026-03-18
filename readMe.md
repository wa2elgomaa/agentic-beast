# Start local environment
cd backend
docker-compose up -d  # PostgreSQL, Redis, MongoDB, Prometheus, Grafana

# Run migrations
alembic upgrade head

# Start app
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -e .
uvicorn src.app.main:app --reload

# Start Celery worker & beat
celery -A app.tasks.celery_app:celery_app worker -l info
celery -A app.tasks.celery_app:celery_app worker -l info --pool=solo --concurrency=1

# Test analytics query via API
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What was our reach on Instagram last week?"}'

# Trigger Gmail ingestion
curl -X POST http://localhost:8000/api/v1/ingest/trigger \
  -H "Content-Type: application/json" \
  -d '{"source": "gmail"}'