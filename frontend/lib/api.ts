import { APIBaseURL, APIPrefix, CHAT_URL, CHAT_STREAM_URL, VOICE_CHAT_URL, CONVERSATION_URL, MEDIA_CHAT_URL, REALTIME_CHAT_URL, buildApiUrl, buildWebSocketUrl } from '@/constants/urls'
import {
  ChatMediaRequestPayload,
  QueryResponse,
  OrchestratorResponse,
  OperationType,
  AnalyticsResponseContent,
  AnalyticsResultDataItem,
  Conversation,
  ConversationDetail,
  ConversationListResponse,
  IngestionTask,
  IngestionTaskRun,
  SchemaMappingTemplate,
  TaskSchemaMapping,
  SchemaDetectResponse,
  IngestionTaskCreateInput,
  IngestionTaskUpdateInput,
  SchemaMappingUpdateInput,
  SaveAsTemplateInput,
  GmailAuthUrlRequest,
  GmailAuthUrlResponse,
  GmailExchangeCodeRequest,
  GmailExchangeCodeResponse,
  PreviewEmail,
  PreviewEmailsResponse,
} from '@/types'

// Helper to get auth headers
function getAuthHeaders(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
  }
}

export class GmailCredentialExpiredError extends Error {
  reauth_url: string
  task_id: string
  constructor(reauth_url: string, task_id: string) {
    super('Gmail credentials have expired. Re-authorization is required.')
    this.name = 'GmailCredentialExpiredError'
    this.reauth_url = reauth_url
    this.task_id = task_id
  }
}

export function getAccessToken(): string | null {
  return typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
}

/** Call the refresh endpoint and update localStorage with the new token.
 *  Returns the new access token, or throws if the refresh fails. */
export async function refreshToken(): Promise<string> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/users/refresh`), {
    method: 'POST',
    headers: getAuthHeaders(),
  })
  if (!response.ok) {
    throw new Error(`Token refresh failed: ${response.status}`)
  }
  const data = await response.json()
  const newToken: string = data.access_token
  if (typeof window !== 'undefined') {
    localStorage.setItem('access_token', newToken)
  }
  return newToken
}

/** fetch() wrapper that automatically retries once with a refreshed token on 401. */
export async function fetchWithAuth(input: string, init: RequestInit = {}): Promise<Response> {
  const first = await fetch(input, { ...init, headers: { ...getAuthHeaders(), ...(init.headers as Record<string, string> ?? {}) } })
  if (first.status !== 401) return first

  try {
    await refreshToken()
  } catch {
    return first   // surfacing original 401 if refresh itself fails
  }

  return fetch(input, { ...init, headers: { ...getAuthHeaders(), ...(init.headers as Record<string, string> ?? {}) } })
}

export interface VoiceTurnResult {
  transcript: string | null
  assistant_text: string
  audio_base64: string | null
  audio_sample_rate: number
  conversation_id: string | null
}

/** Submit a base64-encoded audio clip and get back transcript + assistant text + TTS audio. */
export async function submitVoiceTurn(
  audioBase64: string,
  conversationId?: string | null,
): Promise<VoiceTurnResult> {
  const response = await fetchWithAuth(buildApiUrl(VOICE_CHAT_URL), {
    method: 'POST',
    body: JSON.stringify({ audio: audioBase64, conversation_id: conversationId ?? null }),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(err.detail || `Voice turn failed: HTTP ${response.status}`)
  }
  return response.json()
}

export function buildChatStreamWsUrl(token: string, conversationId?: string | null): string {
  const url = new URL(buildWebSocketUrl(CHAT_STREAM_URL))
  url.searchParams.set('token', token)
  if (conversationId) {
    url.searchParams.set('conversation_id', conversationId)
  }
  return url.toString()
}

export function buildRealtimeChatWsUrl(token: string, conversationId?: string | null): string {
  const url = new URL(buildWebSocketUrl(REALTIME_CHAT_URL))
  url.searchParams.set('token', token)
  if (conversationId) {
    url.searchParams.set('conversation_id', conversationId)
  }
  return url.toString()
}

function tryParseJsonContent(value: unknown): Record<string, any> | null {
  if (typeof value === 'object' && value !== null) {
    return value as Record<string, any>
  }

  if (typeof value !== 'string') {
    return null
  }

  const trimmed = value.trim()
  if (!trimmed) {
    return null
  }

  // Handles normal JSON and double-encoded/escaped JSON strings.
  const candidates = [trimmed]
  if ((trimmed.startsWith('"{') && trimmed.endsWith('}"')) || (trimmed.startsWith('"[') && trimmed.endsWith(']"'))) {
    candidates.push(trimmed.slice(1, -1))
  }

  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate)
      if (typeof parsed === 'string') {
        try {
          const nested = JSON.parse(parsed)
          if (typeof nested === 'object' && nested !== null) {
            return nested as Record<string, any>
          }
        } catch {
          // Ignore nested parse failure and continue.
        }
      }

      if (typeof parsed === 'object' && parsed !== null) {
        return parsed as Record<string, any>
      }
    } catch {
      // Try next candidate.
    }
  }

  // Last fallback: attempt to parse the first balanced JSON object in the payload.
  // This helps when upstream appends extra characters around otherwise valid JSON.
  const balancedObject = extractBalancedJsonObject(trimmed)
  if (balancedObject) {
    try {
      const parsed = JSON.parse(balancedObject)
      if (typeof parsed === 'object' && parsed !== null) {
        return parsed as Record<string, any>
      }
    } catch {
      // Give up and return null below.
    }
  }

  return null
}

function extractBalancedJsonObject(value: string): string | null {
  const start = value.indexOf('{')
  if (start === -1) {
    return null
  }

  let depth = 0
  let inString = false
  let escape = false

  for (let i = start; i < value.length; i += 1) {
    const char = value[i]

    if (escape) {
      escape = false
      continue
    }

    if (char === '\\') {
      escape = true
      continue
    }

    if (char === '"') {
      inString = !inString
      continue
    }

    if (inString) {
      continue
    }

    if (char === '{') {
      depth += 1
    } else if (char === '}') {
      depth -= 1
      if (depth === 0) {
        return value.slice(start, i + 1)
      }
    }
  }

  return null
}

function mapQueryTypeToOperation(queryType?: string): OperationType {
  switch ((queryType || '').toLowerCase()) {
    case 'analytics':
    case 'query_documents':
      return 'query_documents'
    case 'tag_suggestion':
    case 'suggest_tags_for_article_id':
      return 'suggest_tags_for_article_id'
    case 'suggest_tags_for_article_body':
      return 'suggest_tags_for_article_body'
    default:
      return 'query_documents'
  }
}

function normalizeAnalyticsResultData(resultData: unknown[]): AnalyticsResultDataItem[] {
  return resultData.map((item) => {
    const row = (item || {}) as Record<string, unknown>

    const publishedRaw = row.published_at
    const publishedAt =
      typeof publishedRaw === 'string' &&
      publishedRaw.trim() !== '' &&
      publishedRaw.trim().toLowerCase() !== 'n/a'
        ? publishedRaw
        : undefined

    const normalized: AnalyticsResultDataItem = {
      platform: String(row.platform ?? ''),
      content: String(row.content ?? ''),
      title: String(row.title ?? ''),
      description: String(row.description ?? ''),
      view_url: String(row.view_url ?? row.view_on_platform ?? ''),
      views: String(row.views ?? ''),
    }

    if (publishedAt) {
      normalized.published_at = publishedAt
    }

    return normalized
  })
}

function toAnalyticsContent(parsedContent: Record<string, any> | null): AnalyticsResponseContent | undefined {
  if (!parsedContent) return undefined

  const {
    query_type: queryType,
    resolved_context: resolvedContext,
    result_data: resultData,
    insight_summary: insightSummary,
    verification,
  } = parsedContent

  if (
    typeof queryType !== 'string' ||
    typeof resolvedContext !== 'string' ||
    !Array.isArray(resultData) ||
    typeof insightSummary !== 'string' ||
    typeof verification !== 'string'
  ) {
    return undefined
  }

  return {
    query_type: queryType,
    resolved_context: resolvedContext,
    result_data: resultData,
    insight_summary: insightSummary,
    verification,
  }
}

function toOrchestratorResponse(payload: any): OrchestratorResponse {
  const rawContent = payload?.message?.content
  const parsedContent = tryParseJsonContent(rawContent)
  const analyticsContent = toAnalyticsContent(parsedContent)
  const queryType = analyticsContent?.query_type || parsedContent?.query_type
  const operation = mapQueryTypeToOperation(queryType || payload?.message?.metadata?.operation)

  const isErrorPayload =
    parsedContent !== null &&
    typeof parsedContent === 'object' &&
    typeof parsedContent.error === 'string'

  const answer = isErrorPayload
    ? (typeof parsedContent!.message === 'string'
        ? parsedContent!.message
        : 'Something went wrong. Please try again.')
    : (analyticsContent?.insight_summary ||
        parsedContent?.insight_summary ||
        parsedContent?.answer ||
        (typeof rawContent === 'string' ? rawContent : JSON.stringify(rawContent ?? '')))

  const normalizedResults =
    analyticsContent?.result_data ||
    parsedContent?.result_data ||
    parsedContent?.results ||
    (Array.isArray(payload?.message?.metadata?.raw_rows) ? payload.message.metadata.raw_rows : undefined)

  const note =
    analyticsContent?.verification ||
    analyticsContent?.resolved_context ||
    parsedContent?.verification ||
    parsedContent?.resolved_context ||
    undefined

  return {
    success: !isErrorPayload && payload?.status === 'success',
    operation,
    data: {
      answer,
      results: normalizedResults,
      note,
      analytics_content: analyticsContent,
      query_type: queryType,
      resolved_context: analyticsContent?.resolved_context || parsedContent?.resolved_context,
      verification: analyticsContent?.verification || parsedContent?.verification,
      conversation_id: payload?.conversation_id,
      user_transcript:
        typeof payload?.user_message?.content === 'string'
          ? payload.user_message.content
          : undefined,
      chart_b64: payload?.message?.metadata?.chart_b64 || parsedContent?.chart_b64 || undefined,
      code_output: payload?.message?.metadata?.code_output || parsedContent?.code_output || undefined,
      generated_sql: payload?.message?.metadata?.generated_sql || parsedContent?.generated_sql || undefined,
    },
    metadata: {
      source: parsedContent ? 'computed' : undefined,
      query_type: queryType,
      citations: payload?.message?.metadata?.citations,
      agents_involved: payload?.message?.metadata?.agents_involved,
      chart_b64: payload?.message?.metadata?.chart_b64,
      code_output: payload?.message?.metadata?.code_output,
      generated_sql: payload?.message?.metadata?.generated_sql,
      input_type: payload?.user_message?.metadata?.input_type,
      transcript_source: payload?.user_message?.metadata?.transcript_source,
      transcript_confidence: payload?.user_message?.metadata?.transcript_confidence,
      has_visual_context: payload?.user_message?.metadata?.has_visual_context,
      media_duration_ms: payload?.user_message?.metadata?.media_duration_ms,
      modality_pipeline: payload?.user_message?.metadata?.modality_pipeline,
    },
  }
}

// ============================================================================
// New Orchestrator API (Unified Interface)
// ============================================================================

export async function chat(
  query: string,
  conversationId?: string | null,
  _includeContext: boolean = true,
  _contextWindow: number = 2,
  _preGeneratedSql?: string
): Promise<OrchestratorResponse> {
  const response = await fetch(buildApiUrl(CHAT_URL), {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      message: query,
      conversation_id: conversationId,
    }),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return toOrchestratorResponse(await response.json())
}

export async function chatMedia(payload: ChatMediaRequestPayload): Promise<OrchestratorResponse> {
  const response = await fetch(buildApiUrl(MEDIA_CHAT_URL), {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return toOrchestratorResponse(await response.json())
}

// ============================================================================
// Conversation API
// ============================================================================

export async function createConversation(title?: string): Promise<Conversation> {
  const response = await fetch(buildApiUrl(CONVERSATION_URL), {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ title }),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function getConversations(
  page: number = 1,
  pageSize: number = 20
): Promise<ConversationListResponse> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  const response = await fetch(buildApiUrl(CONVERSATION_URL), {
    headers: {
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    }
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
  const payload = await response.json()
  const conversations = payload?.conversations ?? []
  const total = payload?.total_count ?? conversations.length

  return {
    conversations,
    total,
    page,
    page_size: pageSize,
    has_more: false,
  }
}

export async function getConversation(
  id: string,
  page: number = 1,
  pageSize: number = 50
): Promise<ConversationDetail> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  const response = await fetch(buildApiUrl(`${CONVERSATION_URL}/${id}/messages`), {
    headers: {
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    }
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
  const payload = await response.json()
  const messages = payload?.messages ?? []

  return {
    ...payload,
    messages,
    has_more: false,
    total_messages: messages.length,
  }
}

export async function deleteConversation(id: string): Promise<void> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  const response = await fetch(buildApiUrl(`${CONVERSATION_URL}/${id}`), {
    method: 'DELETE',
    headers: {
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    }
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
}

export async function updateConversationTitle(id: string, title: string): Promise<Conversation> {
  const response = await fetch(buildApiUrl(`${CONVERSATION_URL}/${id}/title`), {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ title }),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// ============================================================================
// Legacy API (for backward compatibility)
// ============================================================================

export async function queryContent(question: string, topK?: number): Promise<QueryResponse> {
  const response = await fetch(`${APIBaseURL}/search/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ question, top_k: topK }),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// ============================================================================
// CMS Update API
// ============================================================================

export async function saveTags(articleId: string, tags: { slug: string; text: string }[]): Promise<{ success: boolean; message: string }> {
  const response = await fetch(`${APIBaseURL}/cms/update/${articleId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      taxonomy: {
        tags
      }
    }),
  })

  if (!response.ok) {

    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  const result = await response.json()
  return { success: result.data?.success || false, message: result.data?.message || 'Tag saved successfully' }
}

export function formatNumber(val: any): string {
  if(isNaN(Number(val))) return String(val)
  const num = Number(val)
  if (num == null) return 'N/A'
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toLocaleString()
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return dateStr
  }
}

export function exportToCSV(results?: any[], filename: string = 'analytics') {
  if (!results || results.length === 0) return
  const headers = Object.keys(results[0] || {}).map(key => key.replace(/_/g, ' ').toUpperCase())
  const rows = results.map(r => Object.values(r))

  const csv = [
    headers.join(','),
    ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
  ].join('\n')

  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${filename}-${new Date().toISOString().split('T')[0]}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ============================================================================
// Ingestion Module API
// ============================================================================

// Ingestion Tasks
export async function getIngestionTasks(adaptorType?: string, status?: string): Promise<IngestionTask[]> {
  const params = new URLSearchParams()
  if (adaptorType) params.append('adaptor_type', adaptorType)
  if (status) params.append('status', status)
  
  const url = params.toString() 
    ? `${buildApiUrl(`${APIPrefix}/admin/ingestion/tasks`)}?${params.toString()}`
    : buildApiUrl(`${APIPrefix}/admin/ingestion/tasks`)

  const response = await fetch(url, {
    headers: getAuthHeaders(),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function getIngestionTask(taskId: string): Promise<IngestionTask> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}`), {
    headers: getAuthHeaders(),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function createIngestionTask(data: IngestionTaskCreateInput): Promise<IngestionTask> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks`), {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function updateIngestionTask(taskId: string, data: IngestionTaskUpdateInput): Promise<IngestionTask> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}`), {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function deleteIngestionTask(taskId: string): Promise<void> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}`), {
    method: 'DELETE',
    headers: getAuthHeaders(),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
}

export async function triggerIngestionTaskRun(taskId: string): Promise<IngestionTaskRun> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}/run`), {
    method: 'POST',
    headers: getAuthHeaders(),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// Ingestion Task Runs
export async function getIngestionTaskRuns(taskId: string): Promise<IngestionTaskRun[]> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}/runs`), {
    headers: getAuthHeaders(),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function getIngestionTaskRunDetail(taskId: string, runId: string): Promise<IngestionTaskRun> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}/runs/${runId}`), {
    headers: getAuthHeaders(),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function cancelIngestionTaskRun(taskId: string, runId: string): Promise<IngestionTaskRun> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}/runs/${runId}/cancel`), {
    method: 'POST',
    headers: getAuthHeaders(),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function previewEmailsForTask(taskId: string, limit: number = 10, pageToken?: string | null): Promise<PreviewEmailsResponse> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (pageToken) {
    params.append('page_token', pageToken)
  }
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}/preview-emails?${params.toString()}`), {
    method: 'GET',
    headers: getAuthHeaders(),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    if (response.status === 401 && error.detail?.error === 'credential_expired' && error.detail?.reauth_url) {
      throw new GmailCredentialExpiredError(error.detail.reauth_url, error.detail.task_id)
    }
    throw new Error(typeof error.detail === 'string' ? error.detail : `HTTP ${response.status}`)
  }

  return response.json()
}

export async function runTaskWithSelections(taskId: string, selectedMessageIds: string[]): Promise<IngestionTaskRun> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}/run-with-selections`), {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ selected_message_ids: selectedMessageIds }),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    if (response.status === 401 && error.detail?.error === 'credential_expired' && error.detail?.reauth_url) {
      throw new GmailCredentialExpiredError(error.detail.reauth_url, error.detail.task_id)
    }
    throw new Error(typeof error.detail === 'string' ? error.detail : `HTTP ${response.status}`)
  }

  return response.json()
}

// Schema Mapping
export async function detectColumnsFromFile(file: File): Promise<SchemaDetectResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/detect-columns`), {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${typeof window !== 'undefined' ? localStorage.getItem('access_token') : null}`,
    },
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function getTaskSchemaMapping(taskId: string): Promise<TaskSchemaMapping | null> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}/schema-mapping`), {
    headers: getAuthHeaders(),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  // Backend returns null (200 with null body) when no mapping configured yet
  const data = await response.json()
  return data ?? null
}

export async function updateTaskSchemaMapping(taskId: string, data: SchemaMappingUpdateInput): Promise<TaskSchemaMapping> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}/schema-mapping`), {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function saveSchemaAsTemplate(taskId: string, data: SaveAsTemplateInput): Promise<SchemaMappingTemplate> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}/schema-mapping/save-template`), {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// Schema Mapping Templates
export async function getSchemaMappingTemplates(): Promise<SchemaMappingTemplate[]> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/schema-templates`), {
    headers: getAuthHeaders(),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function getSchemaMappingTemplate(templateId: string): Promise<SchemaMappingTemplate> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/schema-templates/${templateId}`), {
    headers: getAuthHeaders(),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function createSchemaMappingTemplate(data: Omit<SchemaMappingTemplate, 'id' | 'created_by' | 'created_at' | 'updated_at'>): Promise<SchemaMappingTemplate> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/schema-templates`), {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function updateSchemaMappingTemplate(templateId: string, data: Partial<SchemaMappingTemplate>): Promise<SchemaMappingTemplate> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/schema-templates/${templateId}`), {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function deleteSchemaMappingTemplate(templateId: string): Promise<void> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/schema-templates/${templateId}`), {
    method: 'DELETE',
    headers: getAuthHeaders(),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
}

// File Upload
export async function uploadFileForTask(taskId: string, file: File): Promise<any> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}/upload`), {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${typeof window !== 'undefined' ? localStorage.getItem('access_token') : null}`,
    },
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// Gmail OAuth for task-scoped account linking
export async function getGmailTaskAuthUrl(taskId: string, data: GmailAuthUrlRequest): Promise<GmailAuthUrlResponse> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}/gmail/auth-url`), {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function exchangeGmailTaskCode(taskId: string, data: GmailExchangeCodeRequest): Promise<GmailExchangeCodeResponse> {
  const response = await fetch(buildApiUrl(`${APIPrefix}/admin/ingestion/tasks/${taskId}/gmail/exchange-code`), {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}
