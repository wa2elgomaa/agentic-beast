const normalizePrefix = (value: string) => {
	if (!value) return '/api/v1'
	return value.startsWith('/') ? value : `/${value}`
}

export const APIPrefix = normalizePrefix(process.env.NEXT_PUBLIC_API_PREFIX || '/api/v1')
export const APIBaseURL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')

export const LOGIN_URL = `${APIPrefix}/users/login`
export const FORGET_PASSWORD_URL = `${APIPrefix}/auth/forgot-password`
export const RESET_PASSWORD_URL = `${APIPrefix}/auth/reset-password`
export const ANALYTICS_URL = `${APIPrefix}/analytics`
export const INGESTION_URL = `${APIPrefix}/ingest/manual`
export const CONVERSATION_URL = `${APIPrefix}/chat/conversations`
export const CHAT_URL = `${APIPrefix}/chat`
export const MEDIA_CHAT_URL = `${APIPrefix}/chat/media`
export const REALTIME_CHAT_URL = `${APIPrefix}/chat/realtime/ws`

export const VALIDATE_RESET_TOKEN_URL = (token: string) => `${APIPrefix}/auth/validate-reset-token/${token}`

export const ADMIN_INGESTION_URL = `${APIPrefix}/admin/ingestion`
export const ADMIN_INGESTION_TASKS_URL = `${ADMIN_INGESTION_URL}/tasks`

export const buildApiUrl = (path: string) => `${APIBaseURL}${path.startsWith('/') ? path : `/${path}`}`

export const buildWebSocketUrl = (path: string) => {
	const base = APIBaseURL.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')
	return `${base}${path.startsWith('/') ? path : `/${path}`}`
}