# Data Model: Agentic AI Assistant Platform

**Feature**: 001-agentic-ai-assistant
**Date**: 2026-03-05

## Entity Relationship Overview

```text
users 1──* conversations 1──* messages
documents (analytics + embeddings, unified table)
summaries (pre-computed aggregations)
tags (content classification with embeddings)
[External] MongoDB articles (via CMS API / direct)
```

## Entities

### documents (PostgreSQL — existing, extended)

Unified table combining analytics data columns with vector embeddings. Source: `db/init.sql`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | PK | Auto-increment ID |
| sheet_name | text | NOT NULL | Source sheet identifier |
| row_number | integer | NOT NULL | Row within sheet |
| text | text | NOT NULL | Concatenated text representation of the row |
| doc_metadata | jsonb | | Additional metadata |
| embedding | vector(384) | | all-MiniLM-L6-v2 embedding |
| date | date | | Analytics date |
| profile_name | text | | Social media profile name |
| profile_url | text | | Profile URL |
| profile_id | text | | Platform profile ID |
| post_detail_url | text | | Direct link to post |
| content_id | text | | Platform content ID |
| platform | text | indexed | Social platform (Instagram, Facebook, etc.) |
| content_type | text | indexed | Post type classification |
| media_type | text | indexed | Media format (image, video, etc.) |
| origin_of_the_content | text | | Content origin |
| title | text | | Post title |
| description | text | | Post description |
| author_url | text | | Author profile URL |
| author_id | text | | Author platform ID |
| author_name | text | indexed | Author display name |
| content | text | | Full post content/body |
| link_url | text | | Shared link URL |
| view_on_platform | text | | Platform view link |
| organic_interactions | integer | | Organic interaction count |
| total_interactions | integer | indexed | All interactions |
| total_reactions | integer | | Reaction count |
| total_comments | integer | | Comment count |
| total_shares | integer | | Share count |
| unpublished | boolean | | Unpublished flag |
| engagements | integer | | Engagement count |
| total_reach | integer | | Combined reach |
| paid_reach | integer | | Paid reach |
| organic_reach | integer | | Organic reach |
| total_impressions | integer | | Combined impressions |
| paid_impressions | integer | | Paid impressions |
| organic_impressions | integer | | Organic impressions |
| reach_engagement_rate | numeric | | Engagement/reach ratio |
| total_likes | integer | | Like count |
| video_length_sec | integer | | Video duration |
| video_views | integer | indexed | Video view count |
| total_video_view_time_sec | integer | | Total watch time |
| avg_video_view_time_sec | numeric | | Average watch time |
| completion_rate | numeric | | Video completion rate |
| labels | text | indexed | Applied labels |
| label_groups | text | | Label group classification |
| created_at | timestamp | NOT NULL, DEFAULT NOW() | Record creation time |
| updated_at | timestamp | NOT NULL, DEFAULT NOW() | Last update time |

**Unique constraint**: `(sheet_name, row_number)`
**Key indexes**: platform, media_type, content_type, profile_name, author_name, date, video_views, total_interactions, labels, embedding (ivfflat)

### summaries (PostgreSQL — new)

Pre-computed analytics aggregations at multiple granularities.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | serial | PK | Auto-increment ID |
| granularity | varchar(10) | NOT NULL | 'daily', 'weekly', 'monthly' |
| period_start | date | NOT NULL | Start of period |
| period_end | date | NOT NULL | End of period |
| platform | text | | Platform filter (NULL = all platforms) |
| profile_name | text | | Profile filter (NULL = all profiles) |
| metric_name | varchar(50) | NOT NULL | Metric key (e.g., 'total_reach', 'total_interactions') |
| metric_value | numeric | NOT NULL | Aggregated value |
| record_count | integer | NOT NULL | Number of records aggregated |
| metadata | jsonb | | Additional aggregation details (top posts, day-of-week breakdown) |
| computed_at | timestamp | NOT NULL, DEFAULT NOW() | When this summary was computed |

**Unique constraint**: `(granularity, period_start, platform, profile_name, metric_name)`
**Key indexes**: granularity, period_start, platform, metric_name

### tags (PostgreSQL — existing)

Content classification tags with semantic embeddings.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| slug | varchar | PK | URL-safe identifier |
| name | text | NOT NULL | Human-readable tag name |
| description | text | | Tag description |
| variations | jsonb | | Array of synonyms/variations |
| is_primary | boolean | NOT NULL, DEFAULT FALSE | Primary tag flag |
| embedding | vector(384) | | Semantic embedding for similarity matching |

**Key indexes**: is_primary

### users (PostgreSQL — existing)

Authenticated users with local or AD credentials.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK, DEFAULT gen_random_uuid() | User ID |
| username | varchar(255) | UNIQUE, NOT NULL | Login username |
| email | varchar(255) | UNIQUE, NOT NULL | Email address |
| full_name | varchar(255) | | Display name |
| hashed_password | varchar(255) | | bcrypt hash (nullable for AD users) |
| is_active | boolean | NOT NULL, DEFAULT TRUE | Account active flag |
| is_admin | boolean | NOT NULL, DEFAULT FALSE | Admin privileges |
| auth_provider | varchar(50) | NOT NULL, DEFAULT 'local' | 'local' or 'active_directory' |
| ad_username | varchar(255) | | AD username if different |
| created_at | timestamp | NOT NULL, DEFAULT NOW() | Account creation |
| updated_at | timestamp | NOT NULL, DEFAULT NOW() | Last update |
| last_login | timestamp | | Last login time |

### conversations (PostgreSQL — existing)

Chat sessions linking users to message sequences.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK, DEFAULT gen_random_uuid() | Conversation ID |
| title | varchar(255) | NOT NULL | Conversation title |
| created_at | timestamp | NOT NULL, DEFAULT NOW() | Session start |
| updated_at | timestamp | NOT NULL, DEFAULT NOW() | Last activity |
| user_id | uuid | FK → users.id ON DELETE SET NULL | Owner |
| extra_metadata | jsonb | | Message count, tags, etc. |

### messages (PostgreSQL — existing)

Individual messages within a conversation.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK, DEFAULT gen_random_uuid() | Message ID |
| conversation_id | uuid | FK → conversations.id ON DELETE CASCADE, NOT NULL | Parent conversation |
| role | varchar(20) | NOT NULL, CHECK IN ('user', 'assistant') | Message sender |
| content | text | NOT NULL | Message text |
| operation | varchar(50) | | Operation type (e.g., 'query_analytics', 'suggest_tags') |
| operation_data | jsonb | | Complete response data including query results |
| operation_metadata | jsonb | | Timing, model used, tokens consumed |
| created_at | timestamp | NOT NULL, DEFAULT NOW() | Message timestamp |
| sequence_number | integer | NOT NULL | Order within conversation |

### Article (MongoDB — external, read-only)

Articles in the CMS MongoDB database. Accessed via CMS REST API for single fetch, direct MongoDB for bulk similarity search.

| Field | Type | Description |
|-------|------|-------------|
| _id | ObjectId | MongoDB document ID |
| title | string | Article headline |
| body | string | Full article content (HTML or plain text) |
| slug | string | URL slug |
| tags | array[string] | Assigned tag slugs |
| author | object | Author info (name, id) |
| published_at | datetime | Publication date |
| category | string | Article category |
| embedding | array[float] | Pre-computed 384-dim embedding (if available) |

**Note**: MongoDB schema is owned by the CMS; the assistant reads but never writes.

## State Transitions

### Data Ingestion States

```text
EMAIL_RECEIVED → ATTACHMENT_DOWNLOADED → VALIDATING → VALIDATED → INGESTING → INGESTED
                                           ↓
                                    VALIDATION_FAILED (partial: valid rows proceed)
```

### Conversation States

Conversations have no explicit state machine — they grow by appending messages. The `updated_at` timestamp tracks last activity.

## Relationships

- `users` 1:N `conversations` — a user owns many conversations
- `conversations` 1:N `messages` — a conversation contains ordered messages
- `documents` — standalone analytics records, no FK relationships
- `summaries` — derived from `documents`, recomputed after ingestion
- `tags` — standalone, referenced by slug in articles and suggestions
- Articles (MongoDB) — external, referenced by CMS article ID
