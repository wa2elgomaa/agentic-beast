'use client'

import { useState, useEffect } from 'react'
import { AlertCircle, CheckCircle2, Clock, Trash2, RotateCw, ChevronDown, ChevronUp } from 'lucide-react'
import { UUID } from '@/types'
import { APIBaseURL, APIPrefix } from '@/constants/urls'


// Helper to get auth headers
function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
  }
}

interface CredentialStatus {
  task_id: UUID
  status: string
  health_score: number
  account_email?: string
  consecutive_failures: number
  max_consecutive_failures: number
  last_used_at?: string
  auth_established_at?: string
  token_refreshed_at?: string
  last_error_code?: string
  last_error_message?: string
  created_at: string
  updated_at: string
}

interface AuditLogEntry {
  id: string
  task_id: UUID
  event_type: string
  account_email?: string
  error_code?: string
  error_message?: string
  action_by?: UUID
  created_at: string
}

interface AuditLogResponse {
  audit_log: AuditLogEntry[]
  limit: number
  offset: number
  total: number
}

interface GmailCredentialStatusProps {
  taskId: UUID
}

export default function GmailCredentialStatus({ taskId }: GmailCredentialStatusProps) {
  const [status, setStatus] = useState<CredentialStatus | null>(null)
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isAuditExpanded, setIsAuditExpanded] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actionInProgress, setActionInProgress] = useState(false)

  useEffect(() => {
    loadCredentialStatus()
  }, [taskId])

  const loadCredentialStatus = async () => {
    try {
      setIsLoading(true)
      setError(null)

      // Fetch credential status
      const statusRes = await fetch(
        `${APIBaseURL}${APIPrefix}/admin/ingestion/tasks/${taskId}/gmail/credential-status`,
        { headers: getAuthHeaders() }
      )
      if (!statusRes.ok) throw new Error('Failed to fetch credential status')
      const statusData = await statusRes.json()
      setStatus(statusData)

      // Fetch audit log
      const auditRes = await fetch(
        `${APIBaseURL}${APIPrefix}/admin/ingestion/tasks/${taskId}/gmail/audit-log?limit=10`,
        { headers: getAuthHeaders() }
      )
      if (!auditRes.ok) throw new Error('Failed to fetch audit log')
      const auditData: AuditLogResponse = await auditRes.json()
      setAuditLog(auditData.audit_log)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load credential status')
    } finally {
      setIsLoading(false)
    }
  }

  const handleReAuthenticate = async () => {
    try {
      setActionInProgress(true)
      const res = await fetch(
        `${APIBaseURL}${APIPrefix}/admin/ingestion/tasks/${taskId}/gmail/re-authenticate`,
        { method: 'POST', headers: getAuthHeaders() }
      )
      if (!res.ok) throw new Error('Failed to initiate re-authentication')
      const data = await res.json()
      // Redirect to auth URL
      window.location.href = data.auth_url
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to re-authenticate')
      setActionInProgress(false)
    }
  }

  const handleClearCredentials = async () => {
    if (!confirm('Are you sure you want to clear the Gmail credentials? The task will need to be re-authenticated before the next run.')) {
      return
    }

    try {
      setActionInProgress(true)
      const res = await fetch(
        `${APIBaseURL}${APIPrefix}/admin/ingestion/tasks/${taskId}/gmail/credentials`,
        { method: 'DELETE', headers: getAuthHeaders() }
      )
      if (!res.ok) throw new Error('Failed to clear credentials')
      await loadCredentialStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear credentials')
    } finally {
      setActionInProgress(false)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'
      case 'expired':
      case 'invalid':
        return 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200'
      case 'needs_refresh':
        return 'bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200'
      case 'pending_auth':
        return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'active':
        return <CheckCircle2 size={16} className="text-green-600" />
      case 'expired':
      case 'invalid':
        return <AlertCircle size={16} className="text-red-600" />
      case 'needs_refresh':
        return <AlertCircle size={16} className="text-orange-600" />
      default:
        return <Clock size={16} className="text-gray-600" />
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <div className="animate-pulse space-y-4">
            <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/4" />
            <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded" />
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
        <div className="flex gap-3">
          <AlertCircle size={16} className="text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-medium text-red-800 dark:text-red-200">Error Loading Credentials</h3>
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
        </div>
      </div>
    )
  }

  if (!status) {
    return (
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 text-center">
        <p className="text-gray-600 dark:text-gray-400">No credential data available</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Status Card */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Credential Status</h3>
          <div className="flex items-center gap-2">
            {getStatusIcon(status.status)}
            <span className={`px-3 py-1 rounded-full text-sm font-medium capitalize ${getStatusColor(status.status)}`}>
              {status.status}
            </span>
          </div>
        </div>

        {/* Health Score */}
        <div className="mb-6">
          <div className="flex justify-between mb-2">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Health Score</label>
            <span className="text-sm font-mono text-gray-900 dark:text-gray-100">{status.health_score}/100</span>
          </div>
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all ${
                status.health_score >= 75
                  ? 'bg-green-600 dark:bg-green-500'
                  : status.health_score >= 50
                  ? 'bg-yellow-600 dark:bg-yellow-500'
                  : 'bg-red-600 dark:bg-red-500'
              }`}
              style={{ width: `${status.health_score}%` }}
            />
          </div>
        </div>

        {/* Metadata Grid */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div>
            <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Account Email</p>
            <p className="text-sm text-gray-900 dark:text-gray-100 break-all">
              {status.account_email || '-'}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Last Used</p>
            <p className="text-sm text-gray-900 dark:text-gray-100">
              {status.last_used_at ? new Date(status.last_used_at).toLocaleString() : '-'}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Auth Established</p>
            <p className="text-sm text-gray-900 dark:text-gray-100">
              {status.auth_established_at ? new Date(status.auth_established_at).toLocaleString() : '-'}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Token Refreshed</p>
            <p className="text-sm text-gray-900 dark:text-gray-100">
              {status.token_refreshed_at ? new Date(status.token_refreshed_at).toLocaleString() : '-'}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Consecutive Failures</p>
            <p className="text-sm text-gray-900 dark:text-gray-100">
              {status.consecutive_failures}/{status.max_consecutive_failures}
            </p>
          </div>
        </div>

        {/* Error Alert */}
        {status.last_error_code && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
            <div className="flex gap-3">
              <AlertCircle size={16} className="text-red-600 flex-shrink-0 mt-0.5" />
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <p className="font-medium text-red-800 dark:text-red-200">
                    Last Error: <span className="font-mono">{status.last_error_code}</span>
                  </p>
                </div>
                {status.last_error_message && (
                  <p className="text-sm text-red-700 dark:text-red-300">{status.last_error_message}</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3">
          {status.status !== 'active' && (
            <button
              onClick={handleReAuthenticate}
              disabled={actionInProgress}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white rounded-lg transition-colors font-medium text-sm"
            >
              <RotateCw size={16} />
              {actionInProgress ? 'Processing...' : 'Re-authenticate'}
            </button>
          )}
          <button
            onClick={handleClearCredentials}
            disabled={actionInProgress}
            className="flex items-center gap-2 px-4 py-2 bg-red-100 hover:bg-red-200 disabled:bg-red-50 text-red-700 rounded-lg transition-colors font-medium text-sm"
          >
            <Trash2 size={16} />
            Clear Credentials
          </button>
          <button
            onClick={loadCredentialStatus}
            disabled={actionInProgress}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 hover:bg-gray-200 disabled:bg-gray-50 text-gray-700 rounded-lg transition-colors font-medium text-sm"
          >
            <RotateCw size={16} className={actionInProgress ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Audit Log */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setIsAuditExpanded(!isAuditExpanded)}
          className="w-full px-6 py-4 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
        >
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Credential History</h3>
          {isAuditExpanded ? (
            <ChevronUp size={20} className="text-gray-600" />
          ) : (
            <ChevronDown size={20} className="text-gray-600" />
          )}
        </button>

        {isAuditExpanded && (
          <div className="border-t border-gray-200 dark:border-gray-700 p-6 space-y-3">
            {auditLog.length === 0 ? (
              <p className="text-center text-gray-600 dark:text-gray-400 py-4">No audit log entries</p>
            ) : (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {auditLog.map((log) => (
                  <div
                    key={log.id}
                    className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-gray-50 dark:bg-gray-700/30"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <span className="font-medium text-sm text-gray-900 dark:text-gray-100 capitalize">
                        {log.event_type.replace(/_/g, ' ')}
                      </span>
                      <time className="text-xs text-gray-600 dark:text-gray-400">
                        {new Date(log.created_at).toLocaleString()}
                      </time>
                    </div>
                    {log.account_email && (
                      <p className="text-sm text-gray-700 dark:text-gray-300">
                        Email: <span className="font-mono">{log.account_email}</span>
                      </p>
                    )}
                    {log.error_code && (
                      <p className="text-sm text-red-600 dark:text-red-400">
                        Error: <span className="font-mono">{log.error_code}</span>
                      </p>
                    )}
                    {log.error_message && (
                      <p className="text-sm text-gray-700 dark:text-gray-300">{log.error_message}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
