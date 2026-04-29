'use client'

import { useEffect, useRef, useState } from 'react'
import { APIBaseURL, APIPrefix } from '@/constants/urls'
import { Plus, Trash2, Pencil, AlertCircle, X, Check, UploadCloud, Zap, Loader2, CheckCircle } from 'lucide-react'

interface TagItem {
  slug: string
  name: string
  description: string | null
  variations: string[]
  is_primary: boolean
  embedding_dim: number | null
  created_at: string
  updated_at: string
}

function getAuthHeaders(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  return token ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' }
}

const emptyForm = { slug: '', name: '', description: '', variations: '', is_primary: false }

interface EmbedStatus {
  taskId: string
  status: string
  progress: number
  embedded: number
  total: number
}

export default function TagsPage() {
  const [tags, setTags] = useState<TagItem[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editingSlug, setEditingSlug] = useState<string | null>(null)
  const [form, setForm] = useState(emptyForm)
  const [isSaving, setIsSaving] = useState(false)

  // Bulk upload state
  const [isBulkUploading, setIsBulkUploading] = useState(false)
  const [bulkResult, setBulkResult] = useState<{ created: number; skipped: number; failed: number; errors: string[] } | null>(null)
  const bulkFileRef = useRef<HTMLInputElement>(null)

  // Re-embed state
  const [isEmbedding, setIsEmbedding] = useState(false)
  const [embedStatus, setEmbedStatus] = useState<EmbedStatus | null>(null)
  const embedPollRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    loadTags()
    return () => { if (embedPollRef.current) clearTimeout(embedPollRef.current) }
  }, [])

  const loadTags = async () => {
    try {
      setIsLoading(true)
      setError(null)
      const res = await fetch(`${APIBaseURL}${APIPrefix}/admin/tags?limit=100`, { headers: getAuthHeaders() })
      if (!res.ok) throw new Error(`Failed to load tags (${res.status})`)
      const data = await res.json()
      setTags(data.items || [])
      setTotal(data.total || 0)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tags')
    } finally {
      setIsLoading(false)
    }
  }

  const openCreate = () => {
    setEditingSlug(null)
    setForm(emptyForm)
    setShowForm(true)
  }

  const openEdit = (tag: TagItem) => {
    setEditingSlug(tag.slug)
    setForm({
      slug: tag.slug,
      name: tag.name,
      description: tag.description ?? '',
      variations: tag.variations.join(', '),
      is_primary: tag.is_primary,
    })
    setShowForm(true)
  }

  const handleSave = async () => {
    if (!form.name.trim()) { setError('Name is required'); return }
    if (!editingSlug && !form.slug.trim()) { setError('Slug is required'); return }

    setIsSaving(true)
    setError(null)
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        variations: form.variations.split(',').map(v => v.trim()).filter(Boolean),
        is_primary: form.is_primary,
        ...(editingSlug ? { re_embed: true } : { slug: form.slug.trim() }),
      }

      const url = editingSlug
        ? `${APIBaseURL}${APIPrefix}/admin/tags/${editingSlug}`
        : `${APIBaseURL}${APIPrefix}/admin/tags`
      const method = editingSlug ? 'PUT' : 'POST'

      const res = await fetch(url, { method, headers: getAuthHeaders(), body: JSON.stringify(payload) })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `Save failed (${res.status})`)
      }

      setShowForm(false)
      await loadTags()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async (slug: string) => {
    if (!confirm(`Delete tag "${slug}"?`)) return
    try {
      const res = await fetch(`${APIBaseURL}${APIPrefix}/admin/tags/${slug}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      })
      if (!res.ok) throw new Error(`Delete failed (${res.status})`)
      await loadTags()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  const handleBulkUpload = async (file: File) => {
    setIsBulkUploading(true)
    setError(null)
    setBulkResult(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
      const res = await fetch(`${APIBaseURL}${APIPrefix}/admin/tags/bulk-upload?auto_embed=true&skip_duplicates=true`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      })
      if (!res.ok) {
        const b = await res.json().catch(() => ({}))
        throw new Error(b.detail || `Upload failed (${res.status})`)
      }
      const data = await res.json()
      setBulkResult({ created: data.created_count, skipped: data.skipped_count, failed: data.failed_count, errors: data.errors || [] })
      await loadTags()
      if (data.embedding_task_id) pollEmbedStatus(data.embedding_task_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Bulk upload failed')
    } finally {
      setIsBulkUploading(false)
      if (bulkFileRef.current) bulkFileRef.current.value = ''
    }
  }

  const handleReEmbed = async () => {
    setIsEmbedding(true)
    setError(null)
    setEmbedStatus(null)
    try {
      const res = await fetch(`${APIBaseURL}${APIPrefix}/admin/tags/re-embed`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ tag_slugs: null, batch_size: 100 }),
      })
      if (!res.ok) {
        const b = await res.json().catch(() => ({}))
        throw new Error(b.detail || `Re-embed failed (${res.status})`)
      }
      const data = await res.json()
      pollEmbedStatus(data.task_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Re-embed failed')
      setIsEmbedding(false)
    }
  }

  const pollEmbedStatus = (taskId: string) => {
    const check = async () => {
      try {
        const res = await fetch(`${APIBaseURL}${APIPrefix}/admin/tags/embed-status/${taskId}`, { headers: getAuthHeaders() })
        if (!res.ok) return
        const data = await res.json()
        setEmbedStatus({ taskId, status: data.status, progress: data.progress_percent, embedded: data.embedded_count, total: data.total_count })
        if (data.status === 'completed' || data.status === 'failed') {
          setIsEmbedding(false)
          await loadTags()
        } else {
          embedPollRef.current = setTimeout(check, 2000)
        }
      } catch {
        setIsEmbedding(false)
      }
    }
    check()
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Tags</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            {total} tag{total !== 1 ? 's' : ''} — manage content tags and their embeddings
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* Bulk Upload */}
          <label className="flex items-center gap-2 px-3 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg text-sm cursor-pointer transition-colors">
            {isBulkUploading ? <Loader2 size={15} className="animate-spin" /> : <UploadCloud size={15} />}
            {isBulkUploading ? 'Uploading…' : 'Import CSV/XLSX'}
            <input
              ref={bulkFileRef}
              type="file"
              accept=".csv,.xlsx"
              className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) handleBulkUpload(f) }}
            />
          </label>
          {/* Re-Embed All */}
          <button
            onClick={handleReEmbed}
            disabled={isEmbedding}
            className="flex items-center gap-2 px-3 py-2 border border-amber-300 dark:border-amber-600 text-amber-700 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/20 disabled:opacity-40 rounded-lg text-sm transition-colors"
          >
            {isEmbedding ? <Loader2 size={15} className="animate-spin" /> : <Zap size={15} />}
            {isEmbedding ? 'Embedding…' : 'Re-Embed All'}
          </button>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors font-medium text-sm"
          >
            <Plus size={15} />
            New Tag
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400">
          <AlertCircle size={18} className="shrink-0" />
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="ml-auto"><X size={16} /></button>
        </div>
      )}

      {success && (
        <div className="flex items-center gap-2 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg text-green-700 dark:text-green-400 text-sm">
          <CheckCircle size={16} />{success}
        </div>
      )}

      {/* Bulk upload result */}
      {bulkResult && (
        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg text-sm">
          <div className="flex items-center gap-4">
            <span className="text-green-700 dark:text-green-400 font-medium">{bulkResult.created} created</span>
            <span className="text-gray-500">{bulkResult.skipped} skipped</span>
            {bulkResult.failed > 0 && <span className="text-red-600 dark:text-red-400">{bulkResult.failed} failed</span>}
            <button onClick={() => setBulkResult(null)} className="ml-auto text-gray-400 hover:text-gray-600"><X size={14} /></button>
          </div>
          {bulkResult.errors.length > 0 && (
            <ul className="mt-2 text-xs text-red-600 dark:text-red-400 list-disc list-inside space-y-0.5">
              {bulkResult.errors.slice(0, 5).map((e, i) => <li key={i}>{e}</li>)}
              {bulkResult.errors.length > 5 && <li>…and {bulkResult.errors.length - 5} more</li>}
            </ul>
          )}
        </div>
      )}

      {/* Embed progress */}
      {embedStatus && (
        <div className="p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg text-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="font-medium text-amber-800 dark:text-amber-300">
              {embedStatus.status === 'completed' ? 'Embedding complete' : `Embedding… ${embedStatus.embedded}/${embedStatus.total}`}
            </span>
            {embedStatus.status === 'completed' && (
              <button onClick={() => setEmbedStatus(null)} className="text-gray-400 hover:text-gray-600"><X size={14} /></button>
            )}
          </div>
          <div className="w-full bg-amber-200 dark:bg-amber-800 rounded-full h-1.5">
            <div className="bg-amber-500 h-1.5 rounded-full transition-all" style={{ width: `${embedStatus.progress}%` }} />
          </div>
        </div>
      )}

      {/* Create/Edit form */}
      {showForm && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 space-y-4">
          <h3 className="font-semibold text-gray-900 dark:text-white">
            {editingSlug ? `Edit "${editingSlug}"` : 'New Tag'}
          </h3>
          <div className="grid grid-cols-2 gap-4">
            {!editingSlug && (
              <div>
                <label className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1 block">Slug *</label>
                <input
                  value={form.slug}
                  onChange={e => setForm(p => ({ ...p, slug: e.target.value }))}
                  placeholder="e.g. artificial-intelligence"
                  className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}
            <div>
              <label className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1 block">Name *</label>
              <input
                value={form.name}
                onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                placeholder="Display name"
                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="col-span-2">
              <label className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1 block">Description</label>
              <input
                value={form.description}
                onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
                placeholder="Optional description"
                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="col-span-2">
              <label className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1 block">Variations (comma-separated)</label>
              <input
                value={form.variations}
                onChange={e => setForm(p => ({ ...p, variations: e.target.value }))}
                placeholder="e.g. AI, A.I., Artificial Intelligence"
                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_primary"
                checked={form.is_primary}
                onChange={e => setForm(p => ({ ...p, is_primary: e.target.checked }))}
                className="rounded"
              />
              <label htmlFor="is_primary" className="text-sm text-gray-700 dark:text-gray-300">Primary tag</label>
            </div>
          </div>
          <div className="flex gap-2 pt-2">
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium"
            >
              <Check size={15} />
              {isSaving ? 'Saving…' : 'Save'}
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg text-sm"
            >
              <X size={15} />
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Tags table */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-14 bg-gray-200 dark:bg-gray-700 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : tags.length === 0 ? (
        <div className="text-center py-16 text-gray-500 dark:text-gray-400">
          <p className="text-lg font-medium">No tags yet</p>
          <p className="text-sm mt-1">Create your first tag to get started.</p>
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-700/50 text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              <tr>
                <th className="px-6 py-3 text-left">Slug</th>
                <th className="px-6 py-3 text-left">Name</th>
                <th className="px-6 py-3 text-left">Variations</th>
                <th className="px-6 py-3 text-left">Primary</th>
                <th className="px-6 py-3 text-left">Embedding</th>
                <th className="px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {tags.map(tag => (
                <tr key={tag.slug} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                  <td className="px-6 py-4 font-mono text-gray-900 dark:text-white">{tag.slug}</td>
                  <td className="px-6 py-4 text-gray-700 dark:text-gray-300">{tag.name}</td>
                  <td className="px-6 py-4 text-gray-500 dark:text-gray-400">
                    {tag.variations.length > 0 ? tag.variations.slice(0, 3).join(', ') + (tag.variations.length > 3 ? '…' : '') : '—'}
                  </td>
                  <td className="px-6 py-4">
                    {tag.is_primary && <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded text-xs">primary</span>}
                  </td>
                  <td className="px-6 py-4 text-gray-500 dark:text-gray-400">
                    {tag.embedding_dim
                      ? <span className="text-green-600 dark:text-green-400 text-xs">{tag.embedding_dim}d</span>
                      : <span className="text-amber-600 dark:text-amber-400 text-xs">not embedded</span>
                    }
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {!tag.embedding_dim && (
                        <button
                          onClick={async () => {
                            try {
                              const res = await fetch(`${APIBaseURL}${APIPrefix}/admin/tags/re-embed`, {
                                method: 'POST',
                                headers: getAuthHeaders(),
                                body: JSON.stringify({ tag_slugs: [tag.slug], batch_size: 1 }),
                              })
                              if (!res.ok) throw new Error(`Embed failed (${res.status})`)
                              const data = await res.json()
                              setSuccess(`Embedding triggered for "${tag.slug}"`)
                              pollEmbedStatus(data.task_id)
                            } catch (e) {
                              setError(e instanceof Error ? e.message : 'Embed failed')
                            }
                          }}
                          className="p-1.5 text-amber-500 hover:text-amber-700 dark:hover:text-amber-300 rounded"
                          title="Trigger embedding"
                        >
                          <Zap size={14} />
                        </button>
                      )}
                      <button onClick={() => openEdit(tag)} className="p-1.5 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 rounded">
                        <Pencil size={15} />
                      </button>
                      <button onClick={() => handleDelete(tag.slug)} className="p-1.5 text-gray-400 hover:text-red-600 dark:hover:text-red-400 rounded">
                        <Trash2 size={15} />
                      </button>
                    </div>
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
