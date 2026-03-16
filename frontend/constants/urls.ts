const normalizePrefix = (value: string) => {
	if (!value) return '/api/v1'
	return value.startsWith('/') ? value : `/${value}`
}

const APIPrefix = normalizePrefix(process.env.NEXT_PUBLIC_API_PREFIX || '/api/v1')
export const APIBaseURL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')

export const LOGIN_URL = `${APIPrefix}/users/login`
export const FORGET_PASSWORD_URL = `${APIPrefix}/auth/forgot-password`
export const RESET_PASSWORD_URL = `${APIPrefix}/auth/reset-password`
export const ANALYTICS_URL = `${APIPrefix}/analytics`
export const INGESTION_URL = `${APIPrefix}/ingest/manual`
export const CONVERSATION_URL = `${APIPrefix}/chat/conversations`
export const CHAT_URL = `${APIPrefix}/chat`

export const VALIDATE_RESET_TOKEN_URL = (token: string) => `${APIPrefix}/auth/validate-reset-token/${token}`

export const buildApiUrl = (path: string) => `${APIBaseURL}${path.startsWith('/') ? path : `/${path}`}`