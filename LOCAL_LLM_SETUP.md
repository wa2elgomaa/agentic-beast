# Local LLM Setup Guide
**Date**: 2026-03-18
**Purpose**: Replace OpenAI/Bedrock with local LLM (Ollama, LM Studio, or Llama.cpp)
**Status**: Ready to implement

---

## Overview

Your system is **already architected for this**! The `AIProvider` abstract base class allows plugging in any LLM provider. This guide shows 3 local options:

1. **Ollama** (Recommended) - Easy setup, multiple models, REST API
2. **LM Studio** - GUI-based, beginner-friendly
3. **Llama.cpp** - Ultra-lightweight, no server

---

## Option 1: Ollama (Recommended) ⭐

### Why Ollama?
- ✅ Easy setup & installation
- ✅ Multiple models available (Llama 2, Mistral, Phi, etc.)
- ✅ REST API compatible
- ✅ Can swap models without code changes
- ✅ Runs on CPU or GPU
- ✅ Embedding models included

### Installation

**macOS/Linux**:
```bash
# Download from https://ollama.ai
curl -fsSL https://ollama.ai/install.sh | sh

# Or homebrew (macOS)
brew install ollama
```

**Windows**: Download installer from https://ollama.ai

**Docker**:
```bash
docker run -d \
  --name ollama \
  -p 11434:11434 \
  -v ollama:/root/.ollama \
  ollama/ollama
```

### Pull Models

```bash
# Pull a model (choose one)
ollama pull mistral          # Fast, 7B, good for chat
ollama pull llama2           # 7B, slower but capable
ollama pull neural-chat      # Fast chat-optimized
ollama pull orca-mini        # 3B, very fast
ollama pull nomic-embed-text # For embeddings

# Test it
ollama run mistral
```

### Verify Setup
```bash
# Should respond with model info
curl http://localhost:11434/api/tags

# Test generation
curl -X POST http://localhost:11434/api/generate -d '{
  "model": "mistral",
  "prompt": "Hello world",
  "stream": false
}'
```

---

## Option 2: LM Studio

### Installation
1. Download from https://lmstudio.ai
2. GUI-based model management
3. Built-in server (port 1234)
4. Choose models from UI

### Configuration
- Models auto-download on selection
- Server starts via menu → "Start Server"
- Default: http://localhost:1234

---

## Option 3: Llama.cpp

### Installation
```bash
# Clone and build
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
make

# Download a model (GGUF format)
wget https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/resolve/main/Mistral-7B-Instruct-v0.1.Q4_K_M.gguf

# Start server
./server -m mistral-7b-instruct-v0.1.Q4_K_M.gguf -ngl 99 --port 8000
```

---

## Implementation: Create OllamaProvider

### Step 1: Create `backend/src/app/providers/ollama_provider.py`

```python
"""Ollama local LLM provider implementation."""

import httpx
from typing import List, Optional

from app.config import settings
from app.logging import get_logger
from app.providers.base import AIProvider, CompletionResponse, Message

logger = get_logger(__name__)


class OllamaProvider(AIProvider):
    """Ollama local LLM provider implementation."""

    def __init__(self):
        """Initialize Ollama provider."""
        super().__init__(settings.main_model)
        self.base_url = settings.main_model_base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=120.0)
        logger.info("Ollama provider initialized",
                    model=self.model,
                    base_url=self.base_url)

    async def complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> CompletionResponse:
        """Generate completion using Ollama local LLM.

        Args:
            messages: List of messages in conversation.
            temperature: Sampling temperature (0-1).
            max_tokens: Maximum tokens in response.
            **kwargs: Additional provider-specific arguments.

        Returns:
            CompletionResponse with generated text.
        """
        try:
            # Format messages for Ollama
            formatted_messages = [
                {
                    "role": m.role,
                    "content": m.content
                }
                for m in messages
            ]

            # Build request
            payload = {
                "model": self.model,
                "messages": formatted_messages,
                "temperature": temperature,
                "stream": False,  # Get full response at once
            }

            # Optional: add max_tokens if supported by model
            if max_tokens:
                payload["num_predict"] = max_tokens

            # Call Ollama API
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120.0
            )
            response.raise_for_status()

            result = response.json()

            return CompletionResponse(
                content=result["message"]["content"],
                model=self.model,
                stop_reason=result.get("done", True) and "end_turn" or "continue",
                usage={
                    "prompt_tokens": result.get("prompt_eval_count", 0),
                    "completion_tokens": result.get("eval_count", 0),
                    "total_tokens": result.get("eval_count", 0) + result.get("prompt_eval_count", 0),
                }
            )

        except httpx.ConnectError as e:
            logger.error("Ollama connection error", error=str(e))
            raise RuntimeError(f"Ollama not running at {self.base_url}. Start with: ollama serve")
        except Exception as e:
            logger.error("Ollama completion error", error=str(e))
            raise

    async def embed(self, text: str) -> List[float]:
        """Generate embeddings using Ollama.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector.
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": settings.main_model,
                    "prompt": text
                },
                timeout=60.0
            )
            response.raise_for_status()

            result = response.json()
            return result.get("embedding", [])

        except Exception as e:
            logger.error("Ollama embedding error", error=str(e))
            raise

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
```

### Step 2: Update `backend/src/app/config.py`

Add these lines after the OpenAI configuration:

```python
# Local LLM Configuration (Ollama, LM Studio, etc.)
ai_provider: Literal["openai", "bedrock", "ollama", "lm_studio"] = Field(default="openai")
main_model_base_url: str = Field(default="http://localhost:11434")
main_model: str = Field(default="mistral")
main_model: str = Field(default="nomic-embed-text")
lm_studio_base_url: str = Field(default="http://localhost:1234/v1")
```

### Step 3: Update `backend/src/app/providers/__init__.py`

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
    """Get the configured AI provider instance.

    Returns:
        An AI provider instance based on configuration.
    """
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

### Step 4: Update `.env.example`

```bash
# AI Provider Selection
# Options: openai, bedrock, ollama, lm_studio
AI_PROVIDER=ollama

# Ollama Configuration (local LLM)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# OpenAI Configuration (keep for reference)
# OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4
```

---

## Quick Start: Docker Compose Setup

### Update `backend/docker-compose.yml`

Add Ollama service:

```yaml
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0:11434
    pull_policy: always
    # Uncomment for GPU support (requires nvidia-docker)
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]

volumes:
  ollama_data:
```

### Start Everything

```bash
# Start containers
docker-compose up -d

# Pull a model (inside container)
docker exec ollama ollama pull mistral

# Verify
curl http://localhost:11434/api/tags

# Update .env
echo "AI_PROVIDER=ollama" >> backend/.env

# Restart FastAPI to use Ollama
docker-compose restart fastapi
```

---

## Model Selection Guide

### For Analytics (Fast Responses)
```
Model: mistral (7B)
- Fast: ~1-2s per response
- Good reasoning for queries
- 4GB RAM minimum
Command: ollama pull mistral
```

### For Complex Reasoning
```
Model: llama2 (7B)
- Slower but more capable
- Better instruction following
- 8GB RAM recommended
Command: ollama pull llama2
```

### For Lightweight (CPU)
```
Model: orca-mini (3B)
- Very fast on CPU
- Limited reasoning
- 2GB RAM sufficient
Command: ollama pull orca-mini
```

### For Embeddings
```
Model: nomic-embed-text (137M)
- Small, fast embeddings
- Compatible with all LLMs
Command: ollama pull nomic-embed-text
```

### Mix & Match
```bash
# Use different model for chat vs embeddings
OLLAMA_MODEL=mistral              # Fast chat model
OLLAMA_EMBEDDING_MODEL=nomic-embed-text  # Embedding model
```

---

## Configuration Options by Use Case

### Development (Fastest)
```bash
AI_PROVIDER=ollama
OLLAMA_MODEL=orca-mini           # 3B, very fast
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://localhost:11434
```

### Production (Balanced)
```bash
AI_PROVIDER=ollama
OLLAMA_MODEL=mistral             # 7B, good quality/speed
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://ollama:11434  # Docker service name
```

### High Quality (Slower)
```bash
AI_PROVIDER=ollama
OLLAMA_MODEL=llama2              # 7B, best quality
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://localhost:11434
```

---

## Performance Comparison

| Model | Size | Speed | Quality | RAM | Best For |
|-------|------|-------|---------|-----|----------|
| orca-mini | 3B | ⚡⚡⚡ | ⭐⭐ | 2GB | Development |
| mistral | 7B | ⚡⚡ | ⭐⭐⭐⭐ | 4GB | Production |
| llama2 | 7B | ⚡ | ⭐⭐⭐⭐⭐ | 8GB | High Quality |
| neural-chat | 7B | ⚡⚡ | ⭐⭐⭐⭐ | 4GB | Chat |

**Speed**: Time to first token (lower=better)
**Quality**: Response quality (higher=better)

---

## GPU Acceleration

### NVIDIA GPU (CUDA)

```bash
# Install CUDA support
ollama pull mistral  # Will use GPU automatically

# Verify GPU is being used
curl http://localhost:11434/api/tags | jq '.'
```

### With Docker Compose

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

### macOS (Metal)
```bash
# Automatic with M1/M2/M3 Macs
ollama pull mistral  # Uses Metal acceleration by default
```

---

## Hybrid Mode: Local + Cloud Fallback

Want safety? Use local by default with fallback to OpenAI if it fails:

```python
"""Hybrid provider with fallback."""

from typing import List, Optional
from app.providers.base import AIProvider, CompletionResponse, Message
from app.providers.ollama_provider import OllamaProvider
from app.providers.openai_provider import OpenAIProvider
from app.logging import get_logger

logger = get_logger(__name__)


class HybridProvider(AIProvider):
    """Try local Ollama first, fallback to OpenAI."""

    def __init__(self):
        """Initialize hybrid provider."""
        super().__init__("hybrid")
        self.ollama = OllamaProvider()
        self.openai = OpenAIProvider()

    async def complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> CompletionResponse:
        """Try Ollama, fallback to OpenAI."""
        try:
            # Try local Ollama first
            logger.info("Attempting Ollama...")
            return await self.ollama.complete(
                messages, temperature, max_tokens, **kwargs
            )
        except Exception as e:
            logger.warning(f"Ollama failed: {e}, falling back to OpenAI")
            return await self.openai.complete(
                messages, temperature, max_tokens, **kwargs
            )

    async def embed(self, text: str) -> List[float]:
        """Try Ollama embeddings, fallback to OpenAI."""
        try:
            return await self.ollama.embed(text)
        except Exception:
            return await self.openai.embed(text)
```

Register in `__init__.py`:
```python
elif settings.main_llm_provider == "hybrid":
    return HybridProvider()
```

---

## Troubleshooting

### Ollama won't connect
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# If not, start it
ollama serve

# Or with Docker
docker logs ollama
```

### Model loads slowly
```bash
# Model is downloading/caching
# First run takes time. Subsequent runs are fast.
# Models cached in ~/.ollama/models/

# Check download progress
docker logs ollama
```

### Out of memory errors
```bash
# Switch to smaller model
OLLAMA_MODEL=orca-mini  # 3B instead of 7B

# Or increase system RAM allocation
# Docker Desktop → Settings → Resources → Memory
```

### GPU not being used
```bash
# Check if GPU available
docker run --rm --gpus all ollama/ollama nvidia-smi

# Force GPU in docker-compose
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

### Responses are slow
```bash
# Try faster model
OLLAMA_MODEL=mistral  # ~1-2s per response

# Or reduce max_tokens
# Smaller responses = faster generation
```

---

## Cost Analysis

### Without OpenAI (Ollama)
- **Monthly Cost**: $0 (hardware only)
- **Setup Time**: 1 hour
- **Latency**: 1-5 seconds
- **Privacy**: 100% (all local)
- **Downtime**: Only if your server is down

### With OpenAI
- **Monthly Cost**: $20-500+ (depending on usage)
- **Setup Time**: 5 minutes
- **Latency**: 0.5-2 seconds (faster)
- **Privacy**: Data sent to OpenAI
- **Downtime**: If OpenAI is down

### Recommendation
- **Development**: Use Ollama locally (free)
- **Production MVP**: Use Ollama locally + fallback to OpenAI
- **High Traffic**: Use both in hybrid mode for redundancy
- **Cost Sensitive**: Ollama only

---

## Migration Path

### Week 1: Add Ollama Support
```bash
# 1. Create ollama_provider.py (copy from above)
# 2. Update config.py (add ollama settings)
# 3. Update providers/__init__.py (register provider)
# 4. Update .env.example (add ollama variables)
# 5. Test with AI_PROVIDER=ollama
```

### Week 2: Add Docker Compose Service
```bash
# 1. Add ollama to docker-compose.yml
# 2. Add volume for model cache
# 3. Test docker-compose up
# 4. Verify models pull automatically
```

### Week 3: Hybrid Fallback (Optional)
```bash
# 1. Create hybrid_provider.py (copy from above)
# 2. Test fallback behavior
# 3. Monitor logs for failures
```

### Week 4: Remove OpenAI Dependency (Optional)
```bash
# If satisfied with local LLM:
# 1. Remove OpenAI provider
# 2. Clean up config
# 3. Update documentation
```

---

## Summary Table

| Aspect | Ollama | LM Studio | OpenAI |
|--------|--------|-----------|--------|
| **Setup** | 5 min | 10 min | 1 min |
| **Cost** | Free | Free | $0.01-0.1/request |
| **Speed** | 1-5s | 1-5s | 0.5-2s |
| **Privacy** | 100% | 100% | Sent to cloud |
| **Customization** | High | Medium | None |
| **Reliability** | Depends on hardware | Depends on hardware | Very high |
| **Model Control** | Full | Full | Limited |
| **Recommended** | Production | Testing | High-volume |

---

## Next Steps

1. ✅ Install Ollama: https://ollama.ai
2. ✅ Pull a model: `ollama pull mistral`
3. ✅ Copy `ollama_provider.py` to your project
4. ✅ Update config and providers factory
5. ✅ Set `AI_PROVIDER=ollama` in `.env`
6. ✅ Test: `curl http://localhost:11434/api/tags`
7. ✅ Restart FastAPI and test chat endpoint

That's it! Your system now runs entirely locally without OpenAI.

---

## Questions?

- **Ollama docs**: https://github.com/ollama/ollama
- **Model library**: https://ollama.ai/library
- **Performance tips**: https://github.com/ollama/ollama/wiki/Performance
- **GPU setup**: https://github.com/ollama/ollama/issues
