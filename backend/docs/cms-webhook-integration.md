# CMS Article Webhook Integration Guide

## Overview

The Beast platform receives real-time article events from your CMS via HMAC-signed webhooks. When articles are published, updated, or deleted, the webhook endpoint automatically:

1. Verifies the HMAC signature for security
2. Deduplicates events (prevents re-processing via `event_id`)
3. Routes to the appropriate handler (article vectorization, soft-delete, etc.)
4. Queues async processing via Celery
5. Returns HTTP 202 Accepted immediately

## Webhook Endpoint

**URL**: `POST /api/ingest/webhook`

**Base URL**: `https://api.yourdomain.com` (replace with your deployment URL)

**Full URL**: `https://api.yourdomain.com/api/ingest/webhook`

## Authentication & Security

### HMAC Signature Verification

All webhook payloads MUST be signed with HMAC-SHA256 and include the signature in the `X-TNN-Signature` header.

**Header Format**: 

```
X-TNN-Signature: sha256=<hex-encoded-signature>
```

**Signature Computation**:

```python
import hmac
import hashlib
import json

# Raw request body as bytes
body_bytes = request.body

# Shared secret (configured in Beast platform settings)
webhook_secret = "your-webhook-secret-here"

# Compute signature
signature = "sha256=" + hmac.new(
    webhook_secret.encode(),
    body_bytes,
    hashlib.sha256
).hexdigest()

# Add signature to request header
headers = {
    "X-TNN-Signature": signature,
    "Content-Type": "application/json"
}
```

**Important**: Always send the raw request body bytes for HMAC computation. Do NOT re-serialize JSON after parsing.

## Payload Format

All webhook payloads follow this structure:

```json
{
  "source": "cms",
  "event_type": "article.published",
  "event_id": "unique-event-id-12345",
  "data": {
    "article_id": "article-uuid-or-slug",
    "title": "Article Title",
    "content": "Full article body text...",
    "published_at": "2026-04-28T10:30:00Z",
    "metadata": {
      "author": "Jane Doe",
      "category": "Technology",
      "tags": ["ai", "llm"]
    }
  }
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | string | Yes | Event source identifier (e.g., `"cms"`) |
| `event_type` | string | Yes | Type of event: `"article.published"`, `"article.updated"`, `"article.deleted"` |
| `event_id` | string | No (but recommended) | Unique event ID from CMS for deduplication; enables at-least-once delivery pattern |
| `data.article_id` | string | Yes | Unique article identifier in CMS |
| `data.title` | string | No | Article title (used in recommendations display) |
| `data.content` | string | Yes (for published/updated) | Full article body text (will be chunked and embedded) |
| `data.published_at` | ISO 8601 datetime | No | Article publication timestamp |
| `data.metadata` | object | No | Additional metadata (author, category, tags, etc.) |

## Supported Event Types

### 1. `article.published`

A new article has been published in the CMS.

**Action**: The article is fetched, chunked, embedded using all-MiniLM-L6-v2, and upserted into the `article_vectors` table.

**Request Example**:

```bash
curl -X POST https://api.yourdomain.com/api/ingest/webhook \
  -H "Content-Type: application/json" \
  -H "X-TNN-Signature: sha256=abc123def456..." \
  -d '{
    "source": "cms",
    "event_type": "article.published",
    "event_id": "evt_2026_04_28_001",
    "data": {
      "article_id": "art_12345",
      "title": "Breaking News: AI Advances",
      "content": "Full article content here...",
      "published_at": "2026-04-28T10:30:00Z",
      "metadata": {"author": "John Doe"}
    }
  }'
```

**Response**: HTTP 202 Accepted

```json
{
  "event_id": "evt_2026_04_28_001",
  "routed_to": "article_webhook_handler",
  "status": "queued",
  "message": "Webhook received and queued for processing"
}
```

### 2. `article.updated`

An existing article has been updated in the CMS.

**Action**: The article is re-fetched, re-chunked, re-embedded, and the `article_vectors` row is updated (including `updated_at` timestamp).

**Request Example**: Same as `article.published` but with `"event_type": "article.updated"`

### 3. `article.deleted`

An article has been deleted or unpublished in the CMS.

**Action**: The corresponding `article_vectors` row is soft-deleted by setting `deleted_at` timestamp. The row remains in the database but is filtered out of all recommendation queries.

**Data Fields**: Only `article_id` is required in `data` object.

**Request Example**:

```bash
curl -X POST https://api.yourdomain.com/api/ingest/webhook \
  -H "Content-Type: application/json" \
  -H "X-TNN-Signature: sha256=abc123def456..." \
  -d '{
    "source": "cms",
    "event_type": "article.deleted",
    "event_id": "evt_2026_04_28_002",
    "data": {
      "article_id": "art_12345"
    }
  }'
```

## Retry & Delivery Behavior

### At-Least-Once Delivery

The Beast platform uses an **at-least-once** delivery pattern:

- Webhooks may be delivered more than once if network issues or processing errors occur
- Use the `event_id` field to detect and skip duplicate events
- Duplicate events are silently discarded (HTTP 202 returned, but processing is skipped)

**Important**: Always include `event_id` in your webhook payloads to enable deduplication.

### Retry Strategy (CMS → Beast)

If the Beast webhook endpoint returns an error (4xx, 5xx, timeout):

1. **Recommended**: Retry with exponential backoff (base 2s, max 60s, up to 5 retries)
2. **Dedup safety**: Because Beast uses `event_id`-based deduplication, retries are safe — duplicate events won't cause double-processing

### Example Retry Logic

```python
import time
import requests

def send_webhook_with_retry(url, payload, webhook_secret, max_retries=5):
    headers = {
        "Content-Type": "application/json",
        "X-TNN-Signature": compute_hmac(payload, webhook_secret)
    }
    
    body_bytes = json.dumps(payload).encode()
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, data=body_bytes, headers=headers, timeout=10)
            if response.status_code in (200, 202):
                return response
            elif response.status_code >= 500:
                raise requests.RequestException(f"Server error: {response.status_code}")
        except (requests.RequestException, requests.Timeout) as e:
            if attempt < max_retries - 1:
                backoff = 2 ** attempt
                time.sleep(backoff)
            else:
                raise
    
    return None
```

## Webhook Event Logging & Monitoring

### Admin Monitoring Endpoint

**URL**: `GET /api/ingest/webhook/events`

**Query Parameters**:

- `source` (optional): Filter by source (e.g., `"cms"`)
- `event_type` (optional): Filter by event type (e.g., `"article.published"`)
- `limit` (optional, default 50): Max results
- `offset` (optional, default 0): Pagination offset

**Response**:

```json
{
  "total": 250,
  "offset": 0,
  "limit": 50,
  "items": [
    {
      "id": "uuid-of-webhook-event",
      "event_id": "evt_2026_04_28_001",
      "source": "cms",
      "event_type": "article.published",
      "hmac_verified": true,
      "processed_at": "2026-04-28T10:31:15Z",
      "created_at": "2026-04-28T10:30:00Z"
    },
    ...
  ]
}
```

## Error Handling

### HTTP Response Codes

| Code | Meaning | Action |
|------|---------|--------|
| 202 | Accepted | Webhook queued successfully; check logs later for processing status |
| 400 | Bad Request | Payload is malformed or missing required fields; do NOT retry |
| 401 | Unauthorized | HMAC signature is invalid; check webhook secret configuration |
| 429 | Too Many Requests | Rate limit exceeded; retry with exponential backoff |
| 500 | Internal Server Error | Transient server error; retry with exponential backoff |

### Signature Verification Errors

If you receive HTTP 401 with "Invalid webhook signature":

1. Verify the `webhook_secret` is correctly configured in Beast settings
2. Check that you're **using raw request body bytes** (not re-serialized JSON) for HMAC computation
3. Ensure you're using SHA256 algorithm
4. Verify the header format is exactly `sha256=<hex>`

## Configuration

### Setting Up Webhooks in Beast

1. Log in to the Beast admin board at `https://yourdomain.com/admin/settings`
2. Go to **Settings** tab
3. Locate `WEBHOOK_SECRET` setting
4. Generate a strong random secret (e.g., 32 bytes base64):
   ```bash
   python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
   ```
5. Save the secret in both Beast settings and your CMS webhook configuration

### Configuring CMS Webhook

In your CMS administrative interface:

1. Go to Webhooks or Integrations settings
2. Create a new webhook with:
   - **Endpoint URL**: `https://api.yourdomain.com/api/ingest/webhook`
   - **Secret**: (same as WEBHOOK_SECRET in Beast settings)
   - **Events**: Select `article:published`, `article:updated`, `article:deleted`
   - **Content Type**: `application/json`
   - **Signature Header**: `X-TNN-Signature`

## Examples

### Python (Requests Library)

```python
import requests
import json
import hmac
import hashlib

def send_webhook(event_type, article_id, content, webhook_secret):
    url = "https://api.yourdomain.com/api/ingest/webhook"
    
    payload = {
        "source": "cms",
        "event_type": event_type,
        "event_id": f"evt_{article_id}_{int(time.time())}",
        "data": {
            "article_id": article_id,
            "content": content,
        }
    }
    
    body_bytes = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(
        webhook_secret.encode(),
        body_bytes,
        hashlib.sha256
    ).hexdigest()
    
    response = requests.post(
        url,
        data=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-TNN-Signature": signature,
        },
        timeout=10
    )
    
    return response.status_code, response.json()
```

### JavaScript (Node.js)

```javascript
import crypto from 'crypto';
import fetch from 'node-fetch';

function computeHmac(body, secret) {
  return 'sha256=' + crypto
    .createHmac('sha256', secret)
    .update(body)
    .digest('hex');
}

async function sendWebhook(eventType, articleId, content, webhookSecret) {
  const url = 'https://api.yourdomain.com/api/ingest/webhook';
  
  const payload = {
    source: 'cms',
    event_type: eventType,
    event_id: `evt_${articleId}_${Date.now()}`,
    data: {
      article_id: articleId,
      content: content,
    },
  };
  
  const bodyBytes = JSON.stringify(payload);
  const signature = computeHmac(bodyBytes, webhookSecret);
  
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-TNN-Signature': signature,
    },
    body: bodyBytes,
  });
  
  return response.status, await response.json();
}
```

### cURL

```bash
#!/bin/bash

WEBHOOK_URL="https://api.yourdomain.com/api/ingest/webhook"
WEBHOOK_SECRET="your-secret-here"
ARTICLE_ID="article-123"
EVENT_ID="evt_article_123_$(date +%s)"

PAYLOAD='{
  "source": "cms",
  "event_type": "article.published",
  "event_id": "'$EVENT_ID'",
  "data": {
    "article_id": "'$ARTICLE_ID'",
    "title": "Test Article",
    "content": "This is test article content.",
    "published_at": "2026-04-28T10:30:00Z"
  }
}'

SIGNATURE="sha256=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | cut -d' ' -f2)"

curl -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-TNN-Signature: $SIGNATURE" \
  -d "$PAYLOAD"
```

## Support & Troubleshooting

### Checking Webhook Delivery Status

View recent webhook events:

```bash
curl "https://api.yourdomain.com/api/ingest/webhook/events?limit=10" \
  -H "Authorization: Bearer <admin-token>"
```

### Common Issues

**Issue**: HTTP 401 Unauthorized

- **Cause**: Invalid HMAC signature
- **Solution**: Verify the `webhook_secret` configuration matches in both Beast and CMS

**Issue**: HTTP 202 but article not vectorized

- **Cause**: Celery task is still processing or failed
- **Solution**: Check Celery worker logs and Redis for task queue status

**Issue**: Duplicate articles in recommendations

- **Cause**: Missing or duplicate `event_id` values
- **Solution**: Ensure each webhook payload includes a unique `event_id`

## Rate Limiting

The webhook endpoint does not enforce rate limits on a per-event basis. However:

- **Celery worker concurrency**: Default 4 concurrent workers (configurable)
- **Per-article processing**: Articles are processed sequentially per `article_id`
- **Recommendation**: For bulk article imports (1000+ articles), use the batch scraper endpoint instead of webhooks

## Security Considerations

1. **Always use HTTPS** for webhook URLs
2. **Rotate webhook secrets periodically** (at least quarterly)
3. **Verify HMAC signatures** on every webhook delivery
4. **Monitor webhook logs** for unauthorized access attempts
5. **Use event_id deduplication** to prevent re-processing attacks
