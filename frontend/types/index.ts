// ============================================================================
// Operation Types
// ============================================================================

export type OperationType = 
  | 'query_documents'
  | 'suggest_tags_for_article_id'
  | 'suggest_tags_for_article_body'
  | 'cache_get'
  | 'cache_put'
  | 'log_analytics'

// ============================================================================
// Tag Suggestion Types
// ============================================================================

export interface TagSuggestion {
  slug: string
  name: string
  is_primary: boolean
  score: number
  reason?: string
}

// ============================================================================
// Query Suggestion Types
// ============================================================================

export interface QuerySuggestion {
  question: string
  sql: string
}

// ============================================================================
// Analytics Structured Content Types
// ============================================================================

export interface AnalyticsResultDataItem {
  platform: string
  content: string
  title: string
  description?: string
  view_url?: string
  published_at?: string
  views: string
}

export interface AnalyticsResponseContent {
  query_type: string
  resolved_context: string
  result_data: AnalyticsResultDataItem[]
  insight_summary: string
  verification: string
  chart_b64?: string
  code_output?: string
  generated_sql?: string
}

// ============================================================================
// Chat API Metadata
// ============================================================================

export interface ChatMessageMetadata {
  operation?: string
  citations?: Record<string, any>[]
  agents_involved?: string[]
  chart_b64?: string
  code_output?: string
  generated_sql?: string
}

// ============================================================================
// Orchestrator Response Types
// ============================================================================

export interface OrchestratorResponse {
  success: boolean
  operation: OperationType
  data: {
    conversation_id?: string
    analytics_content?: AnalyticsResponseContent
    // For query_documents
    answer?: string
    refined_query?: string
    original_query?: string
    sql?: string
    explanation?: string
    note?: string
    suggestions?: QuerySuggestion[]  // AI-generated follow-up suggestions
    
    // For analytics/tag displays
    results?: AnalyticsResultDataItem[] | TagSuggestion[]
    count?: number
    article_id?: string
    
    // For cache operations
    value?: any
    key?: string
    cached?: boolean
    
    // For analytics
    logged?: boolean
    event_type?: string
    
    // Generic error
    error?: string
    
    // Allow additional fields
    [key: string]: any
  }
  metadata: {
    duration_ms?: number
    source?: 'cache' | 'computed'
    refinement_type?: string
    found?: boolean
    ttl?: number
    event_type?: string
    [key: string]: any
  }
}

// ============================================================================
// Message Types
// ============================================================================

export interface Message {
  id: string
  conversation_id?: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  
  // Chat API metadata (chart, code output, SQL from code interpreter)
  metadata?: ChatMessageMetadata

  // Operation-specific data (camelCase for frontend)
  operation?: OperationType
  operationData?: OrchestratorResponse['data']
  operationMetadata?: OrchestratorResponse['metadata']
  
  // API response fields (snake_case from backend)
  operation_data?: OrchestratorResponse['data']
  operation_metadata?: OrchestratorResponse['metadata']
  
  // For database-stored messages
  sequence_number?: number
  created_at?: string
  
  // Legacy support (deprecated)
  aggregation?: Aggregation[]
  results?: ContentResult[]
  
  isLoading?: boolean
}

// ============================================================================
// Conversation Types
// ============================================================================

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
  last_message_preview?: string
}

export interface ConversationDetail {
  id: string
  title: string
  created_at: string
  updated_at: string
  messages: Message[]
  has_more: boolean
  total_messages: number
}

export interface ConversationListResponse {
  conversations: Conversation[]
  total: number
  page: number
  page_size: number
  has_more?: boolean
}

// ============================================================================
// Legacy Content Result Types (for backward compatibility)
// ============================================================================

export interface ContentResult {
  row_number?: number
  date?: string
  profile_name?: string
  profile_url?: string
  profile_id?: string
  post_detail_url?: string
  content_id?: string
  platform?: string
  content_type?: string
  media_type?: string
  origin_of_the_content?: string
  title?: string
  description?: string
  author_url?: string
  author_id?: string
  author_name?: string
  content?: string
  link_url?: string
  view_on_platform?: string
  organic_interactions?: number
  total_interactions?: number
  total_reactions?: number
  total_comments?: number
  total_shares?: number
  unpublished?: boolean
  engagements?: number
  total_reach?: number
  paid_reach?: number
  organic_reach?: number
  total_impressions?: number
  paid_impressions?: number
  organic_impressions?: number
  reach_engagement_rate?: number
  total_likes?: number
  video_length_sec?: number
  video_views?: number
  total_video_view_time_sec?: number
  avg_video_view_time_sec?: number
  completion_rate?: number
  labels?: string
  label_groups?: string
}

// ============================================================================
// Legacy Aggregation Types (for backward compatibility)
// ============================================================================

export type Aggregation = {
  "_aggregated_total": number,
  "_aggregated_count": number,
  "_aggregation_type": string,
  "_aggregation_metric": string
}

export interface AggregationResult {
  "answer": string
  "data": Aggregation[] | ContentResult[],
  "count": number,
  "is_aggregated": boolean
}

export interface QueryResponse {
  answer: string
  question: string
  count: number
  results: AggregationResult
}

export interface DashboardStats {
  totalResults: number
  totalViews: number
  totalEngagement: number
  avgCompletion: number
}

// ============================================================================
// Ingestion Module Types
// ============================================================================

export type AdaptorType = 'gmail' | 'webhook' | 'manual'
export type ScheduleType = 'none' | 'once' | 'recurring'
export type TaskStatus = 'active' | 'paused' | 'disabled'
export type RunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'partial' | 'canceled'

export interface IngestionTask {
  id: string
  name: string
  adaptor_type: AdaptorType
  adaptor_config: Record<string, any>
  schedule_type: ScheduleType
  cron_expression?: string
  run_at?: string
  status: TaskStatus
  created_by: string
  created_at: string
  updated_at: string
}

export interface IngestionTaskRun {
  id: string
  task_id: string
  started_at?: string
  completed_at?: string
  status: RunStatus
  rows_inserted: number
  rows_updated: number
  rows_failed: number
  error_message?: string
  error_type?: string  // data_error | auth_error | network_error
  error_code?: string  // invalid_grant, unauthorized, etc.
  run_metadata?: Record<string, any>
  created_at: string
}

export interface SchemaMappingTemplate {
  id: string
  name: string
  description?: string
  source_columns: string[]
  field_mappings: Record<string, string>
  created_by: string
  created_at: string
  updated_at: string
}

export interface TaskSchemaMapping {
  id: string
  task_id: string
  template_id?: string
  source_columns: string[]
  field_mappings: Record<string, string>
  identifier_column?: string
  dedup_config?: Record<string, any>
  created_at: string
  updated_at: string
}

export interface UploadedFile {
  id: string
  task_id?: string
  run_id?: string
  original_filename: string
  s3_key: string
  file_size: number
  content_type: string
  status: string
  created_at: string
}

export interface SchemaDetectResponse {
  source_columns: string[]
  auto_mapped: Record<string, string>
  unmatched: string[]
}

export interface IngestionTaskCreateInput {
  name: string
  adaptor_type: AdaptorType
  adaptor_config: Record<string, any>
  schedule_type: ScheduleType
  cron_expression?: string
  run_at?: string
  status: TaskStatus
}

export interface IngestionTaskUpdateInput {
  name?: string
  adaptor_config?: Record<string, any>
  schedule_type?: ScheduleType
  cron_expression?: string
  run_at?: string
  status?: TaskStatus
}

export interface SchemaMappingUpdateInput {
  source_columns: string[]
  field_mappings: Record<string, string>
  identifier_column?: string
  template_id?: string
  dedup_config?: Record<string, any>
}

export interface SaveAsTemplateInput {
  name: string
  description?: string
}

export interface WebhookPayload {
  [key: string]: any
}

export interface GmailAuthUrlRequest {
  redirect_uri: string
}

export interface GmailAuthUrlResponse {
  auth_url: string
  state: string
}

export interface GmailExchangeCodeRequest {
  code: string
  state: string
  redirect_uri: string
}

export interface GmailExchangeCodeResponse {
  task_id: string
  connected_email: string
  message: string
}
