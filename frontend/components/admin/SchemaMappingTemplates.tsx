'use client'

import { useState, useEffect } from 'react'
import { getSchemaMappingTemplates } from '@/lib/api'
import { SchemaMappingTemplate } from '@/types'
import { AlertCircle } from 'lucide-react'

interface SchemaMappingTemplatesProps {
  taskId: string
  onApply: (mapping: Record<string, string>) => void
}

export default function SchemaMappingTemplates({ taskId, onApply }: SchemaMappingTemplatesProps) {
  const [templates, setTemplates] = useState<SchemaMappingTemplate[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isOpen, setIsOpen] = useState(false)

  useEffect(() => {
    if (isOpen) {
      loadTemplates()
    }
  }, [isOpen])

  const loadTemplates = async () => {
    try {
      setIsLoading(true)
      setError(null)
      const data = await getSchemaMappingTemplates()
      setTemplates(data || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load templates')
    } finally {
      setIsLoading(false)
    }
  }

  const handleApplyTemplate = (template: SchemaMappingTemplate) => {
    onApply(template.field_mappings)
    setIsOpen(false)
  }

  return (
    <div className="relative inline-block">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors font-medium"
      >
        Use Template
      </button>

      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />

          {/* Dropdown */}
          <div className="absolute top-full left-0 mt-2 w-80 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 max-h-96 overflow-y-auto">
            {isLoading ? (
              <div className="p-4 text-center text-gray-600 dark:text-gray-400">Loading templates...</div>
            ) : error ? (
              <div className="p-4 flex items-center gap-2 text-red-600 dark:text-red-400">
                <AlertCircle size={16} />
                {error}
              </div>
            ) : templates.length === 0 ? (
              <div className="p-4 text-center text-gray-600 dark:text-gray-400">No templates saved yet</div>
            ) : (
              <div className="divide-y divide-gray-200 dark:divide-gray-700">
                {templates.map((template) => (
                  <div key={template.id} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors">
                    <button
                      onClick={() => handleApplyTemplate(template)}
                      className="w-full text-left"
                    >
                      <h4 className="font-medium text-gray-900 dark:text-white">{template.name}</h4>
                      {template.description && (
                        <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">{template.description}</p>
                      )}
                      <div className="text-xs text-gray-500 dark:text-gray-500 mt-2">
                        {Object.keys(template.field_mappings).length} field mappings
                      </div>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
