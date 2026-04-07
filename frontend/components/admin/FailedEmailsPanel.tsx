'use client'

import { useState } from 'react'
import { AlertCircle, RefreshCw, Trash2, Clock, Mail, User } from 'lucide-react'
import { FailedEmail, FailedEmailListResponse } from '@/types'

interface FailedEmailsPanelProps {
  taskId: string
  initialData?: FailedEmailListResponse
  onRefresh?: () => void
}

const getFailureReasonBadge = (reason: string) => {
  const badges: Record<string, { bg: string; text: string; label: string }> = {
    auth_error: {
      bg: 'bg-red-100 dark:bg-red-900',
      text: 'text-red-800 dark:text-red-200',
      label: 'Auth Error',
    },
    extraction_error: {
      bg: 'bg-yellow-100 dark:bg-yellow-900',
      text: 'text-yellow-800 dark:text-yellow-200',
      label: 'Extraction Error',
    },
    row_error: {
      bg: 'bg-orange-100 dark:bg-orange-900',
      text: 'text-orange-800 dark:text-orange-200',
      label: 'Row Error',
    },
    file_error: {
      bg: 'bg-purple-100 dark:bg-purple-900',
      text: 'text-purple-800 dark:text-purple-200',
      label: 'File Error',
    },
  }

  const badge = badges[reason] || badges.row_error
  return badge
}

const formatDate = (dateString?: string) => {
  if (!dateString) return '-'
  const date = new Date(dateString)
  return date.toLocaleString()
}

const isReadyForRetry = (nextRetryAt?: string) => {
  if (!nextRetryAt) return false
  return new Date(nextRetryAt) <= new Date()
}

export default function FailedEmailsPanel({
  taskId,
  initialData,
  onRefresh,
}: FailedEmailsPanelProps) {
  const [data, setData] = useState<FailedEmailListResponse | null>(initialData || null)
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadFailedEmails = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(
        `/api/admin/ingestion/tasks/${taskId}/failed-emails`
      )
      if (!response.ok) {
        throw new Error('Failed to load failed emails')
      }
      const newData = await response.json()
      setData(newData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const handleRetry = async (emailId: string) => {
    setActionLoading(emailId)
    try {
      const response = await fetch(
        `/api/admin/ingestion/tasks/${taskId}/failed-emails/${emailId}/retry`,
        { method: 'POST' }
      )
      if (!response.ok) {
        throw new Error('Failed to schedule retry')
      }
      // Refresh the list
      await loadFailedEmails()
      onRefresh?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setActionLoading(null)
    }
  }

  const handleRemove = async (emailId: string) => {
    if (!confirm('Are you sure you want to remove this email from the retry queue?')) {
      return
    }
    setActionLoading(emailId)
    try {
      const response = await fetch(
        `/api/admin/ingestion/tasks/${taskId}/failed-emails/${emailId}`,
        { method: 'DELETE' }
      )
      if (!response.ok) {
        throw new Error('Failed to remove email')
      }
      // Refresh the list
      await loadFailedEmails()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setActionLoading(null)
    }
  }

  if (!data && !initialData) {
    return (
      <div className="space-y-4">
        <button
          onClick={loadFailedEmails}
          disabled={loading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-lg transition"
        >
          {loading ? 'Loading...' : 'Load Failed Emails'}
        </button>
      </div>
    )
  }

  const emails = data?.failed_emails || []

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-800 dark:text-red-200">
          <p className="text-sm font-medium">{error}</p>
        </div>
      )}

      {/* Stats Section */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase font-medium">
            Total Failed
          </p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {data?.total || 0}
          </p>
        </div>
        <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
          <p className="text-xs text-green-700 dark:text-green-300 uppercase font-medium">
            Ready for Auto-Retry
          </p>
          <p className="text-2xl font-bold text-green-700 dark:text-green-400">
            {data?.ready_for_auto_retry || 0}
          </p>
        </div>
        <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-4">
          <p className="text-xs text-yellow-700 dark:text-yellow-300 uppercase font-medium">
            Manual Intervention
          </p>
          <p className="text-2xl font-bold text-yellow-700 dark:text-yellow-400">
            {data?.manual_intervention_required || 0}
          </p>
        </div>
      </div>

      {/* Refresh Button */}
      <div className="flex gap-2">
        <button
          onClick={loadFailedEmails}
          disabled={loading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-lg transition flex items-center gap-2"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Empty State */}
      {emails.length === 0 && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-8 text-center">
          <AlertCircle className="mx-auto mb-2 text-green-600 dark:text-green-400" size={32} />
          <p className="text-green-800 dark:text-green-200 font-medium">No failed emails</p>
          <p className="text-sm text-green-700 dark:text-green-300 mt-1">
            All emails have been processed successfully
          </p>
        </div>
      )}

      {/* Emails List */}
      <div className="space-y-3">
        {emails.map((email) => {
          const badge = getFailureReasonBadge(email.failure_reason)
          const ready = isReadyForRetry(email.next_retry_at)

          return (
            <div
              key={email.id}
              className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:shadow-md transition"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  {/* Subject */}
                  <h4 className="font-medium text-gray-900 dark:text-white truncate mb-2">
                    {email.subject || '(No Subject)'}
                  </h4>

                  {/* Meta Info */}
                  <div className="space-y-1 text-sm">
                    <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                      <Mail size={14} />
                      <span className="truncate">{email.message_id}</span>
                    </div>
                    {email.sender && (
                      <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                        <User size={14} />
                        <span className="truncate">{email.sender}</span>
                      </div>
                    )}
                  </div>

                  {/* Error Details */}
                  <div className="mt-3 space-y-2">
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2.5 py-1 rounded text-xs font-medium ${badge.bg} ${badge.text}`}
                      >
                        {badge.label}
                      </span>
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        Attempt {email.error_count}
                      </span>
                    </div>
                    {email.error_message && (
                      <p className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2">
                        {email.error_message}
                      </p>
                    )}
                  </div>

                  {/* Retry Schedule Info */}
                  {email.next_retry_at && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                      <Clock size={12} />
                      <span>
                        {ready
                          ? 'Ready for retry now'
                          : `Next retry: ${formatDate(email.next_retry_at)}`}
                      </span>
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex flex-col gap-2 whitespace-nowrap">
                  <button
                    onClick={() => handleRetry(email.id)}
                    disabled={actionLoading === email.id}
                    className="px-3 py-1.5 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white text-sm rounded transition flex items-center gap-1"
                    title="Retry this email now (bypasses backoff)"
                  >
                    <RefreshCw size={14} />
                    Retry
                  </button>
                  <button
                    onClick={() => handleRemove(email.id)}
                    disabled={actionLoading === email.id}
                    className="px-3 py-1.5 bg-red-600 hover:bg-red-700 disabled:bg-gray-400 text-white text-sm rounded transition flex items-center gap-1"
                    title="Remove from retry queue"
                  >
                    <Trash2 size={14} />
                    Remove
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
