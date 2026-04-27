# Local LLM Quick Start (5-Minute Setup)
**Time**: 5 minutes to running locally
**Difficulty**: Easy
**Date**: 2026-03-18

---

## TL;DR - Fastest Path

```bash
# Step 1: Install Ollama (2 min)
# macOS: brew install ollama
# Linux: curl -fsSL https://ollama.ai/install.sh | sh
# Windows: Download https://ollama.ai

# Step 2: Pull a model (1 min)
ollama pull mistral

# Step 3: Update backend code (see below - 2 min)

# Step 4: Run your app
docker-compose up
```

---

## Step-by-Step Changes

### 1. File: Update `backend/src/app/config.py`

Find the line `ai_provider: Literal["openai", "bedrock"]` and change to:

```python
ai_provider: Literal["openai", "bedrock", "ollama"] = Field(default="openai")
```

Add after the Bedrock config:

```python
# Ollama Local LLM Configuration
main_model_base_url: str = Field(default="http://localhost:11434")
main_model: str = Field(default="mistral")
main_model: str = Field(default="nomic-embed-text")
```

### 2. File: Create `backend/src/app/providers/ollama_provider.py`

**Already created above** - use the file from the previous section. Just copy and paste the entire content into a new file.

### 3. File: Update `backend/src/app/providers/__init__.py`

Replace the entire file with:

```python
"""AI provider factory and implementations."""

from app.config import settings
from app.logging import get_logger
from app.providers.base import AIProvider
from app.providers.bedrock_provider import BedrockProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.ollama_provider import OllamaProvider

logger = get_logger(__name__)


def get_ai_provider() -> AIProvider:
    """Get the configured AI provider instance."""
    if settings.main_llm_provider == "openai":
        logger.info("Using OpenAI provider")
        return OpenAIProvider()
    elif settings.main_llm_provider == "bedrock":
        logger.info("Using AWS Bedrock provider")
        return BedrockProvider()
    elif settings.main_llm_provider == "ollama":
        logger.info("Using Ollama local LLM provider")
        return OllamaProvider()
    else:
        raise ValueError(f"Unknown AI provider: {settings.main_llm_provider}")


__all__ = ["get_ai_provider", "AIProvider", "OpenAIProvider", "BedrockProvider", "OllamaProvider"]
```

### 4. File: Update `backend/.env`

Add these lines (or change if they exist):

```bash
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

### 5. File: Update `backend/docker-compose.yml` (Optional)

Add Ollama service to existing docker-compose.yml:

```yaml
services:
  # ... existing services ...

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0:11434
    pull_policy: always

volumes:
  # ... existing volumes ...
  ollama_data:
```

---

## Installation & Running

### Local Installation (Easiest)

```bash
# 1. Install Ollama
# macOS:
brew install ollama

# Linux:
curl -fsSL https://ollama.ai/install.sh | sh

# Windows:
# Download from https://ollama.ai

# 2. Start Ollama server (in background or new terminal)
ollama serve

# 3. Pull a model
ollama pull mistral

# 4. Verify it works
curl http://localhost:11434/api/tags

# 5. Start your app
cd backend
docker-compose up

# 6. Test
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"message": "What is 2+2?"}'
```

### Docker Installation (Recommended)

```bash
# Update docker-compose.yml (see step 5 above)

# Start everything
docker-compose up -d

# Pull models in container
docker exec ollama ollama pull mistral
docker exec ollama ollama pull nomic-embed-text

# Verify
curl http://localhost:11434/api/tags

# Check logs
docker logs ollama
docker logs fastapi
```

---

## Verify It's Working

### Check Ollama is Running
```bash
curl http://localhost:11434/api/tags
```

**Expected output**:
```json
{
  "models": [
    {
      "name": "mistral:latest",
      "modified_at": "2024-01-15T10:30:00.000Z",
      "size": 3826087936,
      "digest": "abc123..."
    }
  ]
}
```

### Check API is Using Ollama
```bash
# Look for "Using Ollama local LLM provider" in logs
docker logs fastapi | grep -i ollama

# Or manually test:
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "conversation_id": "test",
    "message": "Hello, what is your name?"
  }'
```

**Expected**:
- Response should come from local Ollama (slower than OpenAI, ~1-3 seconds)
- No OpenAI API calls should be made

---

## Model Selection Quick Guide

### Fastest (Development)
```bash
OLLAMA_MODEL=orca-mini      # 3B - very fast
```

### Balanced (Production)
```bash
OLLAMA_MODEL=mistral        # 7B - good quality + speed
```

### Best Quality (Slower)
```bash
OLLAMA_MODEL=llama2         # 7B - best responses
```

### Pull Command
```bash
ollama pull mistral
ollama pull orca-mini
ollama pull llama2
ollama pull neural-chat
```

---

## Troubleshooting

### "Cannot connect to Ollama"
```bash
# Make sure Ollama is running
ollama serve

# Or check if Docker service is up
docker exec ollama ollama serve

# Check if port 11434 is open
curl http://localhost:11434/api/tags
```

### "Model not found"
```bash
# Pull the model first
ollama pull mistral

# Or change to available model
OLLAMA_MODEL=orca-mini
```

### "Out of memory"
```bash
# Use smaller model
OLLAMA_MODEL=orca-mini      # Instead of mistral/llama2

# Or increase system RAM
# Docker Desktop → Settings → Resources → Memory
```

### Slow responses
```bash
# Expected with local LLM (1-5 seconds)
# Use faster model:
OLLAMA_MODEL=mistral        # ~2s instead of 5s
OLLAMA_MODEL=orca-mini      # ~1s but lower quality
```

---

## Compare Before/After

### Before (OpenAI)
```bash
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
# Cost: $0.01-0.1 per request
# Speed: 0.5-2 seconds (very fast)
# Privacy: Data sent to OpenAI
# Dependency: Requires internet + API key
```

### After (Ollama)
```bash
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral
# Cost: $0 (one-time hardware)
# Speed: 1-5 seconds (slower but acceptable)
# Privacy: 100% local (no external calls)
# Dependency: Only local hardware
```

---

## Performance Expectations

| Task | Expected Time |
|------|---|
| First startup | 5-10 seconds |
| First model pull | 5-10 minutes (one-time) |
| Analytics query response | 1-3 seconds |
| Embedding generation | 0.5-2 seconds |
| Context-aware response | 2-5 seconds |

---

## Files Modified

```
backend/src/app/
├── config.py              (✏️ Modified - add ollama settings)
├── providers/
│   ├── __init__.py        (✏️ Modified - register ollama)
│   └── ollama_provider.py (📄 New file)
backend/
├── .env                   (✏️ Modified - set AI_PROVIDER=ollama)
└── docker-compose.yml     (✏️ Modified - add ollama service)
```

---

## Rollback to OpenAI (If Needed)

```bash
# Just change one line in .env
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Restart
docker-compose restart fastapi
```

---

## Next Level: Hybrid Mode

Want safety? Use local Ollama, fallback to OpenAI if it fails:

```python
# In providers/__init__.py
elif settings.main_llm_provider == "hybrid":
    return HybridProvider()  # Tries Ollama first, then OpenAI
```

See `LOCAL_LLM_SETUP.md` for full hybrid implementation.

---

## FAQs

**Q: Will this work without internet?**
A: Yes! Once models are downloaded, you don't need internet. Works completely offline.

**Q: Can I use different models for chat vs embeddings?**
A: Yes!
```bash
OLLAMA_MODEL=mistral              # Fast chat
OLLAMA_EMBEDDING_MODEL=nomic-embed-text  # Embeddings
```

**Q: Is it as good as OpenAI?**
A: Not quite, but close enough for most uses. Mistral 7B is ~80-90% as capable as GPT-3.5.

**Q: Can I run on GPU?**
A: Yes! Ollama auto-detects GPU (NVIDIA, AMD, Apple Silicon).

**Q: How much RAM do I need?**
A: 4GB for Mistral 7B, 2GB for Orca-Mini 3B.

**Q: Can I deploy to production?**
A: Yes! See `LOCAL_LLM_SETUP.md` for production deployment.

---

## Success Checklist

- [ ] Ollama installed
- [ ] Model pulled (`ollama pull mistral`)
- [ ] `config.py` updated with ollama settings
- [ ] `ollama_provider.py` created
- [ ] `providers/__init__.py` updated
- [ ] `.env` set to `AI_PROVIDER=ollama`
- [ ] App restarted
- [ ] API responds without OpenAI calls
- [ ] Responses are correct (but slower)

---

**You're done!** Your system now runs LLMs locally without any external dependencies.

For advanced options, see `LOCAL_LLM_SETUP.md`.
