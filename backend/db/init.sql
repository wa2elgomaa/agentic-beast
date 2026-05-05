-- Initialize pgvector extension and create all application tables.
-- Run automatically by docker-entrypoint-initdb.d on first container start.
-- Keep in sync with SQLAlchemy ORM models in backend/src/app/schemas/.

CREATE EXTENSION IF NOT EXISTS vector;


-- ============================================================
-- documents
-- Source of truth: backend/src/app/schemas/document.py
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
  id                           SERIAL PRIMARY KEY,
  sheet_name                   TEXT        NOT NULL,
  row_number                   INTEGER     NOT NULL,
  text                         TEXT        NOT NULL,
  doc_metadata                 JSONB,
  embedding                    VECTOR(384),

  -- Profile & Post Information
  published_date               DATE,
  published_time               TIME,
  received_at                  DATE,
  reported_time                TIME,
  profile_name                 TEXT,
  profile_url                  TEXT,
  profile_id                   TEXT,
  post_detail_url              TEXT,
  content_id                   TEXT,

  -- Platform & Content Classification
  platform                     TEXT,
  content_type                 TEXT,
  media_type                   TEXT,
  origin_of_the_content        TEXT,

  -- Content Details
  title                        TEXT,
  description                  TEXT,
  author_url                   TEXT,
  author_id                    TEXT,
  author_name                  TEXT,
  content                      TEXT,
  link_url                     TEXT,
  view_on_platform             TEXT,

  -- Engagement Metrics
  organic_interactions         INTEGER,
  total_interactions           INTEGER,
  total_reactions              INTEGER,
  total_comments               INTEGER,
  total_shares                 INTEGER,
  unpublished                  BOOLEAN,
  engagements                  INTEGER,

  -- Reach Metrics
  total_reach                  INTEGER,
  paid_reach                   INTEGER,
  organic_reach                INTEGER,

  -- Impression Metrics
  total_impressions            INTEGER,
  paid_impressions             INTEGER,
  organic_impressions          INTEGER,
  reach_engagement_rate        NUMERIC,

  -- Video Metrics
  total_likes                  INTEGER,
  video_length_sec             INTEGER,
  video_views                  INTEGER,
  total_video_view_time_sec    INTEGER,
  avg_video_view_time_sec      NUMERIC,
  completion_rate              NUMERIC,

  -- Labels & Categorization
  labels                       TEXT,
  label_groups                 TEXT,

  -- Content Deduplication & Cross-Platform Matching
  identifier_cleaned           VARCHAR(500),
  identifier_hash              VARCHAR(64),
  connection_identifier_hash   VARCHAR(64),

  -- Differential Metrics (deltas from previous ingestion)
  metric_deltas                JSONB,

  -- Per-row stable UUID for external content identifier mapping
  beast_uuid                   UUID,
  is_current                   BOOLEAN     NOT NULL DEFAULT FALSE,

  -- Timestamps
  created_at                   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at                   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS documents_embedding_idx
    ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE UNIQUE INDEX IF NOT EXISTS documents_unique_key
    ON documents (sheet_name, row_number);
CREATE INDEX IF NOT EXISTS documents_platform_idx              ON documents (platform);
CREATE INDEX IF NOT EXISTS documents_media_type_idx            ON documents (media_type);
CREATE INDEX IF NOT EXISTS documents_content_type_idx          ON documents (content_type);
CREATE INDEX IF NOT EXISTS documents_profile_name_idx          ON documents (profile_name);
CREATE INDEX IF NOT EXISTS documents_author_name_idx           ON documents (author_name);
CREATE INDEX IF NOT EXISTS documents_published_date_idx        ON documents (published_date);
CREATE INDEX IF NOT EXISTS documents_video_views_idx           ON documents (video_views);
CREATE INDEX IF NOT EXISTS documents_total_interactions_idx    ON documents (total_interactions);
CREATE INDEX IF NOT EXISTS documents_labels_idx                ON documents (labels);
CREATE INDEX IF NOT EXISTS documents_identifier_hash_idx       ON documents (identifier_hash);
CREATE INDEX IF NOT EXISTS documents_conn_identifier_hash_idx  ON documents (connection_identifier_hash);
CREATE INDEX IF NOT EXISTS documents_beast_uuid_idx            ON documents (beast_uuid);


-- ============================================================
-- tags
-- Source of truth: backend/src/app/schemas/tag.py
-- ============================================================
CREATE TABLE IF NOT EXISTS tags (
    slug        VARCHAR     PRIMARY KEY,
    name        TEXT        NOT NULL,
    description TEXT,
    variations  JSONB,
    is_primary  BOOLEAN     NOT NULL DEFAULT FALSE,
    embedding   VECTOR(384),
    created_at  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tags_is_primary ON tags (is_primary);


-- ============================================================
-- users
-- Source of truth: backend/src/app/schemas/user.py
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(255) UNIQUE NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    full_name       VARCHAR(255),
    hashed_password VARCHAR(255),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    is_admin        BOOLEAN      NOT NULL DEFAULT FALSE,
    auth_provider   VARCHAR(50)  NOT NULL DEFAULT 'local',
    ad_username     VARCHAR(255),
    last_login      TIMESTAMP,
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username      ON users (username);
CREATE INDEX IF NOT EXISTS idx_users_email         ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_auth_provider ON users (auth_provider);
CREATE INDEX IF NOT EXISTS idx_users_is_active     ON users (is_active);


-- ============================================================
-- conversations
-- Source of truth: backend/src/app/schemas/conversation.py
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title          VARCHAR(255) NOT NULL,
    user_id        UUID         REFERENCES users(id) ON DELETE SET NULL,
    extra_metadata JSONB,
    created_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_user_id    ON conversations (user_id);


-- ============================================================
-- messages
-- Source of truth: backend/src/app/schemas/conversation.py
-- ============================================================
CREATE TABLE IF NOT EXISTS messages (
    id                 UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id    UUID         NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sequence_number    INTEGER      NOT NULL,
    role               VARCHAR(20)  NOT NULL CHECK (role IN ('user', 'assistant')),
    content            TEXT         NOT NULL,
    operation          VARCHAR(50),
    operation_data     JSONB,
    operation_metadata JSONB,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages (conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at      ON messages (created_at);
CREATE INDEX IF NOT EXISTS idx_messages_sequence        ON messages (conversation_id, sequence_number);


-- ============================================================
-- password_reset_tokens
-- Source of truth: backend/src/app/schemas/password_reset.py
-- ============================================================
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token      VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP    NOT NULL,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id    ON password_reset_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token      ON password_reset_tokens (token);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_expires_at ON password_reset_tokens (expires_at);


-- ============================================================
-- summaries
-- Source of truth: backend/src/app/schemas/summary.py
-- ============================================================
CREATE TABLE IF NOT EXISTS summaries (
    id             SERIAL       PRIMARY KEY,
    granularity    VARCHAR(20)  NOT NULL,
    period_start   DATE         NOT NULL,
    period_end     DATE         NOT NULL,
    platform       VARCHAR(50),
    metric_name    VARCHAR(100) NOT NULL,
    metric_value   NUMERIC      NOT NULL,
    extra_metadata TEXT,
    created_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_summaries_granularity ON summaries (granularity);
CREATE INDEX IF NOT EXISTS idx_summaries_period      ON summaries (period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_summaries_platform    ON summaries (platform);
CREATE INDEX IF NOT EXISTS idx_summaries_metric_name ON summaries (metric_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_summaries_unique
    ON summaries (granularity, period_start, platform, metric_name);


-- ============================================================
-- time_of_day_metrics
-- Source of truth: backend/src/app/schemas/summary.py
-- ============================================================
CREATE TABLE IF NOT EXISTS time_of_day_metrics (
    id           SERIAL       PRIMARY KEY,
    hour_of_day  INTEGER      NOT NULL,
    day_of_week  INTEGER,
    metric_name  VARCHAR(100) NOT NULL,
    metric_value NUMERIC      NOT NULL,
    sample_count INTEGER      NOT NULL DEFAULT 0,
    platform     VARCHAR(50),
    created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- ingestion_tasks
-- Source of truth: backend/src/app/schemas/ingestion_task.py
-- ============================================================
CREATE TABLE IF NOT EXISTS ingestion_tasks (
    id                              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name                            VARCHAR(255) NOT NULL,
    description                     TEXT,
    adaptor_type                    VARCHAR(50)  NOT NULL,
    adaptor_config                  JSONB,
    schedule_type                   VARCHAR(50)  NOT NULL DEFAULT 'none',
    cron_expression                 VARCHAR(255),
    run_at                          TIMESTAMP,
    is_active                       BOOLEAN      NOT NULL DEFAULT TRUE,
    status                          VARCHAR(50)  NOT NULL DEFAULT 'active',
    test_execution_enabled          BOOLEAN      NOT NULL DEFAULT FALSE,
    test_execution_interval_minutes INTEGER      NOT NULL DEFAULT 60,
    deduplication_enabled           BOOLEAN      NOT NULL DEFAULT TRUE,
    dedup_lookback_imports          INTEGER,
    created_by                      UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at                      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ingestion_tasks_status     ON ingestion_tasks (status);
CREATE INDEX IF NOT EXISTS idx_ingestion_tasks_created_by ON ingestion_tasks (created_by);


-- ============================================================
-- ingestion_task_runs
-- Source of truth: backend/src/app/schemas/ingestion_task.py
-- ============================================================
CREATE TABLE IF NOT EXISTS ingestion_task_runs (
    id                      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                 UUID         NOT NULL REFERENCES ingestion_tasks(id) ON DELETE CASCADE,
    parent_run_id           UUID         REFERENCES ingestion_task_runs(id) ON DELETE CASCADE,
    started_at              TIMESTAMP,
    completed_at            TIMESTAMP,
    status                  VARCHAR(50)  NOT NULL DEFAULT 'pending',
    rows_inserted           INTEGER      NOT NULL DEFAULT 0,
    rows_updated            INTEGER      NOT NULL DEFAULT 0,
    rows_failed             INTEGER      NOT NULL DEFAULT 0,
    error_message           TEXT,
    error_type              VARCHAR(50),
    error_code              VARCHAR(50),
    total_rows_processed    INTEGER      NOT NULL DEFAULT 0,
    total_duplicates_found  INTEGER      NOT NULL DEFAULT 0,
    total_deltas_calculated INTEGER      NOT NULL DEFAULT 0,
    deduplication_enabled   BOOLEAN      NOT NULL DEFAULT TRUE,
    failed_emails_count     INTEGER      NOT NULL DEFAULT 0,
    retry_emails_count      INTEGER      NOT NULL DEFAULT 0,
    celery_task_id          VARCHAR(255),
    run_metadata            JSONB,
    created_at              TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ingestion_task_runs_task_id        ON ingestion_task_runs (task_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_task_runs_status         ON ingestion_task_runs (status);
CREATE INDEX IF NOT EXISTS idx_ingestion_task_runs_celery_task_id ON ingestion_task_runs (celery_task_id);


-- ============================================================
-- schema_mapping_templates
-- Source of truth: backend/src/app/schemas/ingestion_task.py
-- ============================================================
CREATE TABLE IF NOT EXISTS schema_mapping_templates (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name           VARCHAR(255) UNIQUE NOT NULL,
    description    TEXT,
    source_columns JSONB        NOT NULL,
    field_mappings JSONB        NOT NULL,
    created_by     UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_schema_mapping_templates_name ON schema_mapping_templates (name);


-- ============================================================
-- task_schema_mappings
-- Source of truth: backend/src/app/schemas/ingestion_task.py
-- ============================================================
CREATE TABLE IF NOT EXISTS task_schema_mappings (
    id                                    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                               UUID         UNIQUE NOT NULL REFERENCES ingestion_tasks(id) ON DELETE CASCADE,
    template_id                           UUID         REFERENCES schema_mapping_templates(id) ON DELETE SET NULL,
    source_columns                        JSONB        NOT NULL,
    field_mappings                        JSONB        NOT NULL,
    identifier_column                     VARCHAR(255),
    connection_strategy_identifier_column VARCHAR(255),
    dedup_config                          JSONB,
    created_at                            TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                            TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- uploaded_files
-- Source of truth: backend/src/app/schemas/ingestion_task.py
-- ============================================================
CREATE TABLE IF NOT EXISTS uploaded_files (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id           UUID         REFERENCES ingestion_tasks(id) ON DELETE CASCADE,
    run_id            UUID         REFERENCES ingestion_task_runs(id) ON DELETE CASCADE,
    original_filename VARCHAR(255) NOT NULL,
    s3_key            VARCHAR(1024) UNIQUE NOT NULL,
    file_size         INTEGER      NOT NULL,
    content_type      VARCHAR(100) NOT NULL,
    status            VARCHAR(50)  NOT NULL DEFAULT 'pending',
    created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_uploaded_files_task_id ON uploaded_files (task_id);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_run_id  ON uploaded_files (run_id);


-- ============================================================
-- cron_test_runs
-- Source of truth: backend/src/app/schemas/ingestion_task.py
-- ============================================================
CREATE TABLE IF NOT EXISTS cron_test_runs (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       UUID         NOT NULL REFERENCES ingestion_tasks(id) ON DELETE CASCADE,
    executed_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status        VARCHAR(50)  NOT NULL,
    duration_ms   INTEGER,
    error_message TEXT,
    logs          TEXT
);

CREATE INDEX IF NOT EXISTS idx_cron_test_runs_task_id ON cron_test_runs (task_id);


-- ============================================================
-- gmail_credential_status
-- Source of truth: backend/src/app/schemas/ingestion_task.py
-- ============================================================
CREATE TABLE IF NOT EXISTS gmail_credential_status (
    id                       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                  UUID         UNIQUE NOT NULL REFERENCES ingestion_tasks(id) ON DELETE CASCADE,
    status                   VARCHAR(50)  NOT NULL DEFAULT 'pending_auth',
    health_score             INTEGER      NOT NULL DEFAULT 100,
    account_email            VARCHAR(255),
    scopes                   TEXT,
    last_used_at             TIMESTAMP,
    last_auth_attempt_at     TIMESTAMP,
    auth_established_at      TIMESTAMP,
    token_refreshed_at       TIMESTAMP,
    last_error_code          VARCHAR(50),
    last_error_message       TEXT,
    consecutive_failures     INTEGER      NOT NULL DEFAULT 0,
    max_consecutive_failures INTEGER      NOT NULL DEFAULT 3,
    created_at               TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- gmail_credential_audit_log
-- Source of truth: backend/src/app/schemas/ingestion_task.py
-- ============================================================
CREATE TABLE IF NOT EXISTS gmail_credential_audit_log (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       UUID        NOT NULL REFERENCES ingestion_tasks(id) ON DELETE CASCADE,
    event_type    VARCHAR(50) NOT NULL,
    account_email VARCHAR(255),
    error_code    VARCHAR(50),
    error_message TEXT,
    details       JSONB,
    action_by     UUID,
    created_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_gmail_credential_audit_log_task_id ON gmail_credential_audit_log (task_id);


-- ============================================================
-- ingestion_deduplication
-- Source of truth: backend/src/app/schemas/ingestion_task.py
-- ============================================================
CREATE TABLE IF NOT EXISTS ingestion_deduplication (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID         NOT NULL REFERENCES ingestion_task_runs(id) ON DELETE CASCADE,
    row_number          INTEGER      NOT NULL,
    cleaned_identifier  VARCHAR(150) NOT NULL,
    beast_uuid          VARCHAR(64)  NOT NULL,
    is_duplicate        BOOLEAN      NOT NULL DEFAULT FALSE,
    is_connection_match BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_ingestion_dedup_run_id       ON ingestion_deduplication (run_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_dedup_beast_uuid   ON ingestion_deduplication (beast_uuid);
CREATE INDEX IF NOT EXISTS idx_ingestion_dedup_is_duplicate ON ingestion_deduplication (is_duplicate);


-- ============================================================
-- processed_emails
-- Source of truth: backend/src/app/schemas/processed_email.py
-- ============================================================
CREATE TABLE IF NOT EXISTS processed_emails (
    id            SERIAL       PRIMARY KEY,
    message_id    VARCHAR(255) UNIQUE NOT NULL,
    task_id       UUID,
    subject       TEXT,
    sender        TEXT,
    rows_inserted INTEGER      NOT NULL DEFAULT 0,
    rows_updated  INTEGER      NOT NULL DEFAULT 0,
    rows_skipped  INTEGER      NOT NULL DEFAULT 0,
    rows_failed   INTEGER      NOT NULL DEFAULT 0,
    is_success    BOOLEAN      NOT NULL DEFAULT TRUE,
    is_retryable  BOOLEAN      NOT NULL DEFAULT FALSE,
    sent_at       TIMESTAMP,
    processed_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_processed_emails_message_id ON processed_emails (message_id);
CREATE INDEX IF NOT EXISTS idx_processed_emails_task_id    ON processed_emails (task_id);


-- ============================================================
-- failed_email_queue
-- Source of truth: backend/src/app/schemas/failed_email_queue.py
-- ============================================================
CREATE TABLE IF NOT EXISTS failed_email_queue (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id           UUID         NOT NULL REFERENCES ingestion_tasks(id) ON DELETE CASCADE,
    message_id        VARCHAR(255) NOT NULL,
    subject           VARCHAR(255),
    sender            VARCHAR(255),
    failure_reason    VARCHAR(50)  NOT NULL,
    error_message     TEXT,
    error_count       INTEGER      NOT NULL DEFAULT 1,
    last_attempted_at TIMESTAMP,
    next_retry_at     TIMESTAMP,
    created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_failed_email_queue_task_id    ON failed_email_queue (task_id);
CREATE INDEX IF NOT EXISTS idx_failed_email_queue_message_id ON failed_email_queue (message_id);
CREATE INDEX IF NOT EXISTS idx_failed_email_queue_next_retry ON failed_email_queue (next_retry_at);
