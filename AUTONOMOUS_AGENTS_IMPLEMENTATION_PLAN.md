# Autonomous Agents Implementation Plan

**Objective:** Eliminate all static decision logic, hard-coded patterns, and magic values from the backend. Replace with LLM-driven routing, configuration-driven schemas, and dynamic decision-making.

**Status:** Planning Phase  
**Date:** April 3, 2026  

---

## Part 1: Complete Hard-Coded Values Audit

### 1.1 Static Pattern Matching & Routing

| Category | Current Location | Hard-Coded Value | Impact |
|----------|------------------|-----------------|---------|
| **Follow-up Detection** | `orchestrator.py:50-62` | `_FOLLOWUP_PATTERNS` regex | Determines if query uses code interpreter vs. standard analytics |
| **Intent Routing** | `orchestrator.py:85-93` | `_ANALYTICS_INTENTS`, `_TAGGING_INTENTS`, `_DOC_QA_INTENTS` | Maps intents to agent pipelines |
| **Intent Validation** | `intent_classifier.py:26-33` | `_VALID_INTENTS = ["analytics", "tag_suggestions", "article_recommendations", "unknown"]` | Restricts LLM to 4 predefined intents |
| **Intent Classification** | `intent_classifier.py:36-49` | `_INTENT_FEW_SHOT` (5 hand-crafted examples) | Few-shot examples for intent classifier |
| **Intent System Prompt** | `intent_classifier.py:50-68` | `_INTENT_SYSTEM_PROMPT` (hard-coded taxonomy) | Instructs LLM to classify into 4 categories |

---

### 1.2 Schema & Column Mappings (HARD-CODED DATA DICTIONARY)

| Category | Current Location | Values | Problem |
|----------|------------------|--------|---------|
| **Metric Aliases** | `analytics_db_function_tools.py:41-69` | 28 metrics like `"reach"→total_reach`, `"views"→video_views` | New metrics require code changes |
| **Dimension Columns** | `analytics_db_function_tools.py:73-87` | 8 dimensions: `platform, published_date, profile_id, content_type, media_type, labels, author_name, profile_name` | Adding new dimensions requires code change |
| **Column Mapper** | `column_mapper.py:14-63` | 80+ NLU term → DB column pairs (DATA_DICTIONARY) | Entire mapping baked into Python module |
| **Metric Whitelist** | `column_mapper.py:69-89` | Frozenset of 20+ metrics | Can't dynamically add new metrics without code redeploy |
| **Dimension Whitelist** | `column_mapper.py:90-98` | Frozenset of 8 dimensions | New dimensions require code change |
| **Numeric Defaults** | `ingestion_service.py:241-257` | 10 fields default to 0 when NULL | Schema knowledge baked in |
| **Key Metrics** | `ingestion_service.py:152-158` | 14 fingerprinting metrics for duplicate detection | Change in metrics requires code update |
| **Field Priority** | `response_agent.py:137-164`, `188-191` | `title` → `display_label` → `content` → `"Unknown"` | Display logic not driven by data |

---

### 1.3 System Prompts (BAKED-IN SCHEMA KNOWLEDGE)

| File | Lines | Content | Problem |
|------|-------|---------|---------|
| `intent_classifier.py` | 50-68 | `_INTENT_SYSTEM_PROMPT`: Hard-codes 4 intent categories with examples | Can't extend intent taxonomy without code change |
| `classify_agent.py` | 31-68 | system_prompt: References specific metrics (`views`, `reach`, `impressions`, `interactions`) | Prompt assumes specific DB schema |
| `analytics_agent.py` | 81-145 | `_SQL_GEN_SYSTEM_PROMPT`: 150+ lines listing all metrics, dimensions, rules | Entire schema baked into prompt; ~30 hard-coded metric names |
| `analytics_agent.py` | 481-554 | `_SQL_GEN_FEW_SHOT`: 6 hand-coded user→SQL examples | Few-shot examples not data-driven |
| `nlp/intent_parser.py` | 20-60 | `_PARSE_SYSTEM_PROMPT`: Whitelists metrics/dimensions in prompt text | Schema manifest in prompt, not config |
| `response_agent.py` | 65-71 | Platform URL templates (YouTube, TikTok, Instagram, Facebook) | URL format changes require code edit |
| `agent_provider_service.py` | 83-90 | Tag suggestions prompt: "Return ONLY valid JSON with keys: ..." | Output schema baked into prompt |

---

### 1.4 Magic Numbers & Thresholds

| File | Value | Purpose |
|------|-------|---------|
| `orchestrator.py:186` | `30.0` seconds | Tag suggestions timeout |
| `orchestrator.py:230` | `90.0` seconds | Article recommendations timeout |
| `orchestrator.py:135` | `>= 100` | Value guard threshold (skip validation for numbers < 100) |
| `code_interpreter_tool.py:43` | `30` seconds | Sandbox execution timeout |
| `dbquery_tool.py:36` | `200` rows | MAX_ROWS hard limit per query |
| `dbquery_tool.py:39` | `10_000` ms | PostgreSQL statement timeout |
| `analytics_db_function_tools.py:136,158,266` | `20`, `10` | Default/limit row counts |
| `analytics_db_function_tools.py:194` | `max(1, min(limit, 100))` | Limit bounds clamping |
| `analytics_agent.py:478` | `1` | MAX_SQL_RETRIES |
| `code_interpreter_agent.py:83-85` | temp=0.1, max_tokens=600, timeout=30 | LLM generation params |
| `providers/base.py:35,45` | 3, 1.0s, 60.0s | Retry config (max_retries, base_delay, max_delay) |
| `ingestion_service.py:984` | `60.0` seconds | HTTP client timeout |

---

### 1.5 Blocked Patterns & Security Lists

| File | Description | Values | Scope |
|------|-------------|--------|-------|
| `code_interpreter_tool.py:325-333` | Python import blocklist (fallback) | `import os`, `subprocess`, `open(`, `__import__`, `exec`, `eval` | Security (⚠️ KEEP AS-IS) |
| `dbquery_tool.py:43-46` | SQL keyword blocklist | `INSERT\|UPDATE\|DELETE\|TRUNCATE\|DROP\|ALTER\|CREATE\|EXEC\|GRANT\|REVOKE` | Security (⚠️ KEEP AS-IS) |
| `dbquery_tool.py:41` | Allowed tables | Frozenset: `{"documents"}` | Should be config-driven |

---

### 1.6 Business Logic Constants

| File | Value | Purpose |
|------|-------|---------|
| `services/provider_payload_validation.py:10` | `800` chars | Default max text length (sanitization) |
| `services/provider_payload_validation.py:36,85` | `600` chars | Error message max length |
| `services/provider_payload_validation.py:53` | `1200` chars | Description max length |
| `services/chat_service.py:126` | `100` | Max conversations returned in list |
| `services/ingestion_service.py:823` | `"max_results: 25"` | Gmail API default limit |

---

## Part 2: Implementation Roadmap

### Phase 1: Schema Registry & Configuration (Week 1-2)

**Goal:** Extract all hard-coded schemas, metrics, and mappings into YAML configuration.

**New Files to Create:**
1. **`backend/config/schema_registry.yaml`** — Master schema definition
   - Metrics (with aliases, types, aggregations allowed)
   - Dimensions (with types, values for enums)
   - Column whitelist for queries
   - Data types and constraints
   - Example:
     ```yaml
     schema:
       version: "1.0"
       table: "documents"
       metrics:
         video_views:
           aliases: ["views", "video views", "total views"]
           type: "integer"
           aggregations: ["sum", "avg", "max", "min", "count"]
           description: "Total YouTube video views"
         organic_reach:
           aliases: ["organic reach", "organic_reach"]
           type: "integer"
           aggregations: ["sum", "avg"]
       dimensions:
         platform:
           aliases: ["social platform", "channel"]
           type: "categorical"
           values: ["YouTube", "TikTok", "Instagram", "Facebook"]
         published_date:
           aliases: ["date posted", "publish date"]
           type: "date"
     ```

2. **`backend/config/intents.yaml`** — Intent taxonomy (dynamic, extensible)
   ```yaml
   intents:
     analytics:
       description: "Analyze metrics, top content, trends"
       aliases: ["query_metrics", "publishing_insights"]
       tools: ["run_analytics_query", "run_code_interpreter"]
     tagging:
       description: "Generate content tags"
       aliases: ["tag_suggestions", "tagging"]
       tools: ["generate_tags"]
     recommendation:
       description: "Recommend content"
       aliases: ["article_recommendations", "document_qa"]
       tools: ["get_recommendations"]
     general:
       description: "General conversation"
       aliases: []
       tools: []
   ```

3. **`backend/config/routing_rules.yaml`** — LLM-assisted routing rules
   ```yaml
   routing:
     decision_model: "gpt-4o-mini"  # LLM to use for routing
     confidence_threshold: 0.7
     fallback_intent: "general"
     retry_on_invalid_intent: true
     max_retries: 2
   ```

4. **`backend/config/agent_settings.yaml`** — Timeouts, limits, model params
   ```yaml
   agents:
     analytics:
       lm_timeout_seconds: 45
       sql_max_retries: 2
       row_limit: 200
       sandbox_timeout: 30
     tagging:
       lm_timeout_seconds: 30
       max_tags: 10
     recommendation:
       lm_timeout_seconds: 90
       max_results: 20
   
   code_interpreter:
     timeout_seconds: 30
     max_code_lines: 30
     allowed_imports: ["pandas", "matplotlib.pyplot", "json", "math"]
   
   database:
     statement_timeout_ms: 10000
     max_rows_per_query: 200
   ```

**Code Changes Required:**

- **`backend/src/app/config.py`** (new)
  ```python
  import yaml
  from pathlib import Path
  
  class SchemaRegistry:
      def __init__(self, yaml_path: str):
          with open(yaml_path) as f:
              self.data = yaml.safe_load(f)
      
      @property
      def metrics(self) -> dict:
          return self.data.get("schema", {}).get("metrics", {})
      
      @property
      def dimensions(self) -> dict:
          return self.data.get("schema", {}).get("dimensions", {})
      
      def get_metric_aliases(self, metric_name: str) -> list[str]:
          """Return all aliases for a metric (including the metric name itself)"""
          m = self.metrics.get(metric_name, {})
          return [metric_name] + m.get("aliases", [])
      
      def resolve_metric(self, user_term: str) -> str | None:
          """Find canonical metric name from user-facing term"""
          for metric, config in self.metrics.items():
              if user_term.lower() in (m.lower() for m in self.get_metric_aliases(metric)):
                  return metric
          return None
  
  class IntentRegistry:
      def __init__(self, yaml_path: str):
          with open(yaml_path) as f:
              self.data = yaml.safe_load(f)
      
      @property
      def valid_intents(self) -> list[str]:
          return list(self.data.get("intents", {}).keys())
      
      @property
      def intent_taxonomy(self) -> dict:
          return self.data.get("intents", {})
  
  # Load at startup
  SCHEMA_REGISTRY = SchemaRegistry("config/schema_registry.yaml")
  INTENT_REGISTRY = IntentRegistry("config/intents.yaml")
  ```

- **`backend/src/app/nlp/column_mapper.py`** (refactor)
  - Remove hard-coded `DATA_DICTIONARY`, `WHITELISTED_METRICS`, `WHITELISTED_DIMENSIONS`
  - Inject `SCHEMA_REGISTRY` and derive dynamically:
    ```python
    # OLD:
    DATA_DICTIONARY = { "reach": "total_reach", ... }  # 80+ entries
    
    # NEW:
    def get_metric_mapping() -> dict:
        """Build alias → canonical name mapping from schema registry"""
        return {
            alias: canonical
            for canonical, config in SCHEMA_REGISTRY.metrics.items()
            for alias in [canonical] + config.get("aliases", [])
        }
    
    def get_dimension_names() -> set[str]:
        """Get all valid dimensions from schema"""
        return set(SCHEMA_REGISTRY.dimensions.keys())
    ```

---

### Phase 2: LLM-Driven Intent Classification (Week 2-3)

**Goal:** Replace static intent list with LLM decision on intent + confidence + reasoning.

**Changes:**

- **`backend/src/app/utilities/intent_classifier.py`** (refactor)
  - Remove `_VALID_INTENTS`, `_INTENT_FEW_SHOT`, `_INTENT_SYSTEM_PROMPT` (hard-coded)
  - Make system prompt dynamic from `INTENT_REGISTRY.intent_taxonomy`
  - Get few-shot examples from YAML (or generate them dynamically)
  - LLM response now includes `{intent, confidence, reasoning}`
  - If confidence < threshold: use fallback or ask for clarification

  ```python
  async def classify_intent(message: str) -> dict:
      """Classify user intent using LLM + dynamic intent registry"""
      
      # Build system prompt dynamically from registry
      intent_descriptions = "\n".join([
          f"- {name}: {config['description']}"
          for name, config in INTENT_REGISTRY.intent_taxonomy.items()
      ])
      
      system_prompt = f"""You are an intent classifier for an analytics platform.
  Classify the user's message into one of these intents:
  
  {intent_descriptions}
  
  Respond with JSON: {{"intent": "<intent>", "confidence": 0.0-1.0, "reasoning": "..."}}
  """
      
      # Get few-shot from config or dynamically
      few_shot = load_few_shot_from_config()
      
      response = await llm_call(
          model="gpt-4o-mini",
          system=system_prompt,
          messages=[*few_shot, {"role": "user", "content": message}],
          response_format="json"
      )
      
      result = json.loads(response)
      
      # Validate against registry
      if result["intent"] not in INTENT_REGISTRY.valid_intents:
          result["intent"] = INTENT_REGISTRY.fallback_intent
          result["confidence"] = 0.0
      
      return result
  ```

---

### Phase 3: Autonomous Router (LLM-Based Agent Routing) (Week 3-4)

**Goal:** Replace `_is_followup_or_complex()` regex with LLM reasoning about conversation context.

**New File:**
- **`backend/src/app/agents/autonomous_router.py`**

```python
async def route_query(
    message: str,
    intent: str,
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Route query to appropriate agent using LLM reasoning + conversation context.
    
    Returns: {
        "target_agent": "analytics" | "code_interpreter" | "tagging" | "recommendation",
        "confidence": 0.0-1.0,
        "reasoning": "...",
        "requires_context": true | false,
        "conversation_stage": "initial" | "followup" | "deep_analysis",
    }
    """
    
    # Build conversation context summary
    context_summary = summarize_conversation(conversation_history)
    
    system_prompt = """You are a query router. Based on the user's intent, current message, 
and conversation history, decide which agent should handle this query.

Routing options:
- "analytics": Run SQL analytics queries
- "code_interpreter": Run Python code for advanced analysis
- "tagging": Generate content tags
- "recommendation": Recommend content

Consider:
1. Is this a follow-up to a previous query? (e.g., "break them down by platform")
2. Does it require visualization? (e.g., "show chart")
3. Is it a complex multi-step analysis? (e.g., "compare then filter")
4. Does the user reference prior results? (e.g., "those", "that data")

Respond with JSON: {
    "target_agent": "...",
    "confidence": 0.0-1.0,
    "reasoning": "...",
    "requires_context": true|false,
    "conversation_stage": "initial|followup|deep_analysis"
}"""
    
    response = await llm_call(
        model="gpt-4o-mini",
        system=system_prompt,
        messages=[
            {"role": "system", "content": f"Conversation context: {context_summary}"},
            {"role": "user", "content": f"Intent: {intent}\nMessage: {message}"}
        ],
        response_format="json"
    )
    
    routing_decision = json.loads(response)
    
    # Validate target_agent
    valid_agents = list(INTENT_REGISTRY.intent_taxonomy[intent]["tools"])
    if routing_decision["target_agent"] not in valid_agents:
        routing_decision["target_agent"] = valid_agents[0]
        routing_decision["confidence"] = 0.5
    
    return routing_decision
```

**Integration in `orchestrator.py`:**
```python
# BEFORE (static):
if _is_followup_or_complex(message, conversation_history):
    return await run_code_interpreter(...)
else:
    return await run_sql_analytics_pipeline(...)

# AFTER (LLM-driven):
routing = await route_query(message, intent, conversation_history)
if routing["target_agent"] == "code_interpreter":
    return await run_code_interpreter(...)
elif routing["target_agent"] == "analytics":
    return await run_sql_analytics_pipeline(...)
```

---

### Phase 4: Dynamic System Prompts from Schema (Week 4-5)

**Goal:** Generate SQL-gen and code-gen prompts dynamically from schema registry, not hard-coded.

**Changes:**

- **`backend/src/app/agents/analytics_agent.py`** (refactor)
  - Remove `_SQL_GEN_SYSTEM_PROMPT` (150+ line hard-coded prompt)
  - Generate dynamically:
    ```python
    def build_sql_gen_prompt() -> str:
        """Generate SQL generation prompt from live schema"""
        
        available_metrics = "\n".join([
            f"- {m}: {config.get('description', '')}"
            for m, config in SCHEMA_REGISTRY.metrics.items()
        ])
        
        available_dimensions = "\n".join([
            f"- {d}: {config.get('description', '')}"
            for d, config in SCHEMA_REGISTRY.dimensions.items()
        ])
        
        return f"""You are an expert PostgreSQL query generator for social media analytics.
    
Available metrics (can aggregate with sum, avg, max, min, count):
{available_metrics}

Available dimensions (can GROUP BY):
{available_dimensions}

Table schema:
<dynamic from SCHEMA_REGISTRY>

Rules:
1. Use ONLY metrics and dimensions from above whitelist
2. Always use parameterized queries ($1, $2, etc.)
3. Return valid PostgreSQL
4. Order results by metric DESC
5. Limit results to 100 rows max

Generate SQL for: {{user_query}}
        """
    ```

- **`backend/src/app/agents/code_interpreter_agent.py`** (refactor)
  - Dynamic prompt for code generation based on available imports and constraints

- **`backend/src/app/nlp/intent_parser.py`** (refactor)
  - Generate parse system prompt with live metric/dimension list from registry

---

### Phase 5: Configuration-Driven Magic Numbers (Week 5)

**Goal:** Move all timeouts, limits, and thresholds to environment/config.

**Changes:**

- **`.env.example`** and **`backend/src/app/config.py`** (extend settings)
  ```python
  class Settings(BaseSettings):
      # Agent timeouts (seconds)
      AGENT_ANALYTICS_TIMEOUT: int = 45
      AGENT_TAGGING_TIMEOUT: int = 30
      AGENT_RECOMMENDATION_TIMEOUT: int = 90
      
      # Code interpreter
      CODE_INTERPRETER_TIMEOUT: int = 30
      CODE_INTERPRETER_MAX_LINES: int = 30
      
      # Database
      DB_STATEMENT_TIMEOUT_MS: int = 10_000
      DB_MAX_ROWS_PER_QUERY: int = 200
      
      # Query limits
      DEFAULT_QUERY_LIMIT: int = 20
      MAX_QUERY_LIMIT: int = 100
      
      # Value guard
      VALUE_GUARD_THRESHOLD: int = 100
      
      # Retry policy
      LLM_MAX_RETRIES: int = 2
      LLM_RETRY_BASE_DELAY: float = 1.0
      LLM_RETRY_MAX_DELAY: float = 60.0
      
      # Intent classification
      INTENT_CONFIDENCE_THRESHOLD: float = 0.7
  ```

- Update all Agent files to read from `settings` instead of hard-coded values

---

### Phase 6: Intelligent Few-Shot Example Generation (Week 6)

**Goal:** Generate few-shot examples dynamically from schema + conversation patterns.

**New File:**
- **`backend/src/app/nlp/few_shot_generator.py`**

```python
async def generate_few_shots_for_intent(intent: str, schema: dict) -> list[dict]:
    """
    Generate few-shot examples dynamically using LLM + schema.
    Falls back to stored examples if LLM fails.
    """
    
    # Prompt LLM to generate few-shot examples based on current schema
    prompt = f"""You are an example generator. Create 3 realistic user queries 
and corresponding expected outputs for the '{intent}' intent.

Available metrics: {', '.join(schema['metrics'].keys())}
Available dimensions: {', '.join(schema['dimensions'].keys())}

Generate examples in this format:
{{"role": "user", "content": "..."}}
{{"role": "assistant", "content": "..."}}

Output ONLY valid JSON list of 6 objects (3 pairs).
    """
    
    try:
        response = await llm_call(..., response_format="json")
        return json.loads(response)
    except:
        # Fallback to stored examples
        return load_stored_few_shots(intent)
```

---

### Phase 7: Database-Driven Schema Discovery (Optional, Week 7-8)

**Goal:** Inspect live database schema at startup, validate against YAML, warn on drift.

**New File:**
- **`backend/src/app/services/schema_validator.py`**

```python
async def validate_schema_drift():
    """Compare stored schema registry with actual DB schema"""
    
    db_columns = await inspect_documents_table_columns()
    documented_columns = set(SCHEMA_REGISTRY.metrics.keys()) | set(SCHEMA_REGISTRY.dimensions.keys())
    
    undocumented = db_columns - documented_columns
    if undocumented:
        logger.warning(f"Undocumented DB columns found: {undocumented}. Update config/schema_registry.yaml")
    
    missing = documented_columns - db_columns
    if missing:
        logger.warning(f"Columns in schema_registry.yaml not found in DB: {missing}")
```

---

## Part 3: Migration Plan

### Sprint Timeline

| Week | Phase | Key Deliverables | Testing |
|------|-------|------------------|---------|
| 1-2 | Config & Registry | `schema_registry.yaml`, `intents.yaml`, agent_settings.yaml`, `SchemaRegistry` class | Unit tests for YAML loading, metrics resolution |
| 2-3 | Dynamic Intent Classification | Updated `intent_classifier.py`, dynamic system prompts | Integration tests: classify 10 different queries |
| 3-4 | Autonomous Router | `autonomous_router.py`, updated orchestrator routing | E2E tests: follow-up detection, routing decisions |
| 4-5 | Dynamic Prompts | Refactored `analytics_agent.py`, `code_interpreter_agent.py` | Verify SQL generation accuracy unchanged |
| 5 | Config-Driven Magic Numbers | `.env` settings, config injection | Smoke tests: verify all agents still work |
| 6 | Few-Shot Generation | `few_shot_generator.py` | A/B test: dynamic vs. static few-shots |
| 7-8 | Schema Validation | `schema_validator.py` | DB introspection tests |

---

## Part 4: File Modification Overview

### Files to Create
- `backend/config/schema_registry.yaml`
- `backend/config/intents.yaml`
- `backend/config/routing_rules.yaml`
- `backend/config/agent_settings.yaml`
- `backend/src/app/config/schema_registry.py` (Python class)
- `backend/src/app/config/intent_registry.py`
- `backend/src/app/agents/autonomous_router.py`
- `backend/src/app/nlp/few_shot_generator.py`
- `backend/src/app/services/schema_validator.py`

### Files to Refactor
- `backend/src/app/agents/orchestrator.py` — Replace static routing with LLM-driven routing
- `backend/src/app/utilities/intent_classifier.py` — Dynamic prompts from registry
- `backend/src/app/agents/analytics_agent.py` — Eliminate `_SQL_GEN_SYSTEM_PROMPT`, generate dynamically
- `backend/src/app/agents/code_interpreter_agent.py` — Dynamic code gen prompt
- `backend/src/app/nlp/column_mapper.py` — Load from schema registry instead of hard-coded
- `backend/src/app/nlp/intent_parser.py` — Dynamic prompt from registry
- `backend/src/app/config.py` — Add all settings/environment vars
- `.env.example` — New config vars

### Files to Keep As-Is
- `backend/src/app/tools/code_interpreter_tool.py` — Security blocklist (needed for sandbox)
- `backend/src/app/tools/dbquery_tool.py` — SQL keyword blocklist (security)

---

## Part 5: Success Criteria

✅ **Fully Autonomous Agents:**
- No hard-coded intent lists — intent taxonomy in YAML, extensible
- No regex-based follow-up detection — LLM reasoning with conversation context
- No static column mappings — derived from live schema registry
- No hard-coded system prompts — generated dynamically from schema

✅ **Configuration-Driven:**
- All magic numbers in `.env` or YAML
- All timeouts, limits, thresholds externalized
- Adding new metrics/dimensions: YAML change only (no code redeploy)

✅ **Backward Compatible:**
- Existing API contracts unchanged
- All existing tests pass
- Query results identical to before (deterministic LLM seed)

✅ **Observable & Debuggable:**
- Routing decisions logged with reasoning
- Schema validation warnings on drift
- LLM prompts logged for inspection

---

