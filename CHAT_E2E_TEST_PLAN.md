# End-to-End Chat Testing Plan
## With 160k Records Production Data

---

## Test Architecture Overview

```
User Message
    ↓
POST /chat endpoint
    ↓
ChatService.handle_user_message()
    ├─ Create/retrieve conversation
    ├─ Add user message to DB
    ├─ Fetch conversation context (up to 10 prior messages)
    ├─ Call AgentOrchestrator.execute()
    │   ├─ IntentClassifier.classify() → intent + confidence
    │   ├─ Route to specialist agent based on intent:
    │   │   ├─ Analytics → SQL pipeline OR code interpreter
    │   │   ├─ Tagging → Direct tag suggestion tool
    │   │   ├─ Recommendations → Direct recommendation tool
    │   │   └─ Other → Strands agent with tools
    │   └─ Apply value-guard validation
    ├─ Store operation_data (SQL, results, metrics) in conversation.operation_data
    ├─ Add assistant message to conversation
    └─ Return ChatResponse with metadata
    ↓
Format & return to UI
```

---

## Test Scenarios

### Phase 1: Basic Intent Classification & Routing (Smoke Tests)

#### Test 1.1: Analytics Intent Detection
- **Query**: "What were the top performing posts last week?"
- **Expected Intent**: `analytics`
- **Expected Confidence**: > 0.8
- **Expected Path**: `route_analytics_query()` → SQL pipeline
- **Verification**:
  - [ ] Intent returned in response metadata
  - [ ] Confidence score visible
  - [ ] SQL query generated and logged to operation_data
  - [ ] Result contains posts with engagement metrics

**curl command:**
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What were the top performing posts last week?"
  }' | jq '.message.metadata | {operation, agents_involved}'
```

---

#### Test 1.2: Tagging Intent Detection
- **Query**: "Can you suggest tags for this article: The future of AI?"
- **Expected Intent**: `tag_suggestions`
- **Expected Path**: `_run_tag_suggestions()` → direct tool call
- **Verification**:
  - [ ] Intent detected as `tag_suggestions`
  - [ ] Tags returned as JSON array in response
  - [ ] No SQL query generated (direct tool call)
  - [ ] Tags are relevant to "future of AI"

**curl command:**
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Can you suggest tags for this article: The future of AI?"
  }' | jq '.message.content'
```

---

#### Test 1.3: Unknown Intent Fallback
- **Query**: "Tell me a joke about analytics"
- **Expected Intent**: `unknown`
- **Expected Behavior**: Graceful response without failing
- **Verification**:
  - [ ] Response is graceful (no 500 error)
  - [ ] Intent classified as `unknown` with low confidence
  - [ ] System provides helpful message

**curl command:**
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me a joke about analytics"
  }' | jq '.message'
```

---

### Phase 2: Analytics SQL Pipeline (Core Testing)

#### Test 2.1: Simple Metric Query
- **Query**: "How many total views do we have?"
- **Expected Flow**:
  1. Intent classification → `analytics`
  2. Generate SQL → `SELECT COUNT(*), SUM(views) FROM documents`
  3. Execute SQL → return aggregated metrics
  4. Build response → format with insight summary
- **Verification**:
  - [ ] SQL query appears in response metadata (`generated_sql`)
  - [ ] Result shows total count and sum of views
  - [ ] Response includes insight_summary (narrative)
  - [ ] No errors in operation_data

**Test script:**
```bash
CONV_ID=$(curl -s -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How many total views do we have?"}' | jq -r '.conversation_id')

echo "Conversation ID: $CONV_ID"
echo "Check operation_data:"
curl -s http://localhost:8000/api/v1/chat/conversations/$CONV_ID/messages \
  | jq '.messages[] | select(.role == "assistant") | .metadata'
```

---

#### Test 2.2: Top Content Query
- **Query**: "Show me the top 5 posts by engagement"
- **Expected Flow**:
  1. Intent → `analytics`
  2. SQL → Query top 5 by engagement metric
  3. Display → Show content title + engagement value
  4. Response → AnalyticsAgentSchema with result_data array
- **Verification**:
  - [ ] Response contains exactly 5 items in result_data
  - [ ] Each item has: content_id, display_label, metric_value, metric_name
  - [ ] Items are ordered by metric (highest first)
  - [ ] insight_summary explains the finding

**curl command:**
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me the top 5 posts by engagement"
  }' | jq '.message.content | {query_type, result_data: (.result_data | length), insight_summary}'
```

---

#### Test 2.3: Multi-Step Analytics (Requires Code Interpreter)
- **Query**: "Compare views and comments for our top 10 posts"
- **Expected Flow**:
  1. Intent → `analytics`
  2. Route → `autonomous_router` → decides `code_interpreter` (multi-metric comparison)
  3. SQL → Fetch top 10 posts with views + comments
  4. Code → Generate pandas/matplotlib code to create comparison chart
  5. Execute → Run code in sandbox
  6. Response → Include base64-encoded chart image
- **Verification**:
  - [ ] Response includes `code_output` metadata
  - [ ] Response includes `chart_b64` (base64 chart image)
  - [ ] Chart image is valid (can decode and display)
  - [ ] Response includes descriptive narrative

**curl command:**
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Compare views and comments for our top 10 posts. Create a chart."
  }' | jq '.message.metadata | {code_output: (.code_output != null), chart_b64: (.chart_b64 != null)}'
```

---

#### Test 2.4: Parameterized SQL (Safety Testing)
- **Query**: "What posts have more than 1000 views?"
- **Expected Flow**:
  1. Generate SQL → `SELECT * FROM documents WHERE views > 1000`
  2. Validate → Check for SQL injection (whitelist tables, readonly operations)
  3. Execute → Parameterized query (no string interpolation)
  4. Return → Safe results
- **Verification**:
  - [ ] Query executes without errors
  - [ ] Results only include posts with > 1000 views
  - [ ] No SQL injection possible (parameterized)
  - [ ] Row count reasonable (< MAX_ROWS limit)

**curl command:**
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What posts have more than 1000 views?"
  }' | jq '.message.content | {result_data: (.result_data | length)}'
```

---

### Phase 3: Conversation Context & Follow-Ups

#### Test 3.1: Context Injection in Follow-Up
- **Query 1**: "What's our top performing post this month?"
- **Query 2**: "How much engagement did it get?" (pronoun reference to Query 1 result)
- **Expected Flow**:
  1. Query 1 → Execute, store SQL + results
  2. Query 2 → Fetch conversation context (includes prior SQL/metrics)
  3. Route → Detect follow-up, mention prior result in context
  4. LLM → Reference prior result to answer follow-up
  5. Execute → New query if needed, or use cached results
- **Verification**:
  - [ ] Query 2 returns results related to the top post
  - [ ] Conversation context includes prior SQL
  - [ ] Follow-up is handled correctly without repeating work

**Test script:**
```bash
# Create conversation
CONV_ID=$(curl -s -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is our top performing post this month?"}' | jq -r '.conversation_id')

echo "Conversation ID: $CONV_ID"
echo ""

# Get the top post from first response
TOP_POST=$(curl -s http://localhost:8000/api/v1/chat/conversations/$CONV_ID/messages \
  | jq -r '.messages[] | select(.role == "assistant") | .content.result_data[0].display_label' | head -1)

echo "Top post: $TOP_POST"
echo ""

# Follow-up query
echo "Sending follow-up query..."
curl -s -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"How much engagement did it get?\",
    \"conversation_id\": \"$CONV_ID\"
  }" | jq '.message.content'
```

---

#### Test 3.2: Conversation History Retrieval
- **Expected**: GET /chat/conversations/{id}/messages returns full history
- **Verification**:
  - [ ] All messages returned in correct order
  - [ ] Each message has: id, role, content, metadata, created_at
  - [ ] Metadata includes: operation, generated_sql (if applicable)

**curl command:**
```bash
curl -s http://localhost:8000/api/v1/chat/conversations/{conversation_id}/messages \
  | jq '.messages | length, .[] | {role, operation: .metadata.operation}'
```

---

#### Test 3.3: Get Conversation Context (LLM-Formatted)
- **Expected**: GET /chat/conversations/{id}/context returns messages formatted for LLM
- **Includes**: Prior SQL queries, metrics, results formatted as context
- **Verification**:
  - [ ] Returns formatted text suitable for LLM prompt injection
  - [ ] Includes relevant prior SQL queries
  - [ ] Includes aggregated metrics from prior runs
  - [ ] Proper formatting (readable, structured)

**curl command:**
```bash
curl -s http://localhost:8000/api/v1/chat/conversations/{conversation_id}/context \
  | jq '.context' | head -50
```

---

### Phase 4: Value-Guard Validation (Safety Testing)

#### Test 4.1: Prevent Invented Metrics
- **Scenario**: Ask for a metric that doesn't exist in results
- **Query**: "What were the exact impressions on the top 3 posts?" (assuming "impressions" column doesn't exist)
- **Expected Behavior**:
  1. SQL executes successfully (alternative metrics used)
  2. Response only includes metrics from actual results
  3. value-guard validation prevents LLM from inventing numbers
- **Verification**:
  - [ ] Response includes actual columns present in data
  - [ ] No hallucinated numbers in narrative
  - [ ] insight_summary only references real values

**curl command:**
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What were the exact impressions on the top 3 posts?"
  }' | jq '.message.content | {insight_summary, result_data: (.result_data[0] | keys)}'
```

---

### Phase 5: Response Format Validation

#### Test 5.1: Analytics Response Schema
- **Expected Response Structure**:
```json
{
  "query_type": "string",
  "resolved_subject": "string",
  "result_data": [
    {
      "content_id": "string or null",
      "display_label": "string (title/label)",
      "metric_name": "string",
      "metric_value": "number or string",
      "platform": "string or null",
      "view_url": "string or null (clickable link)"
    }
  ],
  "insight_summary": "string (grounded narrative)",
  "verification": "string (source info)"
}
```
- **Verification**:
  - [ ] All fields present
  - [ ] result_data is array of objects
  - [ ] metric_value is properly formatted number
  - [ ] display_label is non-empty string
  - [ ] insight_summary never invents numbers
  - [ ] verification indicates data source

**Test script:**
```bash
curl -s -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Top 3 posts by views"}' > /tmp/response.json

echo "Response Schema Validation:"
jq '.message.content | keys' /tmp/response.json
jq '.message.content.result_data[0] | keys' /tmp/response.json
jq '.message.content.result_data | length' /tmp/response.json
```

---

#### Test 5.2: Message Response Schema
- **Expected Structure**:
```json
{
  "id": "UUID",
  "role": "assistant",
  "content": "object or string",
  "metadata": {
    "operation": "string (e.g., 'analytics', 'tagging')",
    "generated_sql": "string or null",
    "agents_involved": ["orchestrator", "analytics"],
    "code_output": "string or null",
    "chart_b64": "string or null",
    "citations": []
  },
  "created_at": "ISO8601 datetime"
}
```
- **Verification**:
  - [ ] All fields present
  - [ ] metadata.operation matches intent
  - [ ] generated_sql present for analytics queries
  - [ ] agents_involved includes appropriate agents
  - [ ] created_at is valid ISO8601

**curl command:**
```bash
curl -s -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How many posts total?"}' \
  | jq '.message | {id, role, metadata: .metadata, has_content: (.content != null)}'
```

---

## Batch Test Queries (Ready to Copy-Paste)

### Test Query Set A: Simple Aggregations
```json
[
  "How many total documents do we have?",
  "What is the average number of views per post?",
  "How many posts have comments?",
  "What's the total engagement across all content?"
]
```

### Test Query Set B: Top-N Queries
```json
[
  "Show me the top 5 posts by views",
  "What are the 3 most commented posts?",
  "Top 10 content by engagement",
  "Which posts got the most views this week?"
]
```

### Test Query Set C: Comparative Queries (Requires Code Interpreter)
```json
[
  "Compare views vs comments for our top posts (include a chart)",
  "Show me how engagement is distributed across content types",
  "Create a chart showing views trend over time"
]
```

### Test Query Set D: Follow-Ups (Use Conversation Context)
```
1. "What's our top post this month?"
2. "How much engagement did it get?"
3. "Compare it with the second top post"
4. "Show me posts from the same creator"
```

### Test Query Set E: Edge Cases / Error Handling
```json
[
  "Show me all posts with -100 views",
  "List posts where comments > views AND views < 0",
  "Get the top 1000000 posts",
  "What's the IQ of our audience?",
  "SELECT * FROM users",
  "DELETE FROM documents"
]
```

---

## Performance Metrics to Track

For each test, measure:

1. **Latency**:
   - Time from POST /chat to response (should be < 10s for SQL, < 30s for code interpreter)
   - Breakdown: SQL generation, SQL execution, response formatting

2. **Data Quality**:
   - Result count accuracy (verify against direct PG query)
   - Value accuracy (no hallucinated numbers)
   - Format compliance (all expected fields present)

3. **Safety**:
   - No SQL injection vectors
   - No unauthorized table access
   - Proper error handling for malformed SQL

4. **Consistency**:
   - Same query returns consistent results across runs
   - Conversation context properly injected in follow-ups
   - Metadata accurately reflects executed operations

---

## Tools & Utilities

### Python Test Client
```python
import requests
import json

API_BASE = "http://localhost:8000/api/v1"

class ChatClient:
    def __init__(self, base_url=API_BASE):
        self.base_url = base_url
        self.conversation_id = None

    def send_message(self, message: str, conversation_id=None):
        url = f"{self.base_url}/chat"
        payload = {"message": message}
        if conversation_id or self.conversation_id:
            payload["conversation_id"] = conversation_id or self.conversation_id

        response = requests.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        self.conversation_id = data["conversation_id"]
        return data

    def get_conversation_context(self):
        if not self.conversation_id:
            raise ValueError("No conversation ID set")
        url = f"{self.base_url}/chat/conversations/{self.conversation_id}/context"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

    def get_messages(self):
        if not self.conversation_id:
            raise ValueError("No conversation ID set")
        url = f"{self.base_url}/chat/conversations/{self.conversation_id}/messages"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

# Usage
client = ChatClient()
response = client.send_message("What are the top 5 posts?")
print(json.dumps(response, indent=2))

# Check conversation context
context = client.get_conversation_context()
print("Conversation context:")
print(context)

# Get full message history
messages = client.get_messages()
print(f"Conversation has {len(messages['messages'])} messages")
```

### cURL Test Runner
```bash
#!/bin/bash
# test_e2e_chat.sh

API="http://localhost:8000/api/v1"
TEST_QUERIES=(
  "How many total documents do we have?"
  "Show me the top 5 posts by views"
  "What's the average views per post?"
)

for i in "${!TEST_QUERIES[@]}"; do
    echo "========================================="
    echo "Test $((i+1)): ${TEST_QUERIES[$i]}"
    echo "========================================="

    curl -s -X POST "$API/chat" \
      -H "Content-Type: application/json" \
      -d "{\"message\": \"${TEST_QUERIES[$i]}\"}" | jq '.message | {operation: .metadata.operation, result_count: (.content.result_data | length), intent_confidence: .metadata}'

    echo ""
done
```

---

## Expected Outcomes

### Success Criteria for Each Phase

**Phase 1**: All intent classifications return correct intent with confidence > 0.8
**Phase 2**: All SQL queries execute correctly, return accurate results, within performance budget
**Phase 3**: Conversation context properly injected, follow-ups handled correctly
**Phase 4**: No hallucinated values, only factual data from results
**Phase 5**: All responses conform to expected schemas, proper formatting

### Sample Success Output

```json
{
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "role": "assistant",
    "content": {
      "query_type": "top_metrics",
      "resolved_subject": "posts",
      "result_data": [
        {
          "content_id": "post_123",
          "display_label": "Top Post Title",
          "metric_name": "views",
          "metric_value": 5432,
          "platform": "twitter",
          "view_url": "https://twitter.com/user/status/123"
        }
      ],
      "insight_summary": "Your highest performing post received 5,432 views, 231 comments, and was shared 45 times.",
      "verification": "Data extracted from 160,000 documents in analytics database"
    },
    "metadata": {
      "operation": "analytics",
      "generated_sql": "SELECT content_id, title, platform, views, comments FROM documents ORDER BY views DESC LIMIT 5",
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

## Troubleshooting Guide

| Issue | Likely Cause | Verification |
|-------|--------------|--------------|
| Intent always classified as "unknown" | IntentClassifier confidence threshold too high | Check confidence value, lower threshold in config |
| SQL never generates | Analytics agent not selected | Check orchestrator routing logic |
| SQL errors ("table not found") | Table whitelist missing 'documents' | Verify dbquery_tool.py table whitelist |
| Hallucinated values in response | value-guard validation not applied | Check response_agent.py validation logic |
| Follow-ups don't use context | Conversation context not being fetched | Verify conversation_context getter in chat_service.py |
| Code interpreter not used for multi-metric | autonomous_router routing to SQL always | Check autonomous_router confidence logic |

---

## Next Steps

1. **Deploy** updated code (latest commits)
2. **Run Phase 1 tests** - Verify intent classification works
3. **Run Phase 2 tests** - Verify SQL pipeline with actual data
4. **Run Phase 3 tests** - Verify conversation context handling
5. **Run Phase 4 tests** - Verify value-guard prevents hallucinations
6. **Run Phase 5 tests** - Verify response formatting
7. **Document** any issues found
8. **Iterate** on improvements based on test results
