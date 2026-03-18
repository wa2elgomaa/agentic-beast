'use client'

import { IngestionTaskRun } from '@/types'
import { CheckCircle2, AlertCircle, Clock, RefreshCw, XCircle } from 'lucide-react'

interface TaskRunHistoryProps {
  runs: IngestionTaskRun[]
  onRefresh: () => void
  onCancelRun?: (runId: string) => Promise<void>
  cancelingRunId?: string | null
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

export default function TaskRunHistory({ runs, onRefresh, onCancelRun, cancelingRunId }: TaskRunHistoryProps) {
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
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Updated</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Failed</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Error</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Action</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id} className="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      {getStatusIcon(run.status)}
                      <span className={`px-2.5 py-1 rounded-full text-xs font-medium capitalize ${getStatusColor(run.status)}`}>
                        {run.status}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : '-'}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                    {run.completed_at ? new Date(run.completed_at).toLocaleString() : '-'}
                  </td>
                  <td className="px-6 py-4 text-sm font-medium text-green-700 dark:text-green-300">{run.rows_inserted}</td>
                  <td className="px-6 py-4 text-sm font-medium text-blue-700 dark:text-blue-300">{run.rows_updated}</td>
                  <td className="px-6 py-4 text-sm font-medium text-red-700 dark:text-red-300">{run.rows_failed}</td>
                  <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400 max-w-xs truncate">
                    {run.error_message ? (
                      <span title={run.error_message} className="text-red-600 dark:text-red-400">
                        {run.error_message.length > 50 ? `${run.error_message.substring(0, 50)}...` : run.error_message}
                      </span>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                    {['pending', 'running'].includes(run.status) && onCancelRun ? (
                      <button
                        onClick={() => onCancelRun(run.id)}
                        disabled={cancelingRunId === run.id || Boolean(run.run_metadata?.cancel_requested)}
                        className="text-red-600 hover:text-red-700 disabled:opacity-50 font-medium"
                      >
                        {cancelingRunId === run.id || run.run_metadata?.cancel_requested ? 'Stopping...' : 'Stop'}
                      </button>
                    ) : (
                      '-'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
