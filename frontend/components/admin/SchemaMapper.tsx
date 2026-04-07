'use client'

import { useState } from 'react'
import { IngestionTask, TaskSchemaMapping } from '@/types'
import { updateTaskSchemaMapping, saveSchemaAsTemplate, detectColumnsFromFile, updateIngestionTask } from '@/lib/api'
import ManualUpload from '@/components/admin/ManualUpload'
import SchemaMappingTemplates from '@/components/admin/SchemaMappingTemplates'
import { AlertCircle, Save, BookmarkPlus, Plus } from 'lucide-react'

interface SchemaMappperProps {
  task: IngestionTask
  initialMapping: TaskSchemaMapping | null
  onUpdated: () => void
}

const DB_TARGET_FIELDS = [
  'sheet_name',
  'row_number',
  'platform',
  'published_date',
  'published_time',
  'reported_at',
  'reported_time',
  'profile_name',
  'profile_url',
  'profile_id',
  'content_id',
  'post_detail_url',
  'content_type',
  'media_type',
  'title',
  'description',
  'content',
  'author_name',
  'author_id',
  'author_url',
  'total_reach',
  'organic_reach',
  'paid_reach',
  'total_impressions',
  'organic_impressions',
  'paid_impressions',
  'total_reactions',
  'total_comments',
  'total_shares',
  'total_interactions',
  'organic_interactions',
  'engagements',
  'video_views',
  'video_length_sec',
  'total_video_view_time_sec',
  'avg_video_view_time_sec',
  'completion_rate',
  'labels',
  'label_groups',
] as const

const DUPLICATE_SOURCE_SEPARATOR = '::dup::'

// Deduplication strategy descriptions
const DEDUP_STRATEGIES = {
  'subtract': {
    label: 'Subtract (Delta)',
    description: 'Calculate delta: new_value - sum(previous_values). Best for daily/weekly increment metrics.'
  },
  'keep': {
    label: 'Keep (Replace)',
    description: 'Use only the new value, replacing old. Best for current state metrics (followers, likes).'
  },
  'add': {
    label: 'Add (Cumulative)',
    description: 'Sum all values: new_value + sum(previous_values). Best for lifetime totals.'
  },
  'sum': {
    label: 'Sum (Cumulative)',
    description: 'Same as Add - cumulative sum of all values.'
  },
  'skip': {
    label: 'Skip',
    description: 'Don\'t store duplicate. Completely skip if seen before.'
  }
} as const

interface DeduplicationConfig {
  default_strategy: 'subtract' | 'keep' | 'add' | 'sum' | 'skip'
  field_strategies?: Record<string, 'subtract' | 'keep' | 'add' | 'sum' | 'skip'>
  is_metric?: Record<string, boolean>
}

function uniq(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)))
}

function humanizeField(field: string): string {
  return field
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function normalizeColumnName(value: string): string {
  return (value || '').toLowerCase().replace(/[^a-z0-9]/g, '')
}

function decodeSourceKey(sourceKey: string): string {
  return sourceKey.split(DUPLICATE_SOURCE_SEPARATOR, 1)[0]
}

function toTargetLookup(fieldMappings: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [sourceKey, target] of Object.entries(fieldMappings || {})) {
    if (!target || out[target]) continue
    out[target] = decodeSourceKey(sourceKey)
  }
  return out
}

function fromTargetLookup(targetLookup: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  const sourceUseCount: Record<string, number> = {}

  for (const [target, source] of Object.entries(targetLookup)) {
    if (!source?.trim()) continue

    const normalizedSource = source.trim()
    const currentCount = sourceUseCount[normalizedSource] || 0
    const sourceKey =
      currentCount === 0
        ? normalizedSource
        : `${normalizedSource}${DUPLICATE_SOURCE_SEPARATOR}${currentCount}`

    out[sourceKey] = target
    sourceUseCount[normalizedSource] = currentCount + 1
  }
  return out
}

export default function SchemaMapper({ task, initialMapping, onUpdated }: SchemaMappperProps) {
  const initialFieldMappings = initialMapping?.field_mappings || {}
  const initialSourceColumns = initialMapping?.source_columns || []
  const initialDedupConfig = (initialMapping?.dedup_config || {
    default_strategy: 'subtract',
    field_strategies: {},
    is_metric: {}
  }) as DeduplicationConfig

  const [targetLookup, setTargetLookup] = useState<Record<string, string>>(toTargetLookup(initialFieldMappings))
  const [sourceColumns, setSourceColumns] = useState<string[]>(
    initialSourceColumns
  )
  const [availableColumns, setAvailableColumns] = useState<string[]>(
    uniq([...initialSourceColumns, ...Object.keys(initialFieldMappings)])
  )
  const [dedupConfig, setDedupConfig] = useState<DeduplicationConfig>(initialDedupConfig)

  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [showSaveTemplate, setShowSaveTemplate] = useState(false)
  const [templateName, setTemplateName] = useState('')
  const [templateDescr, setTemplateDescr] = useState('')
  const [columnInput, setColumnInput] = useState('')
  const [identifierColumn, setIdentifierColumn] = useState<string>(initialMapping?.identifier_column || '')

  const customTargetMappings = Object.fromEntries(
    Object.entries(initialFieldMappings).filter(([, target]) => !DB_TARGET_FIELDS.includes(target as typeof DB_TARGET_FIELDS[number]))
  )

  const handleAddColumns = () => {
    const cols = columnInput
      .split(/[\n,]+/)
      .map((c) => c.trim())
      .filter(Boolean)
    if (!cols.length) return

    setAvailableColumns((prev) => uniq([...prev, ...cols]))
    setSourceColumns((prev) => uniq([...prev, ...cols]))
    setColumnInput('')
  }

  const handleColumnDetect = async (file: File) => {
    try {
      setError(null)
      const result = await detectColumnsFromFile(file)
      setSourceColumns(result.source_columns)
      setAvailableColumns((prev) => uniq([...prev, ...result.source_columns]))

      // Apply backend auto-mapping suggestions into target -> source lookup.
      setTargetLookup((prev) => {
        const next = { ...prev }
        for (const [source, target] of Object.entries(result.auto_mapped || {})) {
          next[target] = source
        }

        // Fallback auto-match: treat separators/case as equivalent.
        // Example: total_reach -> Total Reach
        const normalizedSourceMap = new Map<string, string>()
        for (const source of result.source_columns || []) {
          const key = normalizeColumnName(source)
          if (key && !normalizedSourceMap.has(key)) {
            normalizedSourceMap.set(key, source)
          }
        }

        for (const target of DB_TARGET_FIELDS) {
          if (next[target]) continue
          const matchedSource = normalizedSourceMap.get(normalizeColumnName(target))
          if (matchedSource) {
            next[target] = matchedSource
          }
        }

        return next
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to detect columns')
    }
  }

  const handleFieldMappingChange = (target: string, source: string) => {
    setTargetLookup((prev) => ({ ...prev, [target]: source }))
    setSuccess(false)
  }

  const handleToggleIsMetric = (target: string, isMetric: boolean) => {
    setDedupConfig((prev) => ({
      ...prev,
      is_metric: {
        ...prev.is_metric,
        [target]: isMetric
      }
    }))
    setSuccess(false)
  }

  const handleChangeFieldStrategy = (target: string, strategy: string) => {
    setDedupConfig((prev) => ({
      ...prev,
      field_strategies: {
        ...prev.field_strategies,
        [target]: strategy as 'subtract' | 'keep' | 'add' | 'sum' | 'skip'
      }
    }))
    setSuccess(false)
  }

  const handleChangeDefaultStrategy = (strategy: string) => {
    setDedupConfig((prev) => ({
      ...prev,
      default_strategy: strategy as 'subtract' | 'keep' | 'add' | 'sum' | 'skip'
    }))
    setSuccess(false)
  }

  const handleSaveMapping = async () => {
    try {
      setIsSaving(true)
      setError(null)

      const fieldMappings = {
        ...customTargetMappings,
        ...fromTargetLookup(targetLookup),
      }

      await updateTaskSchemaMapping(task.id, {
        source_columns: uniq([...sourceColumns, ...availableColumns]),
        field_mappings: fieldMappings,
        identifier_column: identifierColumn || undefined,
        dedup_config: dedupConfig
      })

      setSuccess(true)
      onUpdated()
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save mapping')
    } finally {
      setIsSaving(false)
    }
  }

  const handleSaveAsTemplate = async () => {
    if (!templateName.trim()) {
      setError('Template name is required')
      return
    }

    try {
      setIsSaving(true)
      setError(null)
      
      await saveSchemaAsTemplate(task.id, {
        name: templateName,
        description: templateDescr
      })
      
      setSuccess(true)
      setTemplateName('')
      setTemplateDescr('')
      setShowSaveTemplate(false)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save template')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Upload Section */}
      {(task.adaptor_type === 'manual' || task.adaptor_type === 'gmail') && (
        <ManualUpload
          taskId={task.adaptor_type === 'manual' ? task.id : undefined}
          detectOnly={task.adaptor_type === 'gmail'}
          onColumnsDetected={handleColumnDetect}
          title="Import Sample File"
          description={
            task.adaptor_type === 'gmail'
              ? 'Upload a sample attachment (Excel/CSV) to detect headers and configure mapping.'
              : 'Upload an Excel/CSV file to detect headers and configure mapping for this upload task.'
          }
        />
      )}

      {/* Alerts */}
      {error && (
        <div className="flex items-center gap-3 px-4 py-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900 rounded-lg">
          <AlertCircle size={18} className="text-red-600 dark:text-red-400 flex-shrink-0" />
          <p className="text-red-800 dark:text-red-200">{error}</p>
        </div>
      )}

      {success && (
        <div className="flex items-center gap-3 px-4 py-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-900 rounded-lg">
          <p className="text-green-800 dark:text-green-200">✓ Changes saved successfully</p>
        </div>
      )}

      {/* Cross-Platform Deduplication Settings */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">
              Deduplication Identifier Column
              <span className="text-gray-400 font-normal"> (optional)</span>
            </label>
            <select
              value={identifierColumn}
              onChange={(e) => {
                setIdentifierColumn(e.target.value)
                setSuccess(false)
              }}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">None (use sheet position)</option>
              {availableColumns.map(col => (
                <option key={col} value={col}>{col}</option>
              ))}
            </select>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
              When set, this column will be normalized and used to detect duplicate content across different platforms/sheets.
              Leave empty to use only sheet position for matching.
            </p>
          </div>
        </div>
      </div>

      {/* Deduplication Strategy Configuration */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">
              Default Deduplication Strategy
            </label>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              When duplicates are found, apply this strategy to all metric fields (unless overridden per-field below)
            </p>
            <select
              value={dedupConfig.default_strategy}
              onChange={(e) => handleChangeDefaultStrategy(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {Object.entries(DEDUP_STRATEGIES).map(([key, { label }]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">
              {DEDUP_STRATEGIES[dedupConfig.default_strategy].description}
            </p>
          </div>
        </div>
      </div>

      {/* Mapping Controls */}
      <div className="flex gap-3 flex-wrap">
        <SchemaMappingTemplates
          taskId={task.id}
          onApply={(mapping: Record<string, string>) => {
            setTargetLookup(toTargetLookup(mapping))
            setAvailableColumns((prev) => uniq([...prev, ...Object.keys(mapping)]))
            setSourceColumns((prev) => uniq([...prev, ...Object.keys(mapping)]))
          }}
        />
        <button
          onClick={() => setShowSaveTemplate(!showSaveTemplate)}
          className="flex items-center gap-2 px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors font-medium"
        >
          <BookmarkPlus size={16} />
          Save as Template
        </button>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-3">
        <p className="text-sm font-medium text-gray-900 dark:text-white">Add source columns to dropdown</p>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Add one or more extra source headers manually (comma or newline separated). This is useful when a sample file is incomplete.
        </p>
        <div className="flex gap-2 flex-col sm:flex-row">
          <textarea
            value={columnInput}
            onChange={(e) => setColumnInput(e.target.value)}
            rows={3}
            placeholder={'date,time,reach'}
            className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
          />
          <button
            onClick={handleAddColumns}
            disabled={!columnInput.trim()}
            className="self-start px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Add Columns
          </button>
        </div>
      </div>

      {/* Save as Template Form */}
      {showSaveTemplate && (
        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-900 rounded-lg space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-900 dark:text-white mb-1">Template Name</label>
            <input
              type="text"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="e.g., Analytics Import Mapping"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-900 dark:text-white mb-1">Description (optional)</label>
            <input
              type="text"
              value={templateDescr}
              onChange={(e) => setTemplateDescr(e.target.value)}
              placeholder="What is this mapping used for?"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleSaveAsTemplate}
              disabled={isSaving || !templateName.trim()}
              className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg transition-colors font-medium"
            >
              {isSaving ? 'Saving...' : 'Save Template'}
            </button>
            <button
              onClick={() => {
                setShowSaveTemplate(false)
                setTemplateName('')
                setTemplateDescr('')
              }}
              className="flex-1 px-4 py-2 bg-gray-300 dark:bg-gray-600 hover:bg-gray-400 dark:hover:bg-gray-500 text-gray-900 dark:text-white rounded-lg transition-colors font-medium"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Mapping Table */}
      {availableColumns.length > 0 ? (
        <div className="overflow-x-auto bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">DB Field</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Source Column</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Is Metric</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Dedup Strategy</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
              </tr>
            </thead>
            <tbody>
              {DB_TARGET_FIELDS.map((target) => {
                const selectedSource = targetLookup[target] || ''
                const isMatched = !!selectedSource
                const isMetric = dedupConfig.is_metric?.[target] || false
                const fieldStrategy = dedupConfig.field_strategies?.[target] || dedupConfig.default_strategy

                return (
                  <tr key={target} className="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 align-top">
                    <td className="px-6 py-4 text-sm text-gray-900 dark:text-white">
                      <p className="font-medium">{humanizeField(target)}</p>
                      <p className="font-mono text-xs text-gray-500 dark:text-gray-400 mt-1">{target}</p>
                    </td>
                    <td className="px-6 py-4">
                      <select
                        value={selectedSource}
                        onChange={(e) => handleFieldMappingChange(target, e.target.value)}
                        className="min-w-[240px] px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        <option value="">Unselected</option>
                        {availableColumns.map((column) => (
                          <option key={`${target}-${column}`} value={column}>{column}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-6 py-4">
                      <label className="inline-flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={isMetric}
                          onChange={(e) => handleToggleIsMetric(target, e.target.checked)}
                          className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                        <span className="text-xs text-gray-600 dark:text-gray-400">{isMetric ? 'Yes' : 'No'}</span>
                      </label>
                    </td>
                    <td className="px-6 py-4">
                      {isMetric ? (
                        <div className="min-w-[140px]">
                          <select
                            value={fieldStrategy}
                            onChange={(e) => handleChangeFieldStrategy(target, e.target.value)}
                            className="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                          >
                            {Object.entries(DEDUP_STRATEGIES).map(([key, { label }]) => (
                              <option key={key} value={key}>{label}</option>
                            ))}
                          </select>
                          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-xs">
                            {DEDUP_STRATEGIES[fieldStrategy as keyof typeof DEDUP_STRATEGIES].description}
                          </p>
                        </div>
                      ) : (
                        <span className="text-xs text-gray-500 dark:text-gray-400">N/A</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {isMatched ? (
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200">
                          ✓ Mapped
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200">
                          ⚠ Unmatched
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 border-dashed">
          <div className="flex flex-col items-center gap-3 py-12 px-4">
            <p className="text-gray-600 dark:text-gray-400 text-sm text-center">No source columns available yet. Upload a sample file or add columns manually above.</p>
            <button
              onClick={handleAddColumns}
              disabled={!columnInput.trim()}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
            >
              <Plus size={14} />
              Add Columns
            </button>
          </div>
        </div>
      )}

      {/* Save Button */}
      {availableColumns.length > 0 && (
        <button
          onClick={handleSaveMapping}
          disabled={isSaving}
          className="flex items-center gap-2 px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg transition-colors font-medium ml-auto"
        >
          <Save size={16} />
          {isSaving ? 'Saving...' : 'Save Mapping'}
        </button>
      )}
    </div>
  )
}
