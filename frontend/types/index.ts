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
  published_at?: string
  views: string
}

export interface AnalyticsResponseContent {
  query_type: string
  resolved_context: string
  result_data: AnalyticsResultDataItem[]
  insight_summary: string
  verification: string
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
