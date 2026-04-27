## Plan: Multimodal Agentic Backend Refactor

**Goal:**
Implement a clean, modular agentic backend with unified REST and WebSocket entrypoints, provider abstraction, and explicit agent/tool separation. Default all LLM provider configs to `litert_provider` unless a blocker is found.

---

### 1. High-Level Flow Diagram

```
[Client]
   |
   v
[API Gateway (/chat, /chat/ws) + Auth Middleware]
   |
   v
[Orchestrator Agent]
   |--(audio)--> [Audio Transcript Tool] --(transcript)--> [Classify Agent]
   |--(text)-----------------------------> [Classify Agent]
   |
   v 
[Intent Routing]
   |-- analytics --> [Analytics Agent] --> [SQL Interpreter Agent] --> [DBQuery Tool] --> [Response Tool]
   |-- general   --> [Chat Agent] --> [Response Tool]
   |-- ...       --> [Other Specialist Agents] --> [Response Tool]
   |
   v
[Response Tool] (refine, TTS if needed)
   |
   v
[Client]
```

---

### 2. Implementation Steps

#### A. Project Structure
- New code under `v1` subfolders:
  - `services/v1/`, `agents/v1/`, `tools/v1/`, `providers/v1/`, `utils/`
- Wipe legacy files (keep backup in `backend-bk/`).

#### B. Providers
- Implement `litert_provider.py`, `ollama_provider.py`, `openai_provider.py` in `providers/v1/`.
- Provider selection via config/env (default: `litert`).
- All agent/tool configs reference provider/model via env and config files.

#### C. Entry Points
- REST: `/chat` (POST)
- WebSocket: `/chat/ws`
- Both use shared orchestrator logic.
- Add APIKey-based auth middleware for both.

#### D. Orchestrator Agent
- File: `agents/v1/orchestrator_agent.py`
- Receives all requests, routes:
  - Audio → `audio_transcript_tool` → transcript → `classify_agent`
  - Text → `classify_agent`
- Intent-based routing to specialist agents.

#### E. Audio Transcript Tool
- File: `tools/v1/audio_transcript_tool.py`
- Use `litert_lm.Engine` (as in `polar/src/server.py`) for transcription and realtime processing.
- Config: `AUDIO_MODEL`, `AUDIO_LLM_PROVIDER` (from `tools_config`).

#### F. Classify Agent
- File: `agents/v1/classify_agent.py`
- Classifies intents (analytics, general, etc.), intents configurable.
- Config: `CLASSIFY_MODEL`, `CLASSIFY_LLM_PROVIDER`.

#### G. Chat Agent
- File: `agents/v1/chat_agent.py`
- Handles general chat using configured model/provider.
- Config: `CHAT_MODEL`, `CHAT_LLM_PROVIDER`.

#### H. Analytics Agent
- File: `agents/v1/analytics_agent.py`
- Pipeline: user query → `sql_interpreter_agent` → `dbquery_tool` → `response_tool`.
- Config: `ANALYTICS_MODEL`, `ANALYTICS_LLM_PROVIDER`.

#### I. SQL Interpreter Agent
- File: `agents/v1/sql_interpreter_agent.py`
- Converts NL → SQL using schema-aware prompts.
- Config: `SQL_MODEL`, `SQL_LLM_PROVIDER`.

#### J. DBQuery Tool
- File: `tools/v1/dbquery_tool.py`
- Executes SQL using DB session and returns structured data.

#### K. Response Tool
- File: `tools/v1/response_tool.py`
- Refines responses; if flow started with audio, produce a short TTS-ready summary and TTS metadata.
- Switch-case behavior based on response type (analytics vs general chat).

#### L. Utilities
- Reusable helpers go in `utils/`.
- Avoid redundant code; centralize common parsing, validation, and streaming helpers.

#### M. Config & ENV
- Clean `.env` and `config_settings.py`.
- Group agent/tool configs and surface only required ENV variables.
- Example envs: `AUDIO_MODEL`, `AUDIO_LLM_PROVIDER`, `CHAT_MODEL`, `CHAT_LLM_PROVIDER`, `SQL_MODEL`, `SQL_LLM_PROVIDER`, `MAIN_MODEL`, `CLASSIFY_MODEL`.

#### N. Testing & Validation
- Unit tests for provider adapters and agents.
- In-process E2E for `/chat` and `/chat/ws` (text & audio) using auth override.
- Validate response shapes (JSON objects, not raw strings) and TTS streaming contract.

---

### 3. Specific Refactor Notes & Migration Steps
- Replace `MediaProcessingService.transcribe_audio` (currently using OpenAI) with `audio_transcript_tool` that uses `litert_lm.Engine` and consistent engine lifecycle management (see `polar/src/server.py`).
- Create `tools_config` and `chat_config` in `config/` to declare per-tool model and provider envs; these drive provider selection.
- `orchestrator_agent.py` becomes the single routing entry for `/chat` and `/chat/ws`.
- `classify_agent.py` is responsible solely for intent detection; make intents configurable and pluggable.
- `response_tool.py` should transform structured analytics results into human-readable summaries and optionally TTS chunks (via provider TTS) when the request originated from audio.
- Use `litert_provider` as the default provider for all agents; fallback to `openai_provider` only if a hard blocker is found.

---

### 4. Auth & Operational Concerns
- Implement APIKey middleware for both REST and WS. Token in header `Authorization: Bearer <token>` or `x-api-key`.
- Enforce conversation ownership: if `conversation_id` provided, validate and error if not found.
- Keep session manager single-instance semantics for `litert` runtime; design hooks to extend to distributed later.
- Design TTS streaming metadata (stream_id, sample_rate) and ensure frontend `pauseListening` flag receives `audio_start`/`audio_end` events.

---

### 5. Rollout Plan
1. Scaffold directories and config files; add provider adapters.
2. Implement orchestrator and agent stubs with unit tests.
3. Integrate `audio_transcript_tool` using `litert_lm.Engine` (extract minimal code from `polar/src/server.py`).
4. Implement classify_agent routing and chat_agent fallback.
5. Implement analytics pipeline and response tooling.
6. Add APIKey auth middleware and conversation guards.
7. Replace old endpoints / cleanup legacy files (move to `backend-bk/`).
8. Run test suite and fix any response-shape or integration issues.

---

### 6. Deliverables
- New `v1` folder structure with providers, agents, tools, utils.
- Cleaned `.env` and grouped Pydantic config.
- In-process E2E tests for `/chat` and `/chat/ws`.
- Documentation: `README.md` describing agent configs and deployment.

---

If you want, I can now:
1. Scaffold the folder structure and create initial files (providers, agents, tools, utils) with TODOs and minimal implementations, or
2. Start by replacing `MediaProcessingService.transcribe_audio` to use the `litert_lm.Engine` (create `tools/v1/audio_transcript_tool.py`), or
3. Create the `tools_config` and `chat_config` files and update `config_settings.py` grouping.

Which task should I take first?