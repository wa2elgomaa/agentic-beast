'use client'

import { useState, useEffect } from 'react'
import { IngestionTask, IngestionTaskUpdateInput, ScheduleType, TaskStatus } from '@/types'
import { updateIngestionTask } from '@/lib/api'
import { AlertCircle, Save } from 'lucide-react'
import CronBuilder from './CronBuilder'

function toUtcIsoOrUndefined(localDateTime: string | undefined): string | undefined {
  if (!localDateTime) return undefined
  const parsed = new Date(localDateTime)
  if (Number.isNaN(parsed.getTime())) return undefined
  return parsed.toISOString()
}

interface TaskSettingsFormProps {
  task: IngestionTask
  onUpdated: () => void
}

export default function TaskSettingsForm({ task, onUpdated }: TaskSettingsFormProps) {
  const isWebhookTask = task.adaptor_type === 'webhook'
  const [name, setName] = useState(task.name)
  const [status, setStatus] = useState<TaskStatus>(task.status)
  const [scheduleType, setScheduleType] = useState<ScheduleType>(task.schedule_type)
  const [cronExpression, setCronExpression] = useState(task.cron_expression || '')
  const [runAt, setRunAt] = useState(task.run_at ? task.run_at.slice(0, 16) : '')

  // Gmail-specific fields from adaptor_config
  const [gmailQuery, setGmailQuery] = useState<string>(task.adaptor_config?.gmail_query || '')
  const [senderFilter, setSenderFilter] = useState<string>(task.adaptor_config?.sender_filter || '')
  const [subjectPattern, setSubjectPattern] = useState<string>(task.adaptor_config?.subject_pattern || '')
  const [gmailSourceType, setGmailSourceType] = useState<'attachment' | 'download_link'>(task.adaptor_config?.gmail_source_type || 'attachment')
  const [downloadLinkRegex, setDownloadLinkRegex] = useState<string>(task.adaptor_config?.download_link_regex || '')

  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  // Sync form state when task prop changes (e.g., after save and parent re-fetch)
  useEffect(() => {
    setName(task.name)
    setStatus(task.status)
    setScheduleType(task.schedule_type)
    setCronExpression(task.cron_expression || '')
    setRunAt(task.run_at ? task.run_at.slice(0, 16) : '')
    setGmailQuery(task.adaptor_config?.gmail_query || '')
    setSenderFilter(task.adaptor_config?.sender_filter || '')
    setSubjectPattern(task.adaptor_config?.subject_pattern || '')
    setGmailSourceType(task.adaptor_config?.gmail_source_type || 'attachment')
    setDownloadLinkRegex(task.adaptor_config?.download_link_regex || '')
  }, [task])

  const handleCronChange = (newCron: string) => {
    setCronExpression(newCron)
  }
  const handleSave = async () => {
    try {
      setIsSaving(true)
      setError(null)
      setSuccess(false)

      const updates: IngestionTaskUpdateInput = {
        name: name.trim() || task.name,
        status,
        schedule_type: isWebhookTask ? 'none' : scheduleType,
        cron_expression: isWebhookTask ? undefined : (scheduleType === 'recurring' ? cronExpression : undefined),
        run_at: isWebhookTask ? undefined : (scheduleType === 'once' ? toUtcIsoOrUndefined(runAt) : undefined),
      }

      if (task.adaptor_type === 'gmail') {
        updates.adaptor_config = {
          ...task.adaptor_config,
          gmail_query: gmailQuery.trim(), //|| (gmailSourceType === 'download_link' ? 'is:unread' : 'has:attachment is:unread'),
          sender_filter: senderFilter.trim() || undefined,
          subject_pattern: subjectPattern.trim() || undefined,
          gmail_source_type: gmailSourceType,
          download_link_regex: gmailSourceType === 'download_link' ? (downloadLinkRegex.trim() || undefined) : undefined,
        }
        // Remove undefined keys
        if (!updates.adaptor_config.sender_filter) delete updates.adaptor_config.sender_filter
        if (!updates.adaptor_config.subject_pattern) delete updates.adaptor_config.subject_pattern
        if (!updates.adaptor_config.download_link_regex) delete updates.adaptor_config.download_link_regex
      }

      await updateIngestionTask(task.id, updates)
      setSuccess(true)
      onUpdated()
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 space-y-6 max-w-2xl">

      {error && (
        <div className="flex items-start gap-3 px-4 py-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900 rounded-lg">
          <AlertCircle size={18} className="text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
          <p className="text-red-800 dark:text-red-200 text-sm">{error}</p>
        </div>
      )}

      {success && (
        <div className="px-4 py-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-900 rounded-lg">
          <p className="text-green-800 dark:text-green-200 text-sm">✓ Settings saved successfully</p>
        </div>
      )}

      {/* General */}
      <div>
        <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">General</h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-900 dark:text-white mb-1">Task Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-900 dark:text-white mb-1">Status</label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as TaskStatus)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="active">Active</option>
              <option value="paused">Paused</option>
            </select>
          </div>
        </div>
      </div>

      {/* Schedule */}
      <div>
        <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">Schedule</h3>
        {isWebhookTask ? (
          <div className="px-4 py-3 bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-900 rounded-lg">
            <p className="text-sm text-indigo-900 dark:text-indigo-200">
              Webhook tasks are always event-driven. This task runs immediately when webhook payloads arrive and does not use scheduled execution.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-white mb-1">Schedule Type</label>
              <select
                value={scheduleType}
                onChange={(e) => setScheduleType(e.target.value as ScheduleType)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="none">No Schedule (Manual Only)</option>
                <option value="once">Run Once</option>
                <option value="recurring">Recurring</option>
              </select>
            </div>

            {scheduleType === 'once' && (
              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-white mb-1">Run At</label>
                <input
                  type="datetime-local"
                  value={runAt}
                  onChange={(e) => setRunAt(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}

            {scheduleType === 'recurring' && (
              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-white mb-3">Recurring Schedule</label>
                <CronBuilder value={cronExpression} onChange={handleCronChange} />
              </div>
            )}
          </div>
        )}
      </div>

      {/* Gmail Filters */}
      {task.adaptor_type === 'gmail' && (
        <div>
          <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">Gmail Filters</h3>
          <div className="space-y-4">

            {/* Report Source */}
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Report Source</label>
              <div className="flex gap-6">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    value="attachment"
                    checked={gmailSourceType === 'attachment'}
                    onChange={() => {
                      setGmailSourceType('attachment')
                      // if (gmailQuery === 'is:unread') setGmailQuery('has:attachment is:unread')
                    }}
                    className="accent-blue-600"
                  />
                  <span className="text-sm text-gray-700 dark:text-gray-300">Email Attachment</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    value="download_link"
                    checked={gmailSourceType === 'download_link'}
                    onChange={() => {
                      setGmailSourceType('download_link')
                      // if (gmailQuery === 'has:attachment is:unread') setGmailQuery('is:unread')
                    }}
                    className="accent-blue-600"
                  />
                  <span className="text-sm text-gray-700 dark:text-gray-300">Download Link in Body</span>
                </label>
              </div>
            </div>

            {gmailSourceType === 'download_link' && (
              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-white mb-1">
                  Link Extraction Regex <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <input
                  type="text"
                  value={downloadLinkRegex}
                  onChange={(e) => setDownloadLinkRegex(e.target.value)}
                  placeholder={String.raw`sbks-reporting\.svc\.emplifi\.io/download/|https?://\\S+`}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Regex to match the real target URL after Outlook Safe Links are unwrapped. Leave empty to accept any HTTP(S) link.
                </p>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-white mb-1">Gmail Search Query</label>
              <input
                type="text"
                value={gmailQuery}
                onChange={(e) => setGmailQuery(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-white mb-1">Sender Filter <span className="text-gray-400 font-normal">(optional)</span></label>
              <input
                type="text"
                value={senderFilter}
                onChange={(e) => setSenderFilter(e.target.value)}
                placeholder="reports@example.com"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Only emails from this sender will be processed</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-white mb-1">Subject Pattern <span className="text-gray-400 font-normal">(optional regex)</span></label>
              <input
                type="text"
                value={subjectPattern}
                onChange={(e) => setSubjectPattern(e.target.value)}
                placeholder="Scheduled Report \(.*\)"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Emails whose subject does not match are skipped</p>
            </div>
          </div>
        </div>
      )}

      <button
        onClick={handleSave}
        disabled={isSaving}
        className="flex items-center gap-2 px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg transition-colors font-medium"
      >
        <Save size={16} />
        {isSaving ? 'Saving…' : 'Save Settings'}
      </button>
    </div>
  )
}
