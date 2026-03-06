-- Initialize pgvector extension and create canonical documents table for vectors (384 dim)
-- Run automatically by docker-entrypoint-initdb.d

CREATE EXTENSION IF NOT EXISTS vector;

-- Normalized table holding explicit columns for precise filtering & aggregation
CREATE TABLE IF NOT EXISTS documents (
  id serial PRIMARY KEY,
  sheet_name text NOT NULL,
  row_number integer NOT NULL,
  text text NOT NULL,
  doc_metadata jsonb,
  embedding vector(384),

  -- Profile & Post Information
  published_date date,
  reported_at date,
  profile_name text,
  profile_url text,
  profile_id text,
  post_detail_url text,
  content_id text,
  
  -- Platform & Content Classification
  platform text,
  content_type text,
  media_type text,
  origin_of_the_content text,
  
  -- Content Details
  title text,
  description text,
  author_url text,
  author_id text,
  author_name text,
  content text,
  link_url text,
  view_on_platform text,
  
  -- Engagement Metrics
  organic_interactions integer,
  total_interactions integer,
  total_reactions integer,
  total_comments integer,
  total_shares integer,
  unpublished boolean,
  engagements integer,
  
  -- Reach Metrics
  total_reach integer,
  paid_reach integer,
  organic_reach integer,
  
  -- Impression Metrics
  total_impressions integer,
  paid_impressions integer,
  organic_impressions integer,
  reach_engagement_rate numeric,
  
  -- Video Metrics
  total_likes integer,
  video_length_sec integer,
  video_views integer,
  total_video_view_time_sec integer,
  avg_video_view_time_sec numeric,
  completion_rate numeric,
  
  -- Labels & Categorization
  labels text,
  label_groups text,

  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- For small POC you can skip index creation; for larger datasets consider tuning lists parameter.
CREATE INDEX IF NOT EXISTS documents_embedding_idx ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Uniqueness on the natural key we use to join with `documents`
CREATE UNIQUE INDEX IF NOT EXISTS documents_unique_key ON documents (sheet_name, row_number);

-- Helpful indexes for common filters and sorting
CREATE INDEX IF NOT EXISTS documents_platform_idx ON documents (platform);
CREATE INDEX IF NOT EXISTS documents_media_type_idx ON documents (media_type);
CREATE INDEX IF NOT EXISTS documents_content_type_idx ON documents (content_type);
CREATE INDEX IF NOT EXISTS documents_profile_name_idx ON documents (profile_name);
CREATE INDEX IF NOT EXISTS documents_author_name_idx ON documents (author_name);
CREATE INDEX IF NOT EXISTS documents_published_date_idx ON documents (published_date);
CREATE INDEX IF NOT EXISTS documents_video_views_idx ON documents (video_views);
CREATE INDEX IF NOT EXISTS documents_total_interactions_idx ON documents (total_interactions);
CREATE INDEX IF NOT EXISTS documents_labels_idx ON documents (labels);


-- Create tags table
CREATE TABLE IF NOT EXISTS tags (
    slug VARCHAR PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    variations JSONB,  -- Array of string variations/synonyms
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    embedding vector(384),  -- 384-dim for all-MiniLM-L6-v2
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create index on is_primary for faster queries
CREATE INDEX IF NOT EXISTS idx_tags_is_primary ON tags(is_primary);


-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    hashed_password VARCHAR(255),  -- Nullable for AD users
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    auth_provider VARCHAR(50) NOT NULL DEFAULT 'local',  -- 'local' or 'active_directory'
    ad_username VARCHAR(255),  -- ActiveDirectory username if different from username
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- Create indexes for users
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_auth_provider ON users(auth_provider);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);


-- Create conversations table for chat history
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,  -- Link to users table
    extra_metadata JSONB  -- Additional info like message count, tags, etc.
);

-- Create messages table for conversation history
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    operation VARCHAR(50),  -- e.g., 'query_documents', 'suggest_tags'
    operation_data JSONB,  -- Complete response data including query results
    operation_metadata JSONB,  -- Metadata like timing, model used
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sequence_number INTEGER NOT NULL
);

-- Create indexes for conversations
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);

-- Create indexes for messages
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_sequence ON messages(conversation_id, sequence_number);


-- Create password_reset_tokens table
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    token VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used CHAR(1) DEFAULT 'N' NOT NULL CHECK (used IN ('Y', 'N')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id ON password_reset_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_expires_at ON password_reset_tokens(expires_at);

-- Create summaries table for pre-computed analytics
CREATE TABLE IF NOT EXISTS summaries (
    id SERIAL PRIMARY KEY,
    granularity VARCHAR(20) NOT NULL, -- daily, weekly, monthly
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    platform VARCHAR(50),
    metric_name VARCHAR(100) NOT NULL, -- reach_sum, impressions_avg, etc.
    metric_value NUMERIC NOT NULL,
    metadata TEXT, -- JSON stored as text
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes on summaries table
CREATE INDEX IF NOT EXISTS idx_summaries_granularity ON summaries(granularity);
CREATE INDEX IF NOT EXISTS idx_summaries_period ON summaries(period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_summaries_platform ON summaries(platform);
CREATE INDEX IF NOT EXISTS idx_summaries_metric_name ON summaries(metric_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_summaries_unique ON summaries(granularity, period_start, platform, metric_name);

