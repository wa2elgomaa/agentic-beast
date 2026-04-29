'use client'

import { useEffect, useState } from 'react'
import { APIBaseURL, APIPrefix } from '@/constants/urls'
import { Save, Eye, EyeOff, AlertCircle, CheckCircle, ChevronDown, Loader2 } from 'lucide-react'

// ─── Schema ────────────────────────────────────────────────────────────────────

type FieldType = 'text' | 'password' | 'select' | 'number'

interface FieldDef {
  key: string
  label: string
  type: FieldType
  options?: string[]
  placeholder?: string
  isSecret?: boolean
  description?: string
}

interface TabDef {
  id: string
  label: string
  fields: FieldDef[]
}

const LLM_PROVIDERS = ['openai', 'bedrock', 'ollama', 'strands', 'litert']

function agentFields(prefix: string, agentLabel: string): FieldDef[] {
  return [
    {
      key: `${prefix}_LLM_PROVIDER`,
      label: `${agentLabel} Provider`,
      type: 'select',
      options: LLM_PROVIDERS,
      description: 'LLM backend for this agent',
    },
    { key: `${prefix}_MODEL`, label: `${agentLabel} Model`, type: 'text', placeholder: 'e.g. gpt-4o-mini' },
    { key: `${prefix}_API_KEY`, label: `${agentLabel} API Key`, type: 'password', isSecret: true, placeholder: 'sk-…' },
    { key: `${prefix}_MODEL_BASE_URL`, label: `${agentLabel} Base URL`, type: 'text', placeholder: 'http://localhost:11434 (leave blank for default)' },
  ]
}

const TABS: TabDef[] = [
  {
    id: 'agents',
    label: 'Agents',
    fields: [
      ...agentFields('ANALYTICS', 'Analytics'),
      ...agentFields('CHAT', 'Chat'),
      ...agentFields('CLASSIFY', 'Classification'),
      ...agentFields('MAIN', 'Main / Orchestrator'),
      ...agentFields('SQL', 'SQL'),
      ...agentFields('CODING', 'Coding'),
      ...agentFields('TAGGING', 'Tagging'),
    ],
  },
  {
    id: 'voice',
    label: 'Voice',
    fields: [
      ...agentFields('VOICE', 'Voice LLM'),
      { key: 'VOICE_STT_MODEL', label: 'STT Model', type: 'text', placeholder: 'whisper-1', description: 'Speech-to-text model name' },
      { key: 'VOICE_TTS_VOICE', label: 'TTS Voice', type: 'text', placeholder: 'af_heart', description: 'Kokoro / TTS voice ID' },
      { key: 'VOICE_TTS_SPEED', label: 'TTS Speed', type: 'number', placeholder: '1.1', description: 'Playback speed multiplier (0.5–2.0)' },
    ],
  },
  {
    id: 'aws',
    label: 'AWS / S3',
    fields: [
      { key: 'AWS_REGION', label: 'AWS Region', type: 'text', placeholder: 'us-east-1' },
      { key: 'AWS_ACCESS_KEY_ID', label: 'AWS Access Key ID', type: 'text', isSecret: true },
      { key: 'AWS_SECRET_ACCESS_KEY', label: 'AWS Secret Access Key', type: 'password', isSecret: true },
      { key: 'AWS_S3_BUCKET', label: 'S3 Bucket', type: 'text', placeholder: 'agentic-beast-documents' },
      { key: 'AWS_ENDPOINT_URL', label: 'S3 Endpoint URL', type: 'text', placeholder: 'http://localhost:4566 (LocalStack)' },
    ],
  },
  {
    id: 'gmail',
    label: 'Gmail / OAuth',
    fields: [
      { key: 'GMAIL_OAUTH_CLIENT_ID', label: 'OAuth Client ID', type: 'text', isSecret: true },
      { key: 'GMAIL_OAUTH_CLIENT_SECRET', label: 'OAuth Client Secret', type: 'password', isSecret: true },
      { key: 'GMAIL_OAUTH_TOKEN_URI', label: 'Token URI', type: 'text', placeholder: 'https://oauth2.googleapis.com/token' },
      { key: 'GMAIL_INBOX_QUERY', label: 'Inbox Query', type: 'text', placeholder: 'has:attachment is:unread' },
      { key: 'GMAIL_EMAIL_MONITOR_INTERVAL_SECONDS', label: 'Monitor Interval (sec)', type: 'number', placeholder: '300' },
    ],
  },
  {
    id: 'google',
    label: 'Google Search',
    fields: [
      { key: 'GOOGLE_CSE_API_KEY', label: 'CSE API Key', type: 'password', isSecret: true },
      { key: 'GOOGLE_CSE_ID', label: 'CSE ID', type: 'text' },
      { key: 'GOOGLE_CSE_SITE', label: 'Restrict to Site', type: 'text', placeholder: 'example.com' },
      { key: 'GOOGLE_CSE_DAILY_LIMIT', label: 'Daily Request Limit', type: 'number', placeholder: '100' },
    ],
  },
  {
    id: 'documents',
    label: 'Documents',
    fields: [
      { key: 'DOCUMENT_CHUNK_SIZE', label: 'Chunk Size (tokens)', type: 'number', placeholder: '1000' },
      { key: 'DOCUMENT_CHUNK_OVERLAP', label: 'Chunk Overlap', type: 'number', placeholder: '200' },
      { key: 'DOCUMENT_MAX_FILE_SIZE_MB', label: 'Max File Size (MB)', type: 'number', placeholder: '50' },
      { key: 'EMBEDDING_BATCH_SIZE', label: 'Embedding Batch Size', type: 'number', placeholder: '32' },
      { key: 'EMBEDDING_DEVICE', label: 'Embedding Device', type: 'select', options: ['cpu', 'cuda'] },
    ],
  },
  {
    id: 'security',
    label: 'Security',
    fields: [
      { key: 'JWT_SECRET_KEY', label: 'JWT Secret Key', type: 'password', isSecret: true },
      { key: 'JWT_EXPIRATION_HOURS', label: 'JWT Expiry (hours)', type: 'number', placeholder: '24' },
      { key: 'SETTINGS_ENCRYPTION_KEY', label: 'Settings Encryption Key', type: 'password', isSecret: true, description: 'Fernet key for encrypting secret settings' },
      { key: 'WEBHOOK_SECRET', label: 'Webhook HMAC Secret', type: 'password', isSecret: true },
    ],
  },
  {
    id: 'observability',
    label: 'Observability',
    fields: [
      { key: 'LOG_LEVEL', label: 'Log Level', type: 'select', options: ['DEBUG', 'INFO', 'WARNING', 'ERROR'] },
      { key: 'SENTRY_DSN', label: 'Sentry DSN', type: 'text', isSecret: true },
      { key: 'SENTRY_ENVIRONMENT', label: 'Sentry Environment', type: 'text', placeholder: 'development' },
      { key: 'SENTRY_SAMPLE_RATE', label: 'Sentry Sample Rate', type: 'number', placeholder: '0.1' },
    ],
  },
]

// ─── API helpers ────────────────────────────────────────────────────────────────

interface SettingItem {
  key: string
  value: string
  is_secret: boolean
}

function getAuthHeaders(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  return token
    ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
    : { 'Content-Type': 'application/json' }
}

// ─── Component ─────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const [dbSettings, setDbSettings] = useState<Record<string, SettingItem>>({})
  const [edited, setEdited] = useState<Record<string, string>>({})
  const [revealed, setRevealed] = useState<Record<string, boolean>>({})
  const [activeTab, setActiveTab] = useState('agents')
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${APIBaseURL}${APIPrefix}/admin/settings`, { headers: getAuthHeaders() })
      .then(async r => {
        if (!r.ok) throw new Error(`Failed to load settings (${r.status})`)
        const data = await r.json()
        const map: Record<string, SettingItem> = {}
        for (const item of data.items ?? []) map[item.key] = item
        setDbSettings(map)
      })
      .catch(e => setError(e.message))
      .finally(() => setIsLoading(false))
  }, [])

  const getValue = (field: FieldDef) => {
    if (field.key in edited) return edited[field.key]
    const db = dbSettings[field.key]
    if (!db) return ''
    return db.is_secret ? '' : db.value
  }

  const handleChange = (key: string, value: string) => {
    setEdited(prev => ({ ...prev, [key]: value }))
    setSuccess(null)
  }

  const dirtyKeys = Object.keys(edited)
  const currentTab = TABS.find(t => t.id === activeTab)!

  const handleSave = async () => {
    if (!dirtyKeys.length) return
    setIsSaving(true)
    setError(null)
    const allFields = TABS.flatMap(t => t.fields)
    const items = dirtyKeys.map(key => {
      const schema = allFields.find(f => f.key === key)
      return { key, value: edited[key], is_secret: schema?.isSecret ?? false }
    })
    try {
      const r = await fetch(`${APIBaseURL}${APIPrefix}/admin/settings`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({ items }),
      })
      if (!r.ok) throw new Error(`Save failed (${r.status})`)
      const data = await r.json()
      setDbSettings(prev => {
        const next = { ...prev }
        for (const item of items) next[item.key] = item
        return next
      })
      setEdited({})
      setSuccess(`${data.updated_count ?? items.length} setting(s) saved`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-500">
        <Loader2 className="animate-spin mr-2" size={18} />Loading settings…
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Settings</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Runtime configuration — values are stored in the database and applied without restarting.
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={isSaving || !dirtyKeys.length}
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-lg text-sm font-medium transition-colors"
        >
          {isSaving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          Save{dirtyKeys.length > 0 ? ` (${dirtyKeys.length})` : ''}
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400 text-sm">
          <AlertCircle size={16} />{error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg text-green-700 dark:text-green-400 text-sm">
          <CheckCircle size={16} />{success}
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="-mb-px flex gap-1 flex-wrap">
          {TABS.map(tab => {
            const unsaved = tab.fields.filter(f => f.key in edited).length
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors whitespace-nowrap ${
                  activeTab === tab.id
                    ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                    : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                }`}
              >
                {tab.label}
                {unsaved > 0 && (
                  <span className="ml-1.5 inline-block bg-amber-500 text-white text-[10px] font-bold rounded-full px-1.5 py-0.5 leading-none">{unsaved}</span>
                )}
              </button>
            )
          })}
        </nav>
      </div>

      {/* Fields */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700">
        {currentTab.fields.map(field => {
          const value = getValue(field)
          const isDirty = field.key in edited
          const isStored = field.key in dbSettings
          const isRevealed = revealed[field.key] ?? false
          const isSecret = !!(field.isSecret ?? field.type === 'password')

          return (
            <div key={field.key} className="px-6 py-4 flex items-start gap-4">
              <div className="w-56 shrink-0 pt-1">
                <p className="text-sm font-medium text-gray-900 dark:text-white">{field.label}</p>
                {field.description && <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{field.description}</p>}
                <div className="flex gap-1 mt-1 flex-wrap">
                  {isSecret && <span className="text-[10px] bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 px-1.5 py-0.5 rounded font-medium">secret</span>}
                  {isStored && !isDirty && <span className="text-[10px] bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 px-1.5 py-0.5 rounded font-medium">saved</span>}
                  {isDirty && <span className="text-[10px] bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 px-1.5 py-0.5 rounded font-medium">unsaved</span>}
                </div>
              </div>

              <div className="flex-1 min-w-0">
                {field.type === 'select' ? (
                  <div className="relative">
                    <select
                      value={value}
                      onChange={e => handleChange(field.key, e.target.value)}
                      className="w-full appearance-none bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent pr-8"
                    >
                      <option value="">— select —</option>
                      {field.options!.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                    <ChevronDown size={14} className="absolute right-2 top-3 text-gray-400 pointer-events-none" />
                  </div>
                ) : (
                  <div className="relative">
                    <input
                      type={isSecret && !isRevealed ? 'password' : field.type === 'number' ? 'number' : 'text'}
                      value={value}
                      onChange={e => handleChange(field.key, e.target.value)}
                      placeholder={field.placeholder ?? (isStored && isSecret ? '(encrypted — enter new value to change)' : undefined)}
                      className="w-full bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono pr-9"
                    />
                    {isSecret && (
                      <button
                        type="button"
                        onClick={() => setRevealed(p => ({ ...p, [field.key]: !isRevealed }))}
                        className="absolute right-2 top-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                      >
                        {isRevealed ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}