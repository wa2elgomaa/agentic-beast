# Chat E2E Testing - Quick Start Guide

## Overview

You now have a **comprehensive end-to-end testing suite** for the chat orchestrator with your 160k records. This guide shows you how to run tests and what to expect.

---

## Quick Start

### Option 1: Run All Tests (Python)

```bash
cd /Users/wgomaa/Work/TNN/AI\ Project/The\ Beast/agentic-beast

python test_chat_e2e.py
```

**Expected output:**
```
================================================================================
CHAT ORCHESTRATOR E2E TEST SUITE
================================================================================
API Base: http://localhost:8000/api/v1
Timestamp: 2024-04-10T15:30:45.123456

[PHASE 1] Intent Classification & Routing
----
  ✓ [API] What were the top performing... (1.23s)
  ✓ [API] Suggest tags for this article... (0.98s)

================================================================================
TEST RESULTS SUMMARY
================================================================================

Phase 1: Intent Classification & Routing (3/3 passed)
  ✓ PASS | Analytics Intent Detection (1.23s) | Operation: analytics
  ✓ PASS | Tagging Intent Detection (0.98s) | Operation: tagging
  ✓ PASS | Unknown Intent Fallback (1.45s) | Graceful fallback to unknown intent

Phase 2: Analytics SQL Pipeline (3/3 passed)
  ✓ PASS | Simple Metric Query (2.34s) | Generated SQL, 1 results
  ✓ PASS | Top Content Query (1.87s) | 5 results with insight summary
  ✓ PASS | Parameterized SQL (2.12s) | Query parameterized, 42 results

...

================================================================================
OVERALL: 11/11 tests passed
================================================================================
```

---

### Option 2: Test Individual Queries (cURL)

```bash
# Test 1: Simple analytics query
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How many total documents do we have?"
  }' | jq '.message | {operation: .metadata.operation, result_count: (.content.result_data | length)}'

# Expected output:
# {
#   "operation": "analytics",
#   "result_count": 1
# }
```

---

### Option 3: Test with Conversation Context

```bash
# Create conversation and send first message
CONV=$(curl -s -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is our top performing post this month?"
  }' | jq -r '.conversation_id')

echo "Conversation: $CONV"

# Send follow-up in same conversation
curl -s -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"How much engagement did it get?\",
    \"conversation_id\": \"$CONV\"
  }" | jq '.message.content.insight_summary'

# Check conversation history
curl -s http://localhost:8000/api/v1/chat/conversations/$CONV/messages | jq '.messages | length'
```

---

## Architecture Refresh

### The Complete Flow

```
1. User sends message to /chat endpoint
                    ↓
2. ChatService.handle_user_message()
   - Creates/retrieves conversation
   - Stores user message
   - Fetches prior context (up to 10 messages)
                    ↓
3. AgentOrchestrator.execute()
   - Intent Classification
     └─ IntentClassifier.classify(message, context)
        └─ LLM returns: {intent, confidence, reasoning}
                       ↓
   - Route to specialist agent
     ├─ If analytics → SQL pipeline OR code interpreter
     ├─ If tagging → Direct tag suggestion tool
     ├─ If recommendations → Direct recommendation tool
     └─ Else → Strands agent with tools
                       ↓
4. Analytics Pipeline (if applicable)
   - generate_analytics_sql() → LLM generates SELECT query
   - validate_sql() → Check: whitelist tables, readonly, no injection
   - execute_safe_sql() → Parameterized execution, 10s timeout
   - build_analytics_response() → Format results + narrative
                       ↓
5. Value-Guard Validation
   - Ensure no hallucinated metrics
   - Only show values from actual results
   - Generate grounded insight summary
                       ↓
6. Store operation_data
   - Save SQL query executed
   - Save results received
   - Save metrics and operation type
                       ↓
7. Return ChatResponse
   - Message with content
   - Metadata with operation, SQL, agents involved
   - Conversation ID for follow-ups
```

---

## Test Scenarios Explained

### Phase 1: Intent Classification
**Tests**: Can the system correctly identify what the user is asking?

| Test | Query | Expected Intent | Expected Result |
|------|-------|-----------------|-----------------|
| Analytics Intent | "What were the top performing posts last week?" | `analytics` | Route to SQL pipeline |
| Tagging Intent | "Suggest tags for this article" | `tag_suggestions` | Call tagging agent |
| Unknown Intent | "Tell me a joke about data" | `unknown` | Graceful handling |

### Phase 2: Analytics SQL Pipeline
**Tests**: Can the system convert questions to SQL and execute safely?

| Test | Query | Expected SQL | Expected Output |
|------|-------|--------------|-----------------|
| Simple Metric | "How many total documents?" | `SELECT COUNT(*) FROM documents` | Single aggregation |
| Top-N Query | "Top 5 posts by views" | `SELECT ... ORDER BY views DESC LIMIT 5` | 5 result items |
| Safe Execution | "Posts with > 1000 views" | Parameterized (uses bind params) | Safe, no injection possible |

### Phase 3: Conversation Context
**Tests**: Can the system remember previous queries and use them for follow-ups?

**Scenario:**
```
User: "What's our top post this month?"
  → AI: "Post X has 5,000 views"
  → Stores: SQL query + results in conversation

User: "How much engagement did it get?"
  → AI: Injects prior context, knows we're talking about Post X
  → Returns: Specific engagement metrics for Post X
  → Stores: Both messages in conversation history
```

### Phase 4: Value-Guard Validation
**Tests**: Does the system prevent hallucinating numbers?

**Example Protection:**
```
Query: "What metric data do we have for posts?"
Results: {views: 5000, comments: 250}

❌ BAD: Insight says "The post got 5,000 views, 250 comments, and 500 shares"
✓ GOOD: Insight says "The post got 5,000 views and 250 comments"
         (only mentions what's in actual results)
```

### Phase 5: Response Format
**Tests**: Are all responses properly structured with required fields?

**Expected Response Structure:**
```json
{
  "conversation_id": "uuid",
  "message": {
    "id": "uuid",
    "role": "assistant",
    "content": {
      "query_type": "string",
      "result_data": [
        {
          "content_id": "string or null",
          "display_label": "string (post title)",
          "metric_name": "string (views/comments/etc)",
          "metric_value": 5000,
          "view_url": "string"
        }
      ],
      "insight_summary": "string (narrative)",
      "verification": "string (source)"
    },
    "metadata": {
      "operation": "analytics",
      "generated_sql": "SELECT ...",
      "agents_involved": ["orchestrator", "analytics"],
      "chart_b64": null,
      "code_output": null
    },
    "created_at": "2024-04-10T15:30:45Z"
  },
  "status": "success"
}
```

---

## Sample Test Queries (Copy-Paste Ready)

### Aggregation Queries
```bash
# Total count
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How many documents total?"}' | jq '.message.content'

# Average
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the average views per post?"}' | jq '.message.content'

# Sum
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Total engagement across all content?"}' | jq '.message.content'
```

### Top-N Queries
```bash
# Top posts
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show top 5 posts by views"}' | jq '.message.content.result_data | length'

# Top by different metrics
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Most commented posts?"}' | jq '.message.content'

# Top with filters
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Top posts with more than 1000 views?"}' | jq '.message.content'
```

### Conversation Follow-Ups
```bash
#!/bin/bash

# First query
CONV=$(curl -s -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is our top post?"}' | jq -r '.conversation_id')

echo "Conversation: $CONV"

# Follow-up 1
curl -s -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"How many views?\", \"conversation_id\": \"$CONV\"}" | jq '.message.content'

# Follow-up 2
curl -s -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"Compare with second top post\", \"conversation_id\": \"$CONV\"}" | jq '.message.content'

# View full history
curl -s http://localhost:8000/api/v1/chat/conversations/$CONV/messages | jq '.messages | length'
```

---

## Expected Performance

### Latency Targets
- **Intent Classification**: < 1 second
- **SQL Generation + Execution**: 1-3 seconds
- **Code Interpreter (charts)**: 5-15 seconds
- **Total Response Time**: < 10 seconds for SQL, < 20 seconds for code

### Data Validation
- **160k records** should process without timeouts
- Large result sets automatically capped (MAX_ROWS_PER_QUERY)
- SQL timeout at 10 seconds (PostgreSQL statement_timeout)

---

## Troubleshooting

### Problem: Tests fail with "Connection refused"
**Solution**: Make sure the backend is running
```bash
# Check if running
curl http://localhost:8000/api/v1/health

# If not running, restart containers
docker-compose restart beast-app
```

### Problem: All intents classified as "unknown"
**Solution**: Check IntentClassifier configuration
```bash
# Verify intent classification works with a direct test
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Top 5 posts by views"}' \
  | jq '.message.metadata.operation'

# Should return "analytics", not "unknown"
```

### Problem: SQL queries fail or timeout
**Solution**: Check database connection
```bash
# SSH into container and test DB connection
docker exec beast-app psql -U postgres -h postgres -d beast -c "SELECT COUNT(*) FROM documents;"

# Should show row count quickly
```

### Problem: Response missing fields
**Solution**: Check response schema in response_agent.py
```bash
# Inspect actual response structure
curl -s -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Top posts?"}' | jq '.message.content | keys'

# Should include: query_type, result_data, insight_summary, verification
```

---

## Next Steps

1. **Run Phase 1 Tests**: Verify intent classification works
2. **Run Phase 2 Tests**: Verify SQL generation and execution
3. **Run Phase 3 Tests**: Verify conversation context handling
4. **Run Phase 4 Tests**: Verify no hallucinated values
5. **Run Phase 5 Tests**: Verify response formatting
6. **Monitor**: Track performance metrics over time

---

## Files Created

- **CHAT_E2E_TEST_PLAN.md** - Comprehensive test documentation
- **test_chat_e2e.py** - Automated test runner (Python)
- **CHAT_E2E_TESTING_QUICK_START.md** (this file) - Quick reference

---

## Key Files in Orchestrator

If you need to debug or modify the orchestrator:

| Component | File | Key Function |
|-----------|------|--------------|
| Intent Classification | `backend/src/app/utilities/intent_classifier.py` | `classify()` |
| Orchestrator | `backend/src/app/agents/orchestrator.py` | `execute()` |
| Analytics Agent | `backend/src/app/agents/analytics_agent.py` | `run_sql_analytics_pipeline()` |
| SQL Generation | `backend/src/app/agents/analytics_agent.py` | `generate_analytics_sql()` |
| SQL Execution | `backend/src/app/tools/dbquery_tool.py` | `execute_safe_sql()` |
| Response Formatting | `backend/src/app/agents/response_agent.py` | `build_analytics_response()` |
| Chat Service | `backend/src/app/services/chat_service.py` | `handle_user_message()` |

---

## Support

For issues or questions:
1. Check the TROUBLESHOOTING section above
2. Review test output and metadata
3. Check backend logs: `docker logs beast-app`
4. Check database: `docker exec beast-app psql ...`
