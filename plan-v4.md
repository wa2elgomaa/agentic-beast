# Plan: Comprehensive Agent & Asset Refactoring

## TL;DR
Refactor all agents to use Strands `messages=` seeding (drop `augmented_message` text injection), consolidate history utilities into `conversation_utils.py`, and standardise the chart/asset response as a typed `MessageAsset` list with `source` = full data URI. 8 phases; optimal order: 1→2→3→[4+5+6 parallel]→7→8.

---

## Confirmed Decisions
- Drop `augmented_message`; all agents seeded via `messages=`
- Keep `chart_b64` in Postgres as-is (no Redis for persistent blobs)
- `source` = full data URI `data:image/png;base64,...`

---

## Phase 1 — New `app/utils/conversation_utils.py`

New file at `backend/src/app/utils/conversation_utils.py`:

1. `history_to_strands_messages(history, max_turns=20) -> list[dict]`
   - Takes last `max_turns` from `conversation_history`
   - Converts `{role, content}` → `{role, content: [{"text": content}]}`
   - Migrated from `analytics_agent.py`:`_history_to_messages()`

2. `format_history_snippet(history, max_turns=4) -> str`
   - Returns a plain-text block of last `max_turns` turns
   - Migrated from `classify_agent.py` inline logic (role + content[:200])
   - Used ONLY by classify agent

Verify: `get_errors` on new file

---

## Phase 2 — `MessageAsset` schema + schema updates

File: `backend/src/app/schemas/chat.py`

1. Add `MessageAsset` at top:
   - `source: str` (full data URI)
   - `caption: str = ""`
   - `mime: str = "image/png"`
   - `asset_type: str = "chart"`

2. Update `OrchestratorAgentSchema`:
   - Remove `chart_b64: str = ""` and `visualization_caption: str = ""`
   - Add `assets: list[MessageAsset] = []`

3. Update `ChatMessageMetadata`:
   - Keep `chart_b64` and `visualization_caption` (backward compat for old Postgres rows)
   - Add `assets: list[MessageAsset] = []`

4. Update `AnalyticsAgentSchema` (wherever it lives):
   - Same: add `assets: list[MessageAsset] = []`, keep legacy fields

Verify: `get_errors` on schemas files

---

## Phase 3 — `chat_agent.py`: add `messages=` support

File: `backend/src/app/agents/v1/chat_agent.py`

- Change `build_chat_agent()` → `build_chat_agent(messages=None)`
- Pass `messages=cast(Any, messages or [])` to `Agent(...)`

Verify: `get_errors` on file

---

## Phase 4 — `orchestrator_agent.py`: core refactor (most impactful)

File: `backend/src/app/agents/v1/orchestrator_agent.py`

1. Remove import `_history_to_messages` from analytics_agent
2. Import `history_to_strands_messages` from `app.utils.conversation_utils`
3. Delete `_format_history_for_prompt()` method
4. `_build_agent(initial_messages)`:
   - Pass to BOTH: `build_analytics_agent(messages=initial_messages or [])` and `build_chat_agent(messages=initial_messages or [])`
   - Seed orchestrator Agent: `Agent(..., messages=cast(Any, initial_messages or []))`
5. `execute(context)`:
   - Wrap in `asyncio.to_thread` (currently missing)
   - `_run_sync()`: call `agent(message)` (plain; no augmented_message)
   - Build `assets = [MessageAsset(source=f"data:...", caption=...)]` if chart
   - Return `OrchestratorAgentSchema(response_text=..., assets=assets)`
6. `execute_stream(context)`:
   - Remove `augmented_message` construction
   - `_run_agent()` calls `agent(message)` (plain)
   - `image` WS event stays as-is: `{b64, mime, caption}` (no breaking WS protocol change)
   - `complete` event: include `assets: [a.model_dump() for a in assets]` + keep `chart_b64`/`visualization_caption` aliases during transition

Verify: `get_errors` on file

---

## Phase 5 — `analytics_agent.py`: simplify history ownership

File: `backend/src/app/agents/v1/analytics_agent.py`

Pre-check: grep `_history_to_messages` importers before deleting

1. Delete `_history_to_messages()` function (moved to util)
2. `AnalyticsAgent.execute(context)`:
   - Remove `is_followup` context reading and `initial_messages` computation (orchestrator owns this)
   - Keep `_run_sync()` with `set_conversation_id`, `clear_chart_state`, `pop_latest_chart` (needed for direct calls / tests)
   - Return `AnalyticsAgentSchema(..., assets=[MessageAsset(...)] if chart_b64 else [])`

Verify: `get_errors` on file

---

## Phase 6 — `classify_agent.py`: use shared utility

File: `backend/src/app/agents/v1/classify_agent.py`

1. Import `format_history_snippet` from `app.utils.conversation_utils`
2. Replace inline `history[-4:]` loop with `format_history_snippet(history, max_turns=4)`

Verify: `get_errors` on file

---

## Phase 7 — `chat_service.py`: handle `assets` list

File: `backend/src/app/services/v1/chat_service.py`

1. `handle_user_message_stream()`:
   - Read `result.assets` from `OrchestratorAgentSchema`
   - `operation_data = {"assets": [a.model_dump() for a in result.assets]}`
   - Also write `chart_b64` / `visualization_caption` into `operation_data` for backward compat
   - `complete` WS event: include `assets: [a.model_dump() for a in result.assets]`

2. `format_message_response()`:
   - Read `op.get("assets", [])` → build `list[MessageAsset]`
   - Backward compat: if assets empty but `op.get("chart_b64")` present → synthesize `MessageAsset(source=f"data:image/png;base64,{chart_b64}", caption=...)`
   - Return `assets` in `ChatMessageMetadata`

Verify: `get_errors` on file

---

## Phase 8 — Frontend: types + components

Files to update:
- `frontend/types/index.ts`:
  - Add `MessageAsset` interface: `{ source: string; caption: string; mime: string; asset_type: string }`
  - Add `assets?: MessageAsset[]` to `ChatMessageMetadata`
  - Add `assets?: MessageAsset[]` to WS `complete` event data type
- `frontend/hooks/useChatStream.ts`:
  - `onImage` callback stays unchanged for WS `image` event
  - Parse `data.assets` from `complete` event
- `frontend/components/ChatArea.tsx`:
  - `onImage` handler: build `MessageAsset` from `(b64, mime, caption)` → `{ source: \`data:${mime};base64,${b64}\`, ... }`; store in `metadata: { assets: [asset] }`
  - `onComplete` handler: read `data.assets` if present; store in metadata
- `frontend/components/ChatMessage.tsx`:
  - Replace `chart_b64` render block with `assets` loop: `{ metadata?.assets?.map(a => <img src={a.source} />) }`
  - Keep backward-compat `chart_b64` render for old messages

Verify: `cd frontend && npx tsc --noEmit`

---

## Relevant Files

- `backend/src/app/utils/conversation_utils.py` — NEW (Phases 1, 6)
- `backend/src/app/schemas/chat.py` — MessageAsset, schema updates (Phase 2)
- `backend/src/app/agents/v1/chat_agent.py` — messages= (Phase 3)
- `backend/src/app/agents/v1/orchestrator_agent.py` — core refactor (Phase 4)
- `backend/src/app/agents/v1/analytics_agent.py` — remove _history_to_messages (Phase 5)
- `backend/src/app/agents/v1/classify_agent.py` — shared util (Phase 6)
- `backend/src/app/services/v1/chat_service.py` — assets handling (Phase 7)
- `frontend/types/index.ts`, `frontend/hooks/useChatStream.ts`, `frontend/components/ChatArea.tsx`, `frontend/components/ChatMessage.tsx` — (Phase 8)

Dependencies: 1→[4,5,6] | 2→[4,5,7] | 3→4 | 4→7 | 7→8

---

## Verification

1. `get_errors` on each file after editing
2. `cd backend && ruff check src/app/utils/conversation_utils.py src/app/agents/v1/*.py src/app/schemas/chat.py src/app/services/v1/chat_service.py`
3. `cd frontend && npx tsc --noEmit`
4. Send analytics query with chart → confirm `image` WS event fires + `complete.assets[0].source` is valid data URI + chart renders in UI
5. Send non-chart query → confirm empty/absent `assets`

---

## Scope Boundaries

Included: all 8 phases, backward compat for old DB rows, both streaming + non-streaming paths
Excluded: Redis permanent message storage, audio agent, `ConversationAssetService` changes, `python_executor_tool.py` changes
