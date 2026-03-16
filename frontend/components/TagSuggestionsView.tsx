'use client'

import { OrchestratorResponse, TagSuggestion } from '@/types'
import { saveTags } from '@/lib/api'
import { Tag, Copy, Download, Clock, Save, Loader, AlertCircle } from 'lucide-react'
import { useState } from 'react'

interface TagSuggestionsViewProps {
    data: OrchestratorResponse['data']
    metadata: OrchestratorResponse['metadata']
}

export default function TagSuggestionsView({ data, metadata }: TagSuggestionsViewProps) {
    const [copiedIndex, setCopiedIndex] = useState<number | null>(null)
    const [savedIndex, setSavedIndex] = useState<number | null>(null)
    const [isSaving, setIsSaving] = useState<boolean>(false)
    const [saveError, setSaveError] = useState<string | null>(null)

    const tags = data.results || []
    const articleId = data.article_id
    const hasArticleId = !!articleId

    const getScoreColor = (score: number) => {
        if (score >= 0.4) return 'bg-green-100 text-green-800 border-green-300'
        if (score >= 0.25) return 'bg-blue-100 text-blue-800 border-blue-300'
        if (score >= 0.15) return 'bg-yellow-100 text-yellow-800 border-yellow-300'
        return 'bg-gray-100 text-gray-800 border-gray-300'
    }

    const copyTag = (tag: TagSuggestion, index: number) => {
        navigator.clipboard.writeText(tag.slug)
        setCopiedIndex(index)
        setTimeout(() => setCopiedIndex(null), 2000)
    }

    const saveTag = async (tag: TagSuggestion, index: number) => {
        if (!articleId) return

        setSavedIndex(index)
        setIsSaving(true)
        setSaveError(null)

        try {
            const response = await saveTags(articleId, [{ slug: tag.slug, text: tag.name }])
            if (!response.success) {
                throw new Error(response.message || 'Failed to save tag')
            }
            setTimeout(() => {
                setIsSaving(false)
                setTimeout(() => setSavedIndex(null), 2000)
            }, 500)
        } catch (error) {
            setIsSaving(false)
            setSavedIndex(null)
            setSaveError(error instanceof Error ? error.message : 'Failed to save tag')
            setTimeout(() => setSaveError(null), 5000)
        }
    }

    const copyAllTags = () => {
        const tagSlugs = tags.map(t => t.slug).join(', ')
        navigator.clipboard.writeText(tagSlugs)
        setCopiedIndex(-1)
        setTimeout(() => setCopiedIndex(null), 2000)
    }

    const saveAllTags = async () => {
        if (!articleId) return

        setIsSaving(true)
        setSavedIndex(-1)
        setSaveError(null)

        try {
            const tagSlugs = tags.map(t => ({
                slug: t.slug,
                text: t.name
            }))
            const response = await saveTags(articleId, tagSlugs)
            if (!response.success) {
                throw new Error(response.message || 'Failed to save tags')
            }
            setIsSaving(false)
            setTimeout(() => {
                setTimeout(() => setSavedIndex(null), 2000)
            }, 500)
        } catch (error) {
            setIsSaving(false)
            setSavedIndex(null)
            setSaveError(error instanceof Error ? error.message : 'Failed to save tags')
            setTimeout(() => setSaveError(null), 5000)
        }
    }

    const exportTags = () => {
        const json = JSON.stringify(tags, null, 2)
        const blob = new Blob([json], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `tags-${Date.now()}.json`
        a.click()
        URL.revokeObjectURL(url)
    }

    if (!tags.length) {
        return (
            <div className="mt-4 p-4 bg-gray-50 rounded-lg text-gray-600 text-sm">
                No tags found.
            </div>
        )
    }

    return (
        <div className="mt-4">
            {/* Header */}
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Tag size={18} className="text-blue-600" />
                    <h3 className="font-semibold text-gray-900">
                        Suggested Tags ({data.count || tags.length})
                    </h3>
                    {metadata.source && (
                        <span className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded">
                            {metadata.source}
                        </span>
                    )}
                    {metadata.duration_ms && (
                        <span className="text-xs text-gray-500 flex items-center gap-1">
                            <Clock size={12} />
                            {metadata.duration_ms}ms
                        </span>
                    )}
                </div>

                <div className="flex gap-2">
                    <button
                        onClick={copyAllTags}
                        className="text-xs px-3 py-1.5 bg-blue-50 text-blue-700 rounded-md hover:bg-blue-100 transition-colors flex items-center gap-1"
                    >
                        <Copy size={12} />
                        {copiedIndex === -1 ? 'Copied!' : 'Copy All'}
                    </button>
                    {data.article_id ? <button
                        onClick={saveAllTags}
                        className="text-xs px-3 py-1.5 bg-blue-50 text-blue-700 rounded-md hover:bg-blue-100 transition-colors flex items-center gap-1 disabled:opacity-50"
                        disabled={isSaving || savedIndex === -1}
                    >
                        {savedIndex === -1 && isSaving ? <Loader size={14} className='animate-spin' /> : <Save size={12} />}
                        {
                            savedIndex === -1 ? <>
                                {isSaving ? 'Saving...' : 'Saved!'}
                            </> : 'Save All'
                        }

                        {/* {isSaving ? <>
                            Saving...
                        </> : <>
                            {savedIndex === -1 ? 'Saved!' : 'Save All'}
                        </>} */}
                    </button> : null}

                    {/* <button
                        onClick={exportTags}
                        className="text-xs px-3 py-1.5 bg-gray-50 text-gray-700 rounded-md hover:bg-gray-100 transition-colors flex items-center gap-1"
                    >
                        <Download size={12} />
                        Export JSON
                    </button> */}
                </div>
            </div>

            {/* Error Alert */}
            {saveError && (
                <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
                    <AlertCircle size={16} className="text-red-600 flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                        <p className="text-sm text-red-800 font-medium">Failed to save tags</p>
                        <p className="text-xs text-red-600 mt-1">{saveError}</p>
                    </div>
                </div>
            )}

            {/* Tags Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {tags.map((tag, index) => (
                    <div
                        key={tag.slug}
                        className={`p-3 rounded-lg border-2 ${getScoreColor(tag.score)} transition-all hover:shadow-md`}
                    >
                        <div className="flex items-start justify-between gap-2">
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                    <h4 className="font-semibold text-sm truncate">{tag.name}</h4>
                                    {tag.is_primary && (
                                        <span className="text-xs px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded">
                                            Primary
                                        </span>
                                    )}
                                </div>
                                {/* <p className="text-xs font-mono text-gray-600 mb-2">{tag.slug}</p> */}
                                <div className="flex items-center gap-2 mb-2">
                                    <span className="text-xs font-semibold">Score:</span>
                                    <span className="text-xs font-mono">{tag.score.toFixed(3)}</span>
                                </div>
                                {tag.reason && (
                                    <p className="text-xs text-gray-600 italic">{tag.reason}</p>
                                )}
                            </div>

                            <button
                                onClick={() => copyTag(tag, index)}
                                className="flex-shrink-0 p-1.5 hover:bg-white/50 rounded transition-colors"
                                title="Copy slug"
                            >
                                <Copy size={14} />
                            </button>
                            {hasArticleId && (
                                <button
                                    onClick={() => saveTag(tag, index)}
                                    className="flex-shrink-0 p-1.5 hover:bg-white/50 rounded transition-colors disabled:opacity-50"
                                    disabled={isSaving || savedIndex === index}
                                    title="Save To Article"
                                >
                                    {(savedIndex === index && isSaving) ? <Loader size={14} className='animate-spin' /> : <Save size={14} />}
                                </button>
                            )}
                        </div>

                        {copiedIndex === index && (
                            <div className="text-xs text-green-600 mt-2 font-medium">
                                ✓ Copied!
                            </div>
                        )}
                        {
                            savedIndex === index && <>
                                {isSaving ? <div className="text-xs text-green-600 mt-2 font-medium">
                                    Saving...
                                </div> : <div className="text-xs text-green-600 mt-2 font-medium">
                                    ✓ Saved!
                                </div>}
                            </>
                        }
                    </div>
                ))}
            </div>

            {/* Article ID (if present) */}
            {data.article_id && (
                <div className="mt-4 p-3 bg-blue-50 rounded-lg">
                    <span className="text-xs text-blue-700 font-medium">Article ID: </span>
                    <span className="text-xs text-blue-900 font-mono">{data.article_id}</span>
                </div>
            )}
        </div>
    )
}
