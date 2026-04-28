# CMS API Contract

## Overview

The CMS (Content Management System) API provides access to published articles for tag suggestion and recommendation workflows. The Beast application integrates with this API via `backend/src/app/tools/cms_tools.py`.

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `CMS_API_BASE_URL` | `http://localhost:8080` | Base URL for the CMS REST API |
| `CMS_API_KEY` | _(required)_ | API key for authentication |
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection URI for direct article search |
| `MONGODB_DB_NAME` | `cms` | MongoDB database name |
| `MONGODB_ARTICLES_COLLECTION` | `articles` | MongoDB collection for articles |

## Authentication

All REST API requests must include the API key in the `X-API-Key` header:

```
X-API-Key: <CMS_API_KEY>
```

## Endpoints

### GET /articles/{id}

Fetch a single article by its CMS ID.

**Request:**
```
GET /articles/12345
X-API-Key: <key>
```

**Response (200 OK):**
```json
{
  "id": "12345",
  "title": "Breaking News: Event X Happened",
  "body": "Full article body text...",
  "excerpt": "Short excerpt...",
  "author": "Jane Doe",
  "published_at": "2026-03-15T10:00:00Z",
  "updated_at": "2026-03-15T12:00:00Z",
  "status": "published",
  "metadata": {
    "platform": "web",
    "section": "news",
    "tags": ["existing-tag-1"],
    "word_count": 450,
    "language": "en"
  }
}
```

**Error Responses:**

| Status | Description |
|---|---|
| 404 | Article not found |
| 403 | Unauthorized — invalid or missing API key |
| 429 | Rate limit exceeded — retry after `Retry-After` header |
| 500 | Internal server error |

### GET /articles/search

Search articles by keyword.

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `q` | string | Search query |
| `limit` | int | Max results (default: 10, max: 100) |
| `offset` | int | Pagination offset (default: 0) |
| `status` | string | Filter by status: `published`, `draft`, `all` (default: `published`) |

**Response (200 OK):**
```json
{
  "total": 42,
  "offset": 0,
  "limit": 10,
  "articles": [
    {
      "id": "12345",
      "title": "...",
      "excerpt": "...",
      "published_at": "2026-03-15T10:00:00Z"
    }
  ]
}
```

## Direct MongoDB Access

For bulk search and semantic similarity queries, the application connects directly to MongoDB using the motor async driver.

**Collection Schema (`articles`):**

```json
{
  "_id": "ObjectId",
  "cms_id": "string",
  "title": "string",
  "body": "string",
  "excerpt": "string",
  "author": "string",
  "published_at": "ISODate",
  "embedding": [0.123, ...],
  "metadata": {}
}
```

The `embedding` field is a 384-dimensional float array from the `all-MiniLM-L6-v2` model, used for vector similarity search.

## Rate Limits

- 100 requests/minute per API key
- 1000 requests/hour per API key
- Retry-After header indicates when to retry on 429

## Content Extraction

The `cms_tools.py` normalizes article content by:
1. Concatenating `title + " " + body` for embedding generation
2. Stripping HTML tags from body text
3. Truncating to 2000 characters for embedding inputs
