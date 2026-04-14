'use client'

import React, { useState } from 'react'
import { formatInTimeZone } from 'date-fns-tz'
import { APP_TIMEZONE } from '@/lib/dateUtils'
import { IngestionTaskRun } from '@/types'
import { CheckCircle2, AlertCircle, Clock, RefreshCw, XCircle, Eye } from 'lucide-react'

interface TaskRunHistoryProps {
  runs: IngestionTaskRun[]
  onRefresh: () => void
  onCancelRun?: (runId: string) => Promise<void>
  cancelingRunId?: string | null
}

interface DetailModalProps {
  run: IngestionTaskRun
  childRuns: IngestionTaskRun[]
  isOpen: boolean
  onClose: () => void
  onCancelRun?: (runId: string) => Promise<void>
  cancelingRunId?: string | null
  taskId?: string
}

interface ExpandedSubtaskId {
  [key: string]: boolean
}

interface StopConfirmModalProps {
  isOpen: boolean
  runId: string
  runName: string
  childCount: number
  isLoading: boolean
  onConfirm: () => Promise<void>
  onCancel: () => void
}

function StopConfirmModal({ isOpen, runId, runName, childCount, isLoading, onConfirm, onCancel }: StopConfirmModalProps) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full">
        <div className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-shrink-0 flex items-center justify-center h-12 w-12 rounded-full bg-red-100 dark:bg-red-900">
              <XCircle className="h-6 w-6 text-red-600 dark:text-red-200" />
            </div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">Stop Task Run?</h3>
          </div>

          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Are you sure you want to stop this task run?{' '}
            {childCount > 0 && (
              <span>
                <strong>{childCount} email subtask{childCount !== 1 ? 's' : ''}</strong> will also be stopped.
              </span>
            )}
          </p>

          <div className="bg-gray-50 dark:bg-gray-700/50 rounded p-3 mb-6">
            <p className="text-xs text-gray-600 dark:text-gray-400">
              <strong>Run:</strong> {runName}
            </p>
          </div>

          <div className="flex gap-3 justify-end">
            <button
              onClick={onCancel}
              disabled={isLoading}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              disabled={isLoading}
              className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50 flex items-center gap-2"
            >
              {isLoading ? (
                <>
                  <Clock size={14} className="animate-spin" />
                  Stopping...
                </>
              ) : (
                <>
                  <XCircle size={14} />
                  Stop Run
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

const getStatusIcon = (status: string) => {
  switch (status) {
    case 'completed':
      return <CheckCircle2 size={16} className="text-green-600" />
    case 'failed':
      return <AlertCircle size={16} className="text-red-600" />
    case 'partial':
      return <AlertCircle size={16} className="text-yellow-600" />
    case 'running':
      return <Clock size={16} className="text-blue-600 animate-spin" />
    case 'canceled':
      return <XCircle size={16} className="text-gray-500" />
    default:
      return <Clock size={16} className="text-gray-600" />
  }
}

const getStatusColor = (status: string) => {
  switch (status) {
    case 'completed':
      return 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'
    case 'failed':
      return 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200'
    case 'partial':
      return 'bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200'
    case 'running':
      return 'bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200'
    case 'canceled':
      return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
    default:
      return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
  }
}

function DetailModal({ run, childRuns, isOpen, onClose, onCancelRun, cancelingRunId, taskId }: DetailModalProps) {
  const [expandedSubtasks, setExpandedSubtasks] = useState<ExpandedSubtaskId>({})

  const toggleSubtaskExpand = (subtaskId: string) => {
    setExpandedSubtasks(prev => ({
      ...prev,
      [subtaskId]: !prev[subtaskId]
    }))
  }

  if (!isOpen) return null

  const successRate = run.rows_inserted + run.rows_updated > 0
    ? ((run.rows_inserted + run.rows_updated) / (run.rows_inserted + run.rows_updated + run.rows_failed) * 100).toFixed(1)
    : 'N/A'

  const executionTime = run.started_at && run.completed_at
    ? new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
    : null

  const getSubtaskSuccessRate = (subtask: IngestionTaskRun) => {
    const total = subtask.rows_inserted + subtask.rows_updated + subtask.rows_failed
    if (total === 0) return 'N/A'
    return ((subtask.rows_inserted + subtask.rows_updated) / total * 100).toFixed(0)
  }

  const getSubtaskExecutionTime = (subtask: IngestionTaskRun) => {
    if (!subtask.started_at || !subtask.completed_at) return null
    return new Date(subtask.completed_at).getTime() - new Date(subtask.started_at).getTime()
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Run Details</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
          >
            ✕
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Basic Info */}
          <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 space-y-3">
            <h3 className="font-semibold text-gray-900 dark:text-white">Execution Summary</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Status</p>
                <p className={`text-sm font-medium px-2.5 py-1 rounded-full inline-block capitalize ${getStatusColor(run.status)}`}>
                  {run.status}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Duration</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {executionTime ? `${executionTime}ms` : '-'}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Success Rate</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">{successRate}%</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Started At</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {run.started_at ? formatInTimeZone(new Date(run.started_at), APP_TIMEZONE, 'yyyy-MM-dd HH:mm:ss') : '-'}
                </p>
              </div>
            </div>
          </div>

          {/* Row Statistics */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4 border border-green-200 dark:border-green-900">
              <p className="text-xs text-green-600 dark:text-green-400 font-medium uppercase">Inserted</p>
              <p className="text-2xl font-bold text-green-700 dark:text-green-300 mt-2">{run.rows_inserted}</p>
              <p className="text-xs text-green-600 dark:text-green-400 mt-1">New records created</p>
            </div>

            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 border border-blue-200 dark:border-blue-900">
              <p className="text-xs text-blue-600 dark:text-blue-400 font-medium uppercase">Appended</p>
              <p className="text-2xl font-bold text-blue-700 dark:text-blue-300 mt-2">{run.rows_updated}</p>
              <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">Duplicates with changes</p>
            </div>

            <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4 border border-red-200 dark:border-red-900">
              <p className="text-xs text-red-600 dark:text-red-400 font-medium uppercase">Failed</p>
              <p className="text-2xl font-bold text-red-700 dark:text-red-300 mt-2">{run.rows_failed}</p>
              <p className="text-xs text-red-600 dark:text-red-400 mt-1">Processing errors</p>
            </div>
          </div>

          {/* Subtasks Table (if parent has child runs) */}
          {childRuns.length > 0 && (
            <div className="space-y-3">
              <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                📧 Email Processing Subtasks
                <span className="px-2.5 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 text-xs font-bold">
                  {childRuns.length}
                </span>
              </h3>
              <div className="space-y-2">
                {childRuns.map((subtask) => {
                  const successRate = getSubtaskSuccessRate(subtask)
                  const execTime = getSubtaskExecutionTime(subtask)
                  const isExpanded = expandedSubtasks[subtask.id]
                  const emailSubject = subtask.run_metadata?.email_subject || 'Unknown Subject'
                  const messageId = subtask.run_metadata?.selected_message_id ? subtask.run_metadata.selected_message_id.substring(0, 16) : '-'

                  return (
                    <div key={subtask.id} className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden hover:shadow-md transition-shadow">
                      {/* Main Row */}
                      <div
                        className="bg-gray-50 dark:bg-gray-700/30 hover:bg-gray-100 dark:hover:bg-gray-700/50 p-4 cursor-pointer"
                        onClick={() => toggleSubtaskExpand(subtask.id)}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-start gap-3 flex-1 min-w-0">
                            {/* Status Icon and Badge */}
                            <div className="flex items-center gap-2 flex-shrink-0 pt-0.5">
                              {getStatusIcon(subtask.status)}
                              <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold capitalize whitespace-nowrap ${getStatusColor(subtask.status)}`}>
                                {subtask.status}
                              </span>
                            </div>

                            {/* Subject and ID */}
                            <div className="min-w-0 flex-1">
                              <div className="flex items-baseline gap-2">
                                <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                                  {emailSubject}
                                </p>
                              </div>
                              <p className="text-xs text-gray-500 dark:text-gray-400 font-mono mt-0.5">
                                ID: {messageId}
                              </p>
                            </div>
                          </div>

                          {/* Stats Row */}
                          <div className="flex items-center gap-4 flex-shrink-0">
                            {/* Success Rate */}
                            <div className="text-right">
                              <p className={`text-sm font-bold ${successRate === 'N/A' || parseFloat(successRate) === 100 ? 'text-green-600 dark:text-green-400' :
                                  parseFloat(successRate) >= 50 ? 'text-yellow-600 dark:text-yellow-400' :
                                    'text-red-600 dark:text-red-400'
                                }`}>
                                {successRate}%
                              </p>
                              <p className="text-xs text-gray-500 dark:text-gray-400">Success</p>
                            </div>

                            {/* Row Stats */}
                            <div className="flex gap-2">
                              <div className="text-center">
                                <p className="text-sm font-bold text-green-600 dark:text-green-400">{subtask.rows_inserted}</p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">New</p>
                              </div>
                              <div className="text-center">
                                <p className="text-sm font-bold text-blue-600 dark:text-blue-400">{subtask.rows_updated}</p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">Updated</p>
                              </div>
                              <div className="text-center">
                                <p className="text-sm font-bold text-red-600 dark:text-red-400">{subtask.rows_failed}</p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">Failed</p>
                              </div>
                            </div>

                            {/* Time */}
                            <div className="text-right">
                              <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                                {execTime ? `${execTime}ms` : '-'}
                              </p>
                              <p className="text-xs text-gray-500 dark:text-gray-400">Duration</p>
                            </div>

                            {/* Stop Button */}
                            {['pending', 'running'].includes(subtask.status) && onCancelRun ? (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  onCancelRun(subtask.id)
                                }}
                                disabled={cancelingRunId === subtask.id || Boolean(subtask.run_metadata?.cancel_requested)}
                                className="px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded transition-colors disabled:opacity-50 flex items-center gap-1 whitespace-nowrap"
                                title="Stop this email processing task"
                              >
                                <XCircle size={12} />
                                {cancelingRunId === subtask.id || subtask.run_metadata?.cancel_requested ? 'Stopping...' : 'Stop'}
                              </button>
                            ) : null}

                            {/* Expand Arrow */}
                            {(subtask.error_message || subtask.rows_failed > 0) && (
                              <div className={`text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}>
                                ▼
                              </div>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Expanded Details */}
                      {isExpanded && (subtask.error_message || subtask.rows_failed > 0) && (
                        <div className="border-t border-gray-200 dark:border-gray-700 p-4 bg-white dark:bg-gray-800">
                          {subtask.rows_failed > 0 && (
                            <div className="mb-3 pb-3 border-b border-gray-200 dark:border-gray-700">
                              <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase mb-2">Failed Rows</p>
                              <p className="text-sm text-gray-700 dark:text-gray-300">
                                {subtask.rows_failed} row(s) failed to process
                              </p>
                            </div>
                          )}
                          {subtask.error_message && (
                            <div>
                              <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase mb-2">Error Details</p>
                              <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-3">
                                <p className="text-xs text-red-800 dark:text-red-200 font-mono break-words">
                                  {subtask.error_message}
                                </p>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
          {run.error_message && (
            <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4 border border-red-200 dark:border-red-900">
              <h3 className="font-semibold text-red-900 dark:text-red-100 mb-2">Error Information</h3>
              {run.error_type && (
                <div className="flex gap-2 mb-2">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${run.error_type === 'auth_error'
                      ? 'bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200'
                      : run.error_type === 'network_error'
                        ? 'bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200'
                        : 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200'
                    }`}>
                    {run.error_type}
                  </span>
                  {run.error_code && (
                    <span className="px-2 py-1 text-xs font-mono bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded">
                      {run.error_code}
                    </span>
                  )}
                </div>
              )}
              <p className="text-sm text-red-800 dark:text-red-200 break-words font-mono">
                {run.error_message}
              </p>
            </div>
          )}

          {/* Failed Rows Info */}
          {run.rows_failed > 0 && (
            <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-4 border border-amber-200 dark:border-amber-900">
              <h3 className="font-semibold text-amber-900 dark:text-amber-100 mb-2 flex items-center gap-2">
                <AlertCircle size={16} />
                Failed Rows ({run.rows_failed})
              </h3>
              <p className="text-sm text-amber-800 dark:text-amber-200 mb-3">
                {run.rows_failed} row(s) could not be processed due to errors.
              </p>
              <p className="text-xs text-amber-700 dark:text-amber-300 bg-amber-100 dark:bg-amber-900 px-3 py-2 rounded">
                📋 Row-level error details are available in the backend run_metadata. Contact API for detailed error logs.
              </p>
            </div>
          )}

          {/* Failed Emails Info */}
          {run.failed_emails_count && run.failed_emails_count > 0 && (
            <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-4 border border-orange-200 dark:border-orange-900">
              <h3 className="font-semibold text-orange-900 dark:text-orange-100 mb-2 flex items-center gap-2">
                <AlertCircle size={16} />
                Failed Emails ({run.failed_emails_count})
              </h3>
              <p className="text-sm text-orange-800 dark:text-orange-200 mb-3">
                {run.failed_emails_count} email(s) encountered errors during processing and were queued for retry.
              </p>
              {run.retry_emails_count && run.retry_emails_count > 0 && (
                <p className="text-xs text-orange-700 dark:text-orange-300 bg-orange-100 dark:bg-orange-900 px-3 py-2 rounded">
                  ⏱️ {run.retry_emails_count} email(s) scheduled for automatic retry with exponential backoff. View emails in the Failed Emails tab.
                </p>
              )}
            </div>
          )}

          {/* Metadata Info */}
          {run.run_metadata && Object.keys(run.run_metadata).length > 0 && (
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Metadata</h3>
              <div className="space-y-2 text-sm">
                {Object.entries(run.run_metadata).map(([key, value]) => (
                  <div key={key} className="flex justify-between items-start">
                    <span className="text-gray-600 dark:text-gray-400">{key.replace("_", " ")}:</span>
                    <span className="text-gray-900 dark:text-white font-mono text-right max-w-sm">
                      {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="sticky bottom-0 flex justify-end gap-3 p-6 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

export default function TaskRunHistory({ runs, onRefresh, onCancelRun, cancelingRunId }: TaskRunHistoryProps) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [stopConfirmRun, setStopConfirmRun] = useState<string | null>(null)
  const [isStoppingConfirm, setIsStoppingConfirm] = useState(false)

  // Helper function - define early to avoid initialization errors
  const getChildRuns = (parentId: string) => {
    return runs.filter(r => r.parent_run_id === parentId)
  }

  const selectedRun = runs.find(r => r.id === selectedRunId)
  const selectedRunChildren = selectedRun ? runs.filter(r => r.parent_run_id === selectedRun.id) : []
  const stopConfirmRunData = stopConfirmRun ? runs.find(r => r.id === stopConfirmRun) : null
  const stopConfirmChildCount = stopConfirmRunData ? getChildRuns(stopConfirmRunData.id).length : 0

  // Only show parent runs (no children in main table)
  const parentRuns = runs.filter(r => !r.parent_run_id)

  const handleStopClick = (runId: string) => {
    setStopConfirmRun(runId)
  }

  const handleConfirmStop = async () => {
    if (!stopConfirmRun || !onCancelRun) return
    setIsStoppingConfirm(true)
    try {
      await onCancelRun(stopConfirmRun)
    } finally {
      setIsStoppingConfirm(false)
      setStopConfirmRun(null)
    }
  }

  // Render row data for parent runs only
  const renderRunRow = (run: IngestionTaskRun) => {
    const childCount = getChildRuns(run.id).length

    return (
      <tr
        key={run.id}
        className="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50"
      >
        <td className="px-6 py-4">
          <div className="flex items-center gap-2">
            {getStatusIcon(run.status)}
            <span className={`px-2.5 py-1 rounded-full text-xs font-medium capitalize ${getStatusColor(run.status)}`}>
              {run.status}
              {childCount > 0 && run.status === 'pending' && (
                <span className="ml-1 text-xs text-gray-600 dark:text-gray-400">
                  ({getChildRuns(run.id).filter(c => c.status === 'completed').length}/{childCount} emails)
                </span>
              )}
            </span>
          </div>
        </td>
        <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
          {run.started_at ? formatInTimeZone(new Date(run.started_at), APP_TIMEZONE, 'yyyy-MM-dd HH:mm:ss') : '-'}
        </td>
        <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
          {run.completed_at ? formatInTimeZone(new Date(run.completed_at), APP_TIMEZONE, 'yyyy-MM-dd HH:mm:ss') : '-'}
        </td>
        <td className="px-6 py-4 text-sm font-medium text-green-700 dark:text-green-300">{run.rows_inserted}</td>
        <td className="px-6 py-4 text-sm font-medium text-blue-700 dark:text-blue-300">
          <span title="Duplicates with changed metrics (appended as new version)" className="cursor-help">
            {run.rows_updated}
          </span>
        </td>
        <td className="px-6 py-4 text-sm font-medium text-red-700 dark:text-red-300">{run.rows_failed}</td>
        <td className="px-6 py-4 text-sm font-medium">
          {run.failed_emails_count ? (
            <span title="Emails that failed during processing" className="cursor-help px-2 py-1 rounded-full bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200 text-xs font-medium">
              {run.failed_emails_count}
            </span>
          ) : (
            <span className="text-gray-400">-</span>
          )}
        </td>
        <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400 max-w-xs">
          <div className="space-y-1">
            {run.error_type && (
              <div className="flex gap-1">
                <span className={`px-2 py-1 rounded text-xs font-medium ${run.error_type === 'auth_error'
                    ? 'bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200'
                    : run.error_type === 'network_error'
                      ? 'bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200'
                      : 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200'
                  }`}>
                  {run.error_type}
                </span>
                {run.error_code && (
                  <span className="px-2 py-1 text-xs font-mono bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded">
                    {run.error_code}
                  </span>
                )}
              </div>
            )}
            {run.error_message && (
              <span title={run.error_message} className="text-red-600 dark:text-red-400 block truncate text-xs">
                {run.error_message.length > 50 ? `${run.error_message.substring(0, 50)}...` : run.error_message}
              </span>
            )}
            {!run.error_type && !run.error_message && <span>-</span>}
          </div>
        </td>
        <td className="px-6 py-4 text-sm">
          <div className="flex gap-2">
            <button
              onClick={() => setSelectedRunId(run.id)}
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded transition-colors"
              title={childCount > 0 ? "View details and email subtasks" : "View detailed execution stats"}
            >
              <Eye size={14} />
              Details
            </button>
            {['pending', 'running'].includes(run.status) && onCancelRun ? (
              <button
                onClick={() => handleStopClick(run.id)}
                disabled={cancelingRunId === run.id || Boolean(run.run_metadata?.cancel_requested)}
                className="text-red-600 hover:text-red-700 disabled:opacity-50 font-medium text-xs"
              >
                {cancelingRunId === run.id || run.run_metadata?.cancel_requested ? 'Stopping...' : 'Stop'}
              </button>
            ) : null}
          </div>
        </td>
      </tr>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Run History</h3>
        <button
          onClick={onRefresh}
          className="flex items-center gap-2 px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {runs.length === 0 ? (
        <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 border-dashed">
          <p className="text-gray-600 dark:text-gray-400">No runs yet. Trigger the task to see history.</p>
        </div>
      ) : (
        <div className="overflow-x-auto bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Started At</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Completed At</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Inserted</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Appended</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Failed</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Failed Emails</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Error</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Action</th>
              </tr>
            </thead>
            <tbody>
              {parentRuns.map((parentRun) => renderRunRow(parentRun))}
            </tbody>
          </table>
        </div>
      )}

      {selectedRun && (
        <DetailModal
          run={selectedRun}
          childRuns={selectedRunChildren}
          isOpen={!!selectedRunId}
          onClose={() => setSelectedRunId(null)}
          onCancelRun={onCancelRun}
          cancelingRunId={cancelingRunId}
        />
      )}

      <StopConfirmModal
        isOpen={!!stopConfirmRun}
        runId={stopConfirmRun || ''}
        runName={stopConfirmRunData?.run_metadata?.display_name || `Run ${stopConfirmRun?.slice(0, 8)}`}
        childCount={stopConfirmChildCount}
        isLoading={isStoppingConfirm}
        onConfirm={handleConfirmStop}
        onCancel={() => setStopConfirmRun(null)}
      />
    </div>
  )
}
