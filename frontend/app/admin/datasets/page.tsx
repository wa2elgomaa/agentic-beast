'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { APIBaseURL, APIPrefix } from '@/constants/urls'
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle,
  ChevronRight,
  FileText,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  UploadCloud,
  Zap,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface DatasetResponse {
  id: string
  slug: string
  name: string
  description: string | null
  allowed_extensions: string[]
  file_count: number
  embedded_count: number
  created_at: string
  updated_at: string
  files?: DatasetFileResponse[]
}

interface DatasetFileResponse {
  id: string
  filename: string
  s3_key: string
  file_size_bytes: number
  content_type: string | null
  embed_status: string // pending | processing | embedded | failed
  embed_task_id: string | null
  chunks_created: number | null
  error: string | null
  uploaded_at: string
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const ALL_EXTENSIONS = ['.pdf', '.docx', '.txt', '.xlsx', '.csv', '.json', '.md']

function getAuthHeaders(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  return token
    ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
    : { 'Content-Type': 'application/json' }
}

function getBearerHeader(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function autoSlug(name: string) {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

function embedBadge(status: string) {
  const map: Record<string, { label: string; cls: string }> = {
    pending: { label: 'Pending', cls: 'bg-gray-100 text-gray-600' },
    processing: { label: 'Processing…', cls: 'bg-blue-100 text-blue-700' },
    embedded: { label: 'Embedded', cls: 'bg-green-100 text-green-700' },
    failed: { label: 'Failed', cls: 'bg-red-100 text-red-700' },
  }
  const info = map[status] ?? { label: status, cls: 'bg-gray-100 text-gray-600' }
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${info.cls}`}>
      {info.label}
    </span>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

type View = 'list' | 'detail' | 'create' | 'edit'

export default function DatasetsPage() {
  const [view, setView] = useState<View>('list')
  const [datasets, setDatasets] = useState<DatasetResponse[]>([])
  const [selectedDataset, setSelectedDataset] = useState<DatasetResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Create / edit form state
  const [formName, setFormName] = useState('')
  const [formSlug, setFormSlug] = useState('')
  const [formSlugManual, setFormSlugManual] = useState(false)
  const [formDescription, setFormDescription] = useState('')
  const [formExtensions, setFormExtensions] = useState<string[]>(['.pdf', '.docx', '.txt'])
  const [formSubmitting, setFormSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  // File upload state (detail view)
  const [isDragging, setIsDragging] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Embed state
  const [isEmbedding, setIsEmbedding] = useState(false)
  const [embedMessage, setEmbedMessage] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Delete confirmation
  const [deleteTarget, setDeleteTarget] = useState<DatasetResponse | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  // ── Load list ────────────────────────────────────────────────────────────────

  const loadDatasets = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${APIBaseURL}${APIPrefix}/admin/datasets`, {
        headers: getAuthHeaders(),
      })
      if (!res.ok) throw new Error(`Failed to load datasets (${res.status})`)
      const data = await res.json()
      setDatasets(data.datasets ?? data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadDatasets() }, [loadDatasets])

  // ── Load detail ──────────────────────────────────────────────────────────────

  const loadDetail = useCallback(async (slug: string) => {
    setError(null)
    try {
      const res = await fetch(`${APIBaseURL}${APIPrefix}/admin/datasets/${slug}`, {
        headers: getAuthHeaders(),
      })
      if (!res.ok) throw new Error(`Failed to load dataset (${res.status})`)
      const data: DatasetResponse = await res.json()
      setSelectedDataset(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    }
  }, [])

  // ── Create ───────────────────────────────────────────────────────────────────

  const openCreate = () => {
    setFormName('')
    setFormSlug('')
    setFormSlugManual(false)
    setFormDescription('')
    setFormExtensions(['.pdf', '.docx', '.txt'])
    setFormError(null)
    setView('create')
  }

  const handleNameChange = (val: string) => {
    setFormName(val)
    if (!formSlugManual) setFormSlug(autoSlug(val))
  }

  const handleCreate = async () => {
    if (!formName.trim()) { setFormError('Name is required'); return }
    if (!formSlug.match(/^[a-z0-9_-]+$/)) { setFormError('Slug must match ^[a-z0-9_-]+$'); return }
    if (formExtensions.length === 0) { setFormError('Select at least one file type'); return }
    setFormSubmitting(true)
    setFormError(null)
    try {
      const res = await fetch(`${APIBaseURL}${APIPrefix}/admin/datasets`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          name: formName.trim(),
          slug: formSlug,
          description: formDescription.trim() || null,
          allowed_extensions: formExtensions,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `Create failed (${res.status})`)
      }
      await loadDatasets()
      setView('list')
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setFormSubmitting(false)
    }
  }

  // ── Edit ─────────────────────────────────────────────────────────────────────

  const openEdit = (ds: DatasetResponse) => {
    setFormName(ds.name)
    setFormSlug(ds.slug)
    setFormSlugManual(true)
    setFormDescription(ds.description ?? '')
    setFormExtensions([...ds.allowed_extensions])
    setFormError(null)
    setSelectedDataset(ds)
    setView('edit')
  }

  const handleUpdate = async () => {
    if (!selectedDataset) return
    if (!formName.trim()) { setFormError('Name is required'); return }
    if (formExtensions.length === 0) { setFormError('Select at least one file type'); return }
    setFormSubmitting(true)
    setFormError(null)
    try {
      const res = await fetch(`${APIBaseURL}${APIPrefix}/admin/datasets/${selectedDataset.slug}`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          name: formName.trim(),
          description: formDescription.trim() || null,
          allowed_extensions: formExtensions,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `Update failed (${res.status})`)
      }
      await loadDatasets()
      await loadDetail(selectedDataset.slug)
      setView('detail')
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setFormSubmitting(false)
    }
  }

  // ── Delete ───────────────────────────────────────────────────────────────────

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      await fetch(`${APIBaseURL}${APIPrefix}/admin/datasets/${deleteTarget.slug}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      })
      setDeleteTarget(null)
      if (view === 'detail') setView('list')
      await loadDatasets()
    } catch {
      // silently ignore
    } finally {
      setIsDeleting(false)
    }
  }

  // ── Open detail ──────────────────────────────────────────────────────────────

  const openDetail = async (ds: DatasetResponse) => {
    setUploadError(null)
    setUploadSuccess(null)
    setEmbedMessage(null)
    setSelectedDataset(ds)
    setView('detail')
    await loadDetail(ds.slug)
  }

  // ── File upload ──────────────────────────────────────────────────────────────

  const uploadFile = useCallback(async (file: File) => {
    if (!selectedDataset) return
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()
    if (!selectedDataset.allowed_extensions.includes(ext)) {
      setUploadError(`File type "${ext}" not allowed. Allowed: ${selectedDataset.allowed_extensions.join(', ')}`)
      return
    }
    setUploadError(null)
    setUploadSuccess(null)
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await fetch(
        `${APIBaseURL}${APIPrefix}/admin/datasets/${selectedDataset.slug}/upload`,
        { method: 'POST', headers: getBearerHeader(), body: form }
      )
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `Upload failed (${res.status})`)
      }
      setUploadSuccess(`"${file.name}" uploaded successfully.`)
      await loadDetail(selectedDataset.slug)
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : 'Upload failed')
    }
  }, [selectedDataset, loadDetail])

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) await uploadFile(file)
  }, [uploadFile])

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) await uploadFile(file)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  // ── Embedding ────────────────────────────────────────────────────────────────

  const pollEmbedStatuses = useCallback((slug: string) => {
    const check = async () => {
      const ds = await fetch(`${APIBaseURL}${APIPrefix}/admin/datasets/${slug}`, {
        headers: getAuthHeaders(),
      }).then(r => r.json()).catch(() => null)
      if (!ds) { setIsEmbedding(false); return }
      setSelectedDataset(ds)
      const stillProcessing = (ds.files ?? []).some(
        (f: DatasetFileResponse) => f.embed_status === 'processing'
      )
      if (stillProcessing) {
        pollRef.current = setTimeout(() => pollEmbedStatuses(slug), 2000)
      } else {
        setIsEmbedding(false)
        await loadDatasets()
      }
    }
    check()
  }, [loadDatasets])

  const triggerEmbed = async () => {
    if (!selectedDataset) return
    setIsEmbedding(true)
    setEmbedMessage(null)
    try {
      const res = await fetch(
        `${APIBaseURL}${APIPrefix}/admin/datasets/${selectedDataset.slug}/embed`,
        { method: 'POST', headers: getAuthHeaders() }
      )
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `Embed failed (${res.status})`)
      }
      const data = await res.json()
      setEmbedMessage(`Embedding started: ${data.files_queued} file(s) queued.`)
      pollEmbedStatuses(selectedDataset.slug)
    } catch (e: unknown) {
      setEmbedMessage(e instanceof Error ? e.message : 'Embed trigger failed')
      setIsEmbedding(false)
    }
  }

  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current) }, [])

  // ── Extension toggle helper ───────────────────────────────────────────────────

  const toggleExt = (ext: string) => {
    setFormExtensions(prev =>
      prev.includes(ext) ? prev.filter(e => e !== ext) : [...prev, ext]
    )
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────────

  // ── List view ────────────────────────────────────────────────────────────────

  if (view === 'list') {
    return (
      <div className="p-6 max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Datasets</h1>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            <Plus size={16} /> New Dataset
          </button>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
            <AlertCircle size={16} /> {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20 text-gray-400">
            <Loader2 className="animate-spin" size={28} />
          </div>
        ) : datasets.length === 0 ? (
          <div className="rounded-xl border-2 border-dashed border-gray-200 py-20 text-center text-gray-400">
            <FileText size={40} className="mx-auto mb-3 opacity-40" />
            <p className="font-medium">No datasets yet</p>
            <p className="text-sm mt-1">Create a dataset to start organizing your documents.</p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {datasets.map(ds => (
              <div
                key={ds.id}
                className="group relative rounded-xl border border-gray-200 bg-white p-5 shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <h2 className="font-semibold text-gray-900 truncate">{ds.name}</h2>
                    <p className="text-xs text-gray-400 font-mono mt-0.5">{ds.slug}</p>
                    {ds.description && (
                      <p className="text-sm text-gray-500 mt-1 line-clamp-2">{ds.description}</p>
                    )}
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  {ds.allowed_extensions.map(ext => (
                    <span key={ext} className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600 font-mono">
                      {ext}
                    </span>
                  ))}
                </div>

                <div className="mt-3 flex items-center gap-4 text-sm text-gray-500">
                  <span>{ds.file_count} file{ds.file_count !== 1 ? 's' : ''}</span>
                  <span className="text-green-600">{ds.embedded_count} embedded</span>
                  {ds.file_count > ds.embedded_count && (
                    <span className="text-amber-600">{ds.file_count - ds.embedded_count} pending</span>
                  )}
                </div>

                <div className="mt-4 flex items-center gap-2">
                  <button
                    onClick={() => openDetail(ds)}
                    className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-100"
                  >
                    View Files <ChevronRight size={14} />
                  </button>
                  <button
                    onClick={() => openEdit(ds)}
                    className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
                    title="Edit"
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    onClick={() => setDeleteTarget(ds)}
                    className="rounded-lg p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600"
                    title="Delete"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Delete confirmation modal */}
        {deleteTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="rounded-xl bg-white p-6 shadow-xl w-full max-w-sm mx-4">
              <h3 className="font-semibold text-gray-900">Delete &quot;{deleteTarget.name}&quot;?</h3>
              <p className="mt-2 text-sm text-gray-500">
                This will permanently delete the dataset and its file records. S3 objects will remain intact.
              </p>
              <div className="mt-5 flex justify-end gap-3">
                <button
                  onClick={() => setDeleteTarget(null)}
                  className="rounded-lg border border-gray-200 px-4 py-2 text-sm hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmDelete}
                  disabled={isDeleting}
                  className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                >
                  {isDeleting && <Loader2 size={14} className="animate-spin" />}
                  Delete
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  // ── Create / Edit view ───────────────────────────────────────────────────────

  if (view === 'create' || view === 'edit') {
    const isEdit = view === 'edit'
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <button
          onClick={() => setView(isEdit ? 'detail' : 'list')}
          className="mb-5 flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800"
        >
          <ArrowLeft size={15} /> Back
        </button>

        <h1 className="text-2xl font-bold text-gray-900 mb-6">
          {isEdit ? 'Edit Dataset' : 'Create Dataset'}
        </h1>

        {formError && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
            <AlertCircle size={16} /> {formError}
          </div>
        )}

        <div className="space-y-5">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={formName}
              onChange={e => handleNameChange(e.target.value)}
              placeholder="My Org Documents"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Slug */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Slug <span className="text-red-500">*</span>
              <span className="ml-2 text-xs text-gray-400 font-normal">lowercase letters, numbers, hyphens, underscores</span>
            </label>
            <input
              type="text"
              value={formSlug}
              onChange={e => { setFormSlug(e.target.value); setFormSlugManual(true) }}
              placeholder="my-org-documents"
              disabled={isEdit}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
            />
            {isEdit && <p className="mt-1 text-xs text-gray-400">Slug cannot be changed after creation.</p>}
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              value={formDescription}
              onChange={e => setFormDescription(e.target.value)}
              rows={3}
              placeholder="Optional description…"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
            />
          </div>

          {/* Allowed Extensions */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Allowed File Types <span className="text-red-500">*</span>
            </label>
            <div className="flex flex-wrap gap-2">
              {ALL_EXTENSIONS.map(ext => (
                <button
                  key={ext}
                  type="button"
                  onClick={() => toggleExt(ext)}
                  className={`rounded-lg border px-3 py-1.5 text-sm font-mono transition-colors ${
                    formExtensions.includes(ext)
                      ? 'border-blue-500 bg-blue-50 text-blue-700'
                      : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'
                  }`}
                >
                  {ext}
                </button>
              ))}
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              onClick={() => setView(isEdit ? 'detail' : 'list')}
              className="rounded-lg border border-gray-200 px-4 py-2 text-sm hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={isEdit ? handleUpdate : handleCreate}
              disabled={formSubmitting}
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
            >
              {formSubmitting && <Loader2 size={14} className="animate-spin" />}
              {isEdit ? 'Save Changes' : 'Create Dataset'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ── Detail view ──────────────────────────────────────────────────────────────

  if (view === 'detail' && selectedDataset) {
    const files = selectedDataset.files ?? []
    const pendingCount = files.filter(f => f.embed_status === 'pending' || f.embed_status === 'failed').length

    return (
      <div className="p-6 max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <button
              onClick={() => setView('list')}
              className="mb-2 flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800"
            >
              <ArrowLeft size={15} /> All Datasets
            </button>
            <h1 className="text-2xl font-bold text-gray-900">{selectedDataset.name}</h1>
            <p className="text-sm text-gray-400 font-mono mt-0.5">{selectedDataset.slug}</p>
            {selectedDataset.description && (
              <p className="text-sm text-gray-500 mt-1">{selectedDataset.description}</p>
            )}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {selectedDataset.allowed_extensions.map(ext => (
                <span key={ext} className="rounded bg-gray-100 px-2 py-0.5 text-xs font-mono text-gray-600">{ext}</span>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <button
              onClick={() => openEdit(selectedDataset)}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm hover:bg-gray-50"
            >
              <Pencil size={14} /> Edit
            </button>
            <button
              onClick={() => setDeleteTarget(selectedDataset)}
              className="flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50"
            >
              <Trash2 size={14} /> Delete
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
            <AlertCircle size={16} /> {error}
          </div>
        )}

        {/* Upload area */}
        <div
          onDragOver={e => { e.preventDefault(); setIsDragging(true) }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`mb-6 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed py-10 transition-colors ${
            isDragging ? 'border-blue-400 bg-blue-50' : 'border-gray-200 bg-gray-50 hover:border-blue-300 hover:bg-blue-50/50'
          }`}
        >
          <UploadCloud size={32} className={`mb-2 ${isDragging ? 'text-blue-500' : 'text-gray-300'}`} />
          <p className="text-sm font-medium text-gray-600">
            Drop a file here or <span className="text-blue-600">click to browse</span>
          </p>
          <p className="mt-1 text-xs text-gray-400">
            Allowed: {selectedDataset.allowed_extensions.join(', ')}
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept={selectedDataset.allowed_extensions.join(',')}
            onChange={handleFileChange}
            className="hidden"
          />
        </div>

        {uploadError && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
            <AlertCircle size={16} /> {uploadError}
          </div>
        )}
        {uploadSuccess && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-green-50 p-3 text-sm text-green-700">
            <CheckCircle size={16} /> {uploadSuccess}
          </div>
        )}

        {/* Embed controls */}
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-800">
            Files
            <span className="ml-2 text-sm font-normal text-gray-400">
              {selectedDataset.file_count} total · {selectedDataset.embedded_count} embedded
            </span>
          </h2>
          <button
            onClick={triggerEmbed}
            disabled={isEmbedding || pendingCount === 0}
            className="flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
          >
            {isEmbedding ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
            {isEmbedding ? 'Embedding…' : `Run Embedding (${pendingCount})`}
          </button>
        </div>

        {embedMessage && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-700">
            <Zap size={15} /> {embedMessage}
          </div>
        )}

        {/* Files table */}
        {files.length === 0 ? (
          <div className="rounded-xl border-2 border-dashed border-gray-200 py-14 text-center text-gray-400">
            <FileText size={32} className="mx-auto mb-2 opacity-30" />
            <p className="text-sm">No files yet. Upload a file above.</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-gray-200">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-4 py-3 text-left">Filename</th>
                  <th className="px-4 py-3 text-left">Size</th>
                  <th className="px-4 py-3 text-left">Uploaded</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-right">Chunks</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {files.map(file => (
                  <tr key={file.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-800 max-w-xs truncate">
                      {file.filename}
                    </td>
                    <td className="px-4 py-3 text-gray-500">{formatBytes(file.file_size_bytes)}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {new Date(file.uploaded_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {embedBadge(file.embed_status)}
                        {file.error && (
                          <span className="text-xs text-red-500 truncate max-w-[120px]" title={file.error}>
                            {file.error}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right text-gray-500">
                      {file.chunks_created ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Delete confirmation modal */}
        {deleteTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="rounded-xl bg-white p-6 shadow-xl w-full max-w-sm mx-4">
              <h3 className="font-semibold text-gray-900">Delete &quot;{deleteTarget.name}&quot;?</h3>
              <p className="mt-2 text-sm text-gray-500">
                This will permanently delete the dataset and its file records. S3 objects will remain intact.
              </p>
              <div className="mt-5 flex justify-end gap-3">
                <button
                  onClick={() => setDeleteTarget(null)}
                  className="rounded-lg border border-gray-200 px-4 py-2 text-sm hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmDelete}
                  disabled={isDeleting}
                  className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                >
                  {isDeleting && <Loader2 size={14} className="animate-spin" />}
                  Delete
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  return null
}
