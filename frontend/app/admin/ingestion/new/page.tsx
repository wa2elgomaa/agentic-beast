'use client'

import CreateTaskWizard from '@/components/admin/CreateTaskWizard'

export default function NewTaskPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Create New Ingestion Task</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          Set up a new data source for automated or manual ingestion
        </p>
      </div>

      <CreateTaskWizard />
    </div>
  )
}
