'use client'

import { useEffect, useState } from 'react'
import { IngestionTask } from '@/types'
import { getIngestionTasks, deleteIngestionTask } from '@/lib/api'
import TaskList from '@/components/admin/TaskList'
import Link from 'next/link'
import { Plus, AlertCircle } from 'lucide-react'

export default function IngestionPage() {
  const [tasks, setTasks] = useState<IngestionTask[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadTasks()
  }, [])

  const loadTasks = async () => {
    try {
      setIsLoading(true)
      setError(null)
      const data = await getIngestionTasks()
      setTasks(data || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tasks')
    } finally {
      setIsLoading(false)
    }
  }

  const handleDelete = async (taskId: string) => {
    if (!confirm('Are you sure you want to delete this task?')) return

    try {
      await deleteIngestionTask(taskId)
      setTasks(tasks.filter(t => t.id !== taskId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete task')
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Data Ingestion Tasks</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Manage automated data ingestion from Gmail, webhooks, and manual uploads
          </p>
        </div>
        <Link
          href="/admin/ingestion/new"
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors font-medium"
        >
          <Plus size={18} />
          New Task
        </Link>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="flex items-center gap-3 px-4 py-3 bg-red-50 border border-red-200 rounded-lg">
          <AlertCircle size={18} className="text-red-600 flex-shrink-0" />
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="text-gray-500 dark:text-gray-400">Loading tasks...</div>
        </div>
      ) : tasks.length === 0 ? (
        <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No tasks yet</h3>
          <p className="text-gray-600 dark:text-gray-400 mb-4">Create your first data ingestion task to get started</p>
          <Link
            href="/admin/ingestion/new"
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors font-medium"
          >
            <Plus size={18} />
            Create Task
          </Link>
        </div>
      ) : (
        <TaskList tasks={tasks} onDelete={handleDelete} onRefresh={loadTasks} />
      )}
    </div>
  )
}
