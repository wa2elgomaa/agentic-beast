'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { AdaptorType, ScheduleType, TaskStatus, IngestionTaskCreateInput } from '@/types'
import { createIngestionTask } from '@/lib/api'
import { AlertCircle, ChevronRight, ChevronLeft } from 'lucide-react'

export default function CreateTaskWizard() {
  const router = useRouter()
  const [step, setStep] = useState(1)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const [formData, setFormData] = useState<IngestionTaskCreateInput>({
    name: '',
    adaptor_type: 'manual' as AdaptorType,
    adaptor_config: {},
    schedule_type: 'none' as ScheduleType,
    status: 'active' as TaskStatus,
  })

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value
    }))
  }

  const handleConfigChange = (key: string, value: string) => {
    setFormData(prev => ({
      ...prev,
      adaptor_config: {
        ...prev.adaptor_config,
        [key]: value
      }
    }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (step < 3) {
      setStep(step + 1)
      return
    }

    try {
      setIsLoading(true)
      setError(null)

      const payload: IngestionTaskCreateInput = {
        ...formData,
        ...(formData.adaptor_type === 'webhook'
          ? {
              schedule_type: 'none',
              cron_expression: undefined,
              run_at: undefined,
            }
          : {}),
      }
      
      const newTask = await createIngestionTask(payload)
      
      // Redirect to task detail page
      router.push(`/admin/ingestion/${newTask.id}`)
    } catch (err) {
      const raw = err instanceof Error ? err.message : 'Failed to create task'
      // Prevent raw database/server stack traces from reaching the user
      const isTechnical = /programmingerror|sqlerror|asyncpg|sqlalchemy|traceback|undefined.*type|syntax error/i.test(raw)
      setError(isTechnical ? 'A server error occurred. Please try again or contact an administrator.' : raw)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        {/* Progress Bar */}
        <div className="flex h-1 bg-gray-200 dark:bg-gray-700">
          {[1, 2, 3].map(s => (
            <div
              key={s}
              className={`flex-1 transition-colors ${s <= step ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'}`}
            />
          ))}
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="p-8">
          {error && (
            <div className="mb-6 flex items-start gap-3 px-4 py-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900 rounded-lg">
              <AlertCircle size={18} className="text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-red-800 dark:text-red-200 text-sm break-words min-w-0">{error}</p>
            </div>
          )}

          {/* Step 1: Basic Info */}
          {step === 1 && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Step 1: Basic Information</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">Give your ingestion task a name and choose the data source type</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Task Name</label>
                <input
                  type="text"
                  name="name"
                  value={formData.name}
                  onChange={handleInputChange}
                  placeholder="e.g., Daily Gmail Analytics"
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Data Source Type</label>
                <select
                  name="adaptor_type"
                  value={formData.adaptor_type}
                  onChange={handleInputChange}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="manual">Manual Upload (Excel/CSV)</option>
                  <option value="gmail">Gmail Inbox</option>
                  <option value="webhook">Webhook</option>
                </select>
                <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">
                  {formData.adaptor_type === 'manual' && 'Upload files manually through the dashboard'}
                  {formData.adaptor_type === 'gmail' && 'Automatically fetch attachments from Gmail'}
                  {formData.adaptor_type === 'webhook' && 'Receive data from external services'}
                </p>
              </div>
            </div>
          )}

          {/* Step 2: Configuration */}
          {step === 2 && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Step 2: Configuration</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">Configure settings specific to your data source</p>
              </div>

              {formData.adaptor_type === 'gmail' && (
                <div className="space-y-4">
                  <div className="p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900 rounded-lg">
                    <p className="text-sm text-amber-900 dark:text-amber-200">
                      Gmail tasks use per-user OAuth. After task creation, open task details and click Connect Gmail.
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Gmail Search Query</label>
                    <input
                      type="text"
                      value={formData.adaptor_config.gmail_query || 'has:attachment is:unread'}
                      onChange={(e) => handleConfigChange('gmail_query', e.target.value)}
                      placeholder="has:attachment is:unread"
                      className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Sender Filter (optional)</label>
                    <input
                      type="text"
                      value={formData.adaptor_config.sender_filter || ''}
                      onChange={(e) => handleConfigChange('sender_filter', e.target.value)}
                      placeholder="reports@emplifi.io"
                      className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">Only emails from this sender will be processed</p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Subject Pattern (optional regex)</label>
                    <input
                      type="text"
                      value={formData.adaptor_config.subject_pattern || ''}
                      onChange={(e) => handleConfigChange('subject_pattern', e.target.value)}
                      placeholder="Scheduled Report \(Emplifi - .*\)"
                      className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">Example: Scheduled Report (Emplifi - ...)</p>
                  </div>
                </div>
              )}

              {formData.adaptor_type === 'webhook' && (
                <div>
                  <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Webhook Secret (for HMAC validation)</label>
                  <input
                    type="password"
                    value={formData.adaptor_config.webhook_secret || ''}
                    onChange={(e) => handleConfigChange('webhook_secret', e.target.value)}
                    placeholder="Your secret key for validating webhook signatures"
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">Used to validate incoming webhook requests</p>
                </div>
              )}

              {formData.adaptor_type === 'manual' && (
                <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-900 rounded-lg">
                  <p className="text-sm text-blue-800 dark:text-blue-200">
                    Manual upload tasks don't require additional configuration. You'll be able to upload files after creating the task.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Step 3: Schedule */}
          {step === 3 && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Step 3: Scheduling</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">Set when and how often this task should run</p>
              </div>

              {formData.adaptor_type === 'webhook' ? (
                <div className="p-4 bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-900 rounded-lg">
                  <p className="text-sm text-indigo-900 dark:text-indigo-200">
                    Webhook tasks are always event-driven and run immediately when payloads arrive. No schedule is needed.
                  </p>
                </div>
              ) : (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Schedule Type</label>
                    <select
                      name="schedule_type"
                      value={formData.schedule_type}
                      onChange={handleInputChange}
                      className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="none">No Schedule (Manual Only)</option>
                      <option value="once">Run Once</option>
                      <option value="recurring">Recurring</option>
                    </select>
                  </div>

                  {formData.schedule_type === 'once' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Run At (Date & Time)</label>
                      <input
                        type="datetime-local"
                        name="run_at"
                        value={formData.run_at || ''}
                        onChange={handleInputChange}
                        className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                  )}

                  {formData.schedule_type === 'recurring' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Cron Expression</label>
                      <input
                        type="text"
                        name="cron_expression"
                        value={formData.cron_expression || ''}
                        onChange={handleInputChange}
                        placeholder="0 0 * * * (Daily at midnight)"
                        className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                      <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">Use standard cron syntax (minute hour day month weekday)</p>
                    </div>
                  )}
                </>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Initial Status</label>
                <select
                  name="status"
                  value={formData.status}
                  onChange={handleInputChange}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="active">Active (Start immediately)</option>
                  <option value="paused">Paused (Start manually later)</option>
                </select>
              </div>
            </div>
          )}

          {/* Buttons */}
          <div className="mt-8 flex gap-3 justify-between">
            <button
              type="button"
              onClick={() => setStep(Math.max(1, step - 1))}
              disabled={step === 1}
              className="flex items-center gap-2 px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft size={16} />
              Previous
            </button>

            <button
              type="submit"
              disabled={isLoading || !formData.name}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
            >
              {step === 3 ? (isLoading ? 'Creating...' : 'Create Task') : <>
                Next
                <ChevronRight size={16} />
              </>}
            </button>
          </div>

          {/* Step Indicator */}
          <div className="mt-6 text-center text-sm text-gray-600 dark:text-gray-400">
            Step {step} of 3
          </div>
        </form>
      </div>
    </div>
  )
}
