'use client'

import { useState, useEffect } from 'react'
import { Play, RefreshCw, CheckCircle, AlertCircle, Clock, Zap } from 'lucide-react'
import { IngestionTask } from '@/types'

interface CronTestRun {
  id: string
  task_id: string
  executed_at: string
  status: 'success' | 'failed' | 'running'
  duration_ms: number
  error_message?: string
  logs?: string
}

interface CronTestMonitorProps {
  task: IngestionTask
  onTestRun?: () => void
}

export default function CronTestMonitor({ task, onTestRun }: CronTestMonitorProps) {
  const [testRuns, setTestRuns] = useState<CronTestRun[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedRun, setSelectedRun] = useState<CronTestRun | null>(null)

  // Fetch test runs on mount
  useEffect(() => {
    const fetchTestRuns = async () => {
      try {
        setIsLoading(true)
        // TODO: Replace with actual API call
        // const response = await fetch(`/api/admin/tasks/${task.id}/test-runs`)
        // const data = await response.json()
        // setTestRuns(data)
        setTestRuns([]) // Placeholder
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load test runs')
      } finally {
        setIsLoading(false)
      }
    }

    fetchTestRuns()
  }, [task.id])

  const handleRunTest = async () => {
    try {
      setIsRunning(true)
      setError(null)
      setSelectedRun(null)

      // TODO: Replace with actual API call
      // const response = await fetch(`/api/admin/tasks/${task.id}/test-run`, {
      //   method: 'POST',
      // })
      // const result = await response.json()

      // For now, simulate a test run
      const newRun: CronTestRun = {
        id: `test-${Date.now()}`,
        task_id: task.id,
        executed_at: new Date().toISOString(),
        status: 'running',
        duration_ms: 0,
      }
      setTestRuns([newRun, ...testRuns])

      // Simulate delay
      await new Promise(resolve => setTimeout(resolve, 2000))

      newRun.status = 'success'
      newRun.duration_ms = 2000
      setTestRuns([newRun, ...testRuns.slice(1)])

      onTestRun?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Test run failed')
    } finally {
      setIsRunning(false)
    }
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString()
  }

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center justify-center gap-2">
          <RefreshCw size={16} className="animate-spin text-gray-500" />
          <p className="text-gray-600 dark:text-gray-400 text-sm">Loading test history...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button
          onClick={handleRunTest}
          disabled={isRunning}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg transition-colors font-medium text-sm"
        >
          <Zap size={14} />
          {isRunning ? 'Running...' : 'Run Test Now'}
        </button>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="flex items-start gap-3 px-4 py-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900 rounded-lg">
          <AlertCircle size={16} className="text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
          <p className="text-red-800 dark:text-red-200 text-sm">{error}</p>
        </div>
      )}

      {/* Test Runs List */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        {testRuns.length > 0 ? (
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {testRuns.map((run) => (
              <div
                key={run.id}
                className={`p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors ${
                  selectedRun?.id === run.id ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                }`}
                onClick={() => setSelectedRun(selectedRun?.id === run.id ? null : run)}
              >
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    {run.status === 'success' ? (
                      <CheckCircle size={18} className="text-green-600 flex-shrink-0" />
                    ) : run.status === 'failed' ? (
                      <AlertCircle size={18} className="text-red-600 flex-shrink-0" />
                    ) : (
                      <Clock size={18} className="text-yellow-600 animate-pulse flex-shrink-0" />
                    )}

                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-gray-900 dark:text-white">
                        {formatDate(run.executed_at)}
                      </p>
                      <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
                        {run.status === 'running' && 'Executing...'}
                        {run.status === 'success' && `✓ Completed in ${formatDuration(run.duration_ms)}`}
                        {run.status === 'failed' && `✗ Failed in ${formatDuration(run.duration_ms)}`}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                      run.status === 'success'
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200'
                        : run.status === 'failed'
                        ? 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200'
                        : 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200'
                    }`}>
                      {run.status.toUpperCase()}
                    </span>
                  </div>
                </div>

                {/* Expanded Details */}
                {selectedRun?.id === run.id && (
                  <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 space-y-3">
                    {run.error_message && (
                      <div>
                        <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Error:</p>
                        <p className="text-sm text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded font-mono">
                          {run.error_message}
                        </p>
                      </div>
                    )}

                    {run.logs && (
                      <div>
                        <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Logs:</p>
                        <pre className="text-xs text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-900 px-3 py-2 rounded overflow-x-auto max-h-64">
                          {run.logs}
                        </pre>
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-2">
                      <div className="px-3 py-2 bg-gray-50 dark:bg-gray-700/50 rounded text-xs">
                        <p className="text-gray-600 dark:text-gray-400">Duration</p>
                        <p className="text-gray-900 dark:text-white font-medium">{formatDuration(run.duration_ms)}</p>
                      </div>
                      <div className="px-3 py-2 bg-gray-50 dark:bg-gray-700/50 rounded text-xs">
                        <p className="text-gray-600 dark:text-gray-400">Task ID</p>
                        <p className="text-gray-900 dark:text-white font-mono text-xs truncate">{run.task_id}</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="p-8 text-center">
            <Clock size={24} className="mx-auto text-gray-400 mb-3" />
            <p className="text-gray-600 dark:text-gray-400 text-sm">No test runs yet</p>
            <p className="text-gray-500 dark:text-gray-500 text-xs mt-1">
              Click "Run Test Now" to execute this cron task manually.
            </p>
          </div>
        )}
      </div>

      {/* Configuration Info */}
      <div className="px-4 py-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-900 rounded-lg">
        <p className="text-xs text-blue-900 dark:text-blue-200">
          <strong>Test Mode:</strong> Tests will execute the ingestion task even if no new data is available.
          This helps verify that the task configuration is working correctly.
        </p>
      </div>
    </div>
  )
}
