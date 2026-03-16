'use client'

import { OrchestratorResponse } from '@/types'
import { FileCode, Clock, Copy, BarChart3 } from 'lucide-react'
import { useState } from 'react'
import SingleResultCard from './SingleResultCard'

interface QueryDocumentsViewProps {
    data: OrchestratorResponse['data']
    metadata: OrchestratorResponse['metadata']
}

export default function QueryDocumentsView({ data, metadata }: QueryDocumentsViewProps) {
    const [copied, setCopied] = useState(false)

    const labelMap: Record<string, string> = {
        content_id: 'Content ID',
        platform: 'Platform',
        content_type: 'Content Type',
        media_type: 'Media Type',
        profile_name: 'Profile',
        author_name: 'Author',
        view_on_platform: 'View on Platform',
        video_views: 'Video Views',
        total_impressions: 'Total Impressions',
        organic_impressions: 'Organic Impressions',
        paid_impressions: 'Paid Impressions',
        total_reactions: 'Total Reactions',
        total_likes: 'Total Likes',
        total_comments: 'Total Comments',
        total_shares: 'Total Shares',
        total_interactions: 'Total Interactions',
        organic_interactions: 'Organic Interactions',
        engagements: 'Engagements',
        total_reach: 'Total Reach',
        organic_reach: 'Organic Reach',
        paid_reach: 'Paid Reach',
        reach_engagement_rate: 'Reach Engagement Rate',
        video_length_sec: 'Video Length (sec)',
        total_video_view_time_sec: 'Total Video View Time (sec)',
        avg_video_view_time_sec: 'Average Video View Time (sec)',
        completion_rate: 'Completion Rate',
        label_groups: 'Label Groups',
    }

    const formatLabel = (key: string) => labelMap[key] || key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())

    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
    }

    // Check if we have actual results from database
    const hasResults = data.results && Array.isArray(data.results) && data.results.length > 0
    const isAggregated = data.is_aggregated === true
    const isSingleResult = hasResults && !isAggregated && data.results?.length === 1

    // Check if answer is JSON (refined query)
    const isJsonAnswer = data.answer && (data.answer.startsWith('{') || data.answer.startsWith('['))

    return (
        <div className="mt-4 space-y-4">
            {/* Single Result - Fancy Card Display */}
            {isSingleResult && (
                <SingleResultCard result={data.results?.[0]} metadata={metadata} />
            )}

            {/* Database Results (Multiple or Aggregated) */}
            {hasResults && !isSingleResult && (
                <div className="rounded-lg border border-green-200 overflow-hidden mb-2">
                    {/* <div className="bg-green-50 px-4 py-2 flex items-center justify-between border-b border-green-200">
                        <div className="flex items-center gap-2">
                            <BarChart3 size={16} className="text-green-700" />
                            <span className="text-sm font-semibold text-green-900">
                                {isAggregated ? 'Aggregated Results' : 'Query Results'}
                            </span>
                            <span className="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded">
                                {data.count} {isAggregated ? 'group(s)' : 'result(s)'}
                            </span>
                            {metadata.duration_ms && (
                                <span className="text-xs text-green-600 flex items-center gap-1">
                                    <Clock size={12} />
                                    {metadata.duration_ms}ms
                                </span>
                            )}
                        </div>

                        <button
                            onClick={() => copyToClipboard(JSON.stringify(data.results, null, 2))}
                            className="text-xs px-2 py-1 bg-white hover:bg-green-100 text-green-700 rounded flex items-center gap-1 transition-colors"
                        >
                            <Copy size={12} />
                            {copied ? 'Copied!' : 'Copy JSON'}
                        </button>
                    </div> */}

                    <div className="p-4 bg-white">
                        {isAggregated ? (
                            <div className="space-y-3">
                                {(data.results || []).map((result: any, idx: number) => (
                                    <div key={idx} className="p-3 bg-green-50 rounded-lg border border-green-200">
                                        <div className="flex items-center justify-between mb-2">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                {Object.entries(result).map(([key, value]) => {
                                                    if (key.startsWith('_') || !String(value)) return null
                                                    return (
                                                        <span key={key} className="text-xs px-2 py-1 bg-white rounded border border-green-300">
                                                            <span className="font-semibold text-green-900">{formatLabel(key)}:</span>{' '}
                                                            <span className="text-green-700">{typeof value === 'number' ? value.toLocaleString('en-US') : String(value)}</span>
                                                        </span>
                                                    )
                                                })}
                                            </div>
                                        </div>
                                        {result._aggregated_count ? <div className="flex items-center gap-4">
                                            <div className="text-2xl font-bold text-green-900">
                                                {result._aggregated_total?.toLocaleString() || 0}
                                            </div>
                                            <div className="text-xs text-green-600">
                                                {/* {result._aggregation_type} of {result._aggregation_metric} */}
                                                Based on
                                                <span className="text-gray-500 ml-2">({result._aggregated_count} records)</span>
                                            </div>
                                        </div> : null}
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="space-y-4">
                                {(data.results || []).map((result: any, idx: number) => {
                                    // Filter out null, undefined, empty string values
                                    const validEntries = Object.entries(result).filter(([key, value]) => {
                                        if (value === null || value === undefined || value === '') return false
                                        if (typeof value === 'string' && value.trim() === '') return false
                                        return true
                                    })

                                    // Categorize fields
                                    const metaFields = ['id', 'sheet_name', 'row_number', 'distance']
                                    const highlightFields = ['platform', 'content_type', 'media_type', 'date', 'profile_name', 'author_name']
                                    const metricFields = ['video_views', 'total_impressions', 'total_reactions', 'total_comments', 'total_shares', 'total_interactions', 'total_reach', 'engagements']
                                    const contentFields = ['title', 'description', 'content']

                                    // Color schemes for cards (cycle through them)
                                    const colorSchemes = [
                                        { bg: 'bg-gradient-to-br from-blue-50 via-white to-indigo-50', border: 'border-blue-300', hover: 'hover:border-blue-400', badge: 'bg-gradient-to-r from-blue-500 to-indigo-600' },
                                        { bg: 'bg-gradient-to-br from-purple-50 via-white to-pink-50', border: 'border-purple-300', hover: 'hover:border-purple-400', badge: 'bg-gradient-to-r from-purple-500 to-pink-600' },
                                        { bg: 'bg-gradient-to-br from-green-50 via-white to-emerald-50', border: 'border-green-300', hover: 'hover:border-green-400', badge: 'bg-gradient-to-r from-green-500 to-emerald-600' },
                                        { bg: 'bg-gradient-to-br from-orange-50 via-white to-amber-50', border: 'border-orange-300', hover: 'hover:border-orange-400', badge: 'bg-gradient-to-r from-orange-500 to-amber-600' },
                                        { bg: 'bg-gradient-to-br from-cyan-50 via-white to-teal-50', border: 'border-cyan-300', hover: 'hover:border-cyan-400', badge: 'bg-gradient-to-r from-cyan-500 to-teal-600' },
                                    ]
                                    const colors = colorSchemes[idx % colorSchemes.length]

                                    // Metric color mapping
                                    const metricColors: Record<string, { bg: string, text: string, border: string }> = {
                                        'video_views': { bg: 'bg-blue-50', text: 'text-blue-900', border: 'border-blue-200' },
                                        'total_impressions': { bg: 'bg-purple-50', text: 'text-purple-900', border: 'border-purple-200' },
                                        'total_reactions': { bg: 'bg-red-50', text: 'text-red-900', border: 'border-red-200' },
                                        'total_comments': { bg: 'bg-green-50', text: 'text-green-900', border: 'border-green-200' },
                                        'total_shares': { bg: 'bg-orange-50', text: 'text-orange-900', border: 'border-orange-200' },
                                        'total_interactions': { bg: 'bg-indigo-50', text: 'text-indigo-900', border: 'border-indigo-200' },
                                        'total_reach': { bg: 'bg-cyan-50', text: 'text-cyan-900', border: 'border-cyan-200' },
                                        'engagements': { bg: 'bg-pink-50', text: 'text-pink-900', border: 'border-pink-200' },
                                    }

                                    return (
                                        <div key={idx} className={`p-4 ${colors.bg} rounded-xl border-2 ${colors.border} ${colors.hover} transition-all shadow-sm hover:shadow-md`}>
                                            <div className="flex items-start justify-between mb-3">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    {validEntries.filter(([key]) => highlightFields.includes(key)).map(([key, value]) => (
                                                        <span key={key} className={`text-xs px-3 py-1.5 ${colors.badge} text-white rounded-full font-medium shadow-sm`}>
                                                            {key === 'profile_name' ? '👤' : key === 'platform' ? '📱' : key === 'date' ? '📅' : ''} {String(value)}
                                                        </span>
                                                    ))}
                                                </div>
                                                <span className="text-xs text-gray-500 font-mono bg-white px-2 py-1 rounded">#{idx + 1}</span>
                                            </div>

                                            {/* Content Fields */}
                                            {validEntries.filter(([key]) => contentFields.includes(key)).length > 0 && (
                                                <div className="mb-3 space-y-2">
                                                    {validEntries.filter(([key]) => contentFields.includes(key)).map(([key, value]) => (
                                                        <div key={key}>
                                                            {key === 'content' || (String(value).length > 100) ? (
                                                                <div className="p-3 bg-white/80 backdrop-blur rounded-lg border border-gray-200 shadow-sm">
                                                                    <div className="text-xs font-semibold text-gray-600 mb-1 uppercase">{formatLabel(key)}</div>
                                                                    <p className="text-sm text-gray-800 leading-relaxed">{String(value)}</p>
                                                                </div>
                                                            ) : (
                                                                <div className="p-2 bg-white/50 rounded">
                                                                    <span className="text-xs font-semibold text-gray-600 uppercase">{formatLabel(key)}: </span>
                                                                    <span className="text-sm text-gray-800 font-medium">{String(value)}</span>
                                                                </div>
                                                            )}
                                                        </div>
                                                    ))}
                                                </div>
                                            )}

                                            {/* Metrics */}
                                            {validEntries.filter(([key]) => metricFields.includes(key)).length > 0 && (
                                                <div className="mb-3">
                                                    <div className="text-xs font-bold text-gray-700 mb-2 uppercase tracking-wide flex items-center gap-2">
                                                        📊 Performance Metrics
                                                    </div>
                                                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                                                        {validEntries.filter(([key]) => metricFields.includes(key)).map(([key, value]) => {
                                                            const metricColor = metricColors[key] || { bg: 'bg-gray-50', text: 'text-gray-900', border: 'border-gray-200' }
                                                            return (
                                                                <div key={key} className={`p-3 ${metricColor.bg} rounded-lg border ${metricColor.border} shadow-sm hover:shadow transition-shadow`}>
                                                                    <div className="text-xs text-gray-600 mb-1 font-medium">
                                                                        {formatLabel(key)}
                                                                    </div>
                                                                    <div className={`text-lg font-bold ${metricColor.text}`}>
                                                                        {typeof value === 'number' ? value.toLocaleString('en-US') : String(value)}
                                                                    </div>
                                                                </div>
                                                            )
                                                        })}
                                                    </div>
                                                </div>
                                            )}

                                            {/* All Other Fields */}
                                            {validEntries.filter(([key]) =>
                                                !metaFields.includes(key) &&
                                                !highlightFields.includes(key) &&
                                                !metricFields.includes(key) &&
                                                !contentFields.includes(key)
                                            ).length > 0 && (<>
                                                {/* <details className="text-xs bg-white/50 rounded-lg p-3">
                                                    <summary className="cursor-pointer text-gray-700 hover:text-gray-900 font-semibold mb-2 flex items-center gap-2">
                                                        <span>📋 Additional Fields</span>
                                                        <span className="px-2 py-0.5 bg-gray-200 text-gray-700 rounded-full text-xs">
                                                            {validEntries.filter(([key]) =>
                                                                !metaFields.includes(key) &&
                                                                !highlightFields.includes(key) &&
                                                                !metricFields.includes(key) &&
                                                                !contentFields.includes(key)
                                                            ).length}
                                                        </span>
                                                    </summary>
                                                    <div className="mt-2 space-y-2 pl-4 border-l-2 border-gray-300">
                                                        {validEntries.filter(([key]) =>
                                                            !metaFields.includes(key) &&
                                                            !highlightFields.includes(key) &&
                                                            !metricFields.includes(key) &&
                                                            !contentFields.includes(key)
                                                        ).map(([key, value]) => (
                                                            <div key={key} className="flex items-start gap-2 p-2 bg-white rounded">
                                                                <span className="font-semibold text-gray-700 min-w-[120px]">
                                                                    {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}:
                                                                </span>
                                                                <span className="text-gray-600 break-all">
                                                                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                                                </span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </details> */}
                                                {validEntries.filter(([key]) =>
                                                    !metaFields.includes(key) &&
                                                    !highlightFields.includes(key) &&
                                                    !metricFields.includes(key) &&
                                                    !contentFields.includes(key)
                                                ).map(([key, value]) => (
                                                    <div key={key} className="flex items-start gap-2 p-2 bg-white rounded">
                                                        <span className="font-semibold text-gray-700 min-w-[120px]">
                                                            {formatLabel(key)}:
                                                        </span>
                                                        <span className="text-gray-600 break-all">
                                                            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                                        </span>
                                                    </div>
                                                ))}
                                            </>
                                                )}

                                            {/* View Link */}
                                            {validEntries.find(([key]) => key === 'view_on_platform') && (
                                                <div className="mt-3 pt-3 border-t border-white/50">
                                                    <a
                                                        href={String(result.view_on_platform)}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className={`inline-flex items-center gap-2 px-4 py-2 ${colors.badge} text-white text-sm font-medium rounded-lg hover:shadow-lg transition-all`}
                                                    >
                                                        🔗 View on Platform
                                                    </a>
                                                </div>
                                            )}
                                        </div>
                                    )
                                })}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Refined Query / Answer */}
            {data.answer && !hasResults && (
                <div className="rounded-lg border border-gray-200 overflow-hidden">
                    {/* <div className="bg-gray-50 px-4 py-2 flex items-center justify-between border-b border-gray-200">
                        <div className="flex items-center gap-2">
                            <FileCode size={16} className="text-gray-600" />
                            <span className="text-sm font-semibold text-gray-700">
                                {isJsonAnswer ? 'Structured Query' : 'Refined Query'}
                            </span>
                            {metadata.refinement_type && (
                                <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded">
                                    {metadata.refinement_type}
                                </span>
                            )}
                            {metadata.duration_ms && (
                                <span className="text-xs text-gray-500 flex items-center gap-1">
                                    <Clock size={12} />
                                    {metadata.duration_ms}ms
                                </span>
                            )}
                        </div>

                        <button
                            onClick={() => copyToClipboard(data.answer || '')}
                            className="text-xs px-2 py-1 bg-white hover:bg-gray-100 text-gray-700 rounded flex items-center gap-1 transition-colors"
                        >
                            <Copy size={12} />
                            {copied ? 'Copied!' : 'Copy'}
                        </button>
                    </div> */}

                    {/* <div className="p-4 bg-white">
                        {isJsonAnswer ? (
                            <pre className="text-xs font-mono text-gray-800 overflow-x-auto whitespace-pre-wrap">
                                {JSON.stringify(JSON.parse(data.answer), null, 2)}
                            </pre>
                        ) : (
                            <p className="text-sm text-gray-800">{data.answer}</p>
                        )}
                    </div> */}
                </div>
            )}

            {/* Note */}
            {data.note && (
                <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                    <p className="text-xs text-blue-800">
                        ℹ️ {data.note}
                    </p>
                </div>
            )}

            {/* Original Query (if different) */}
            {data.original_query && data.answer !== data.original_query && (
                <details className="text-xs text-gray-600">
                    <summary className="cursor-pointer hover:text-gray-900 font-medium">
                        Original Query
                    </summary>
                    <p className="mt-2 pl-4 border-l-2 border-gray-300">
                        {data.original_query}
                    </p>
                </details>
            )}
        </div>
    )
}
