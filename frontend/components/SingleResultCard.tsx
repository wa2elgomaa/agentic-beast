'use client'

import { formatNumber } from '@/lib/api'
import { TrendingUp, Eye, MessageCircle, Heart, Share2, Calendar, User, ExternalLink, Video, FileText, Clock, Copy } from 'lucide-react'

interface SingleResultCardProps {
    result: any
    metadata?: any
}

export default function SingleResultCard({ result, metadata }: SingleResultCardProps) {

    const formatLabel = (key: string): string => {
        return key
            .replace(/_/g, ' ')
            .replace(/([a-z])([A-Z])/g, '$1 $2')
            .replace(/\b\w/g, char => char.toUpperCase())
    }

    const formatDate = (dateStr: string | null | undefined): string => {
        if (!dateStr) return ''
        try {
            const date = new Date(dateStr)
            return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
        } catch {
            return dateStr
        }
    }

    const outboundUrl = String(
        result.view_url || result.view_on_platform || result.link_url || ''
    ).trim()

    const normalizedTitle = String(result.title || '').trim()
    const normalizedDescription = String(result.description || '').trim()
    const normalizedContent = String(result.content || '').trim()

    const primaryBodyText = [normalizedDescription, normalizedContent]
        .find(text => text && text !== normalizedTitle) || ''

    const detailRows = [
        { key: 'label', label: 'Label', value: String(result.label || '').trim() },
        { key: 'view_url', label: 'View', value: String(result.view_url || '').trim() },
        { key: 'value', label: 'Value', value: String(result.value || '').trim() },
        { key: 'published_at', label: 'Published', value: formatDate(result.published_at || result.date) },
    ].filter(row => row.value && row.value !== normalizedTitle && row.value !== primaryBodyText)


    const contentType = result.content_type || result.media_type || 'post'
    const isVideo = contentType.toLowerCase().includes('video') || result.video_views != null

    return (
        <div className="rounded-xl border-2 border-blue-200 bg-gradient-to-br from-blue-50 via-white to-purple-50 overflow-hidden shadow-lg hover:shadow-2xl transition-all duration-300">
            {/* Header */}
            <div className="bg-gradient-to-r from-blue-600 via-blue-700 to-purple-600 px-6 py-4">
                <div className="flex items-start justify-between">
                    <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                            {isVideo ? (
                                <Video size={20} className="text-white" />
                            ) : (
                                <FileText size={20} className="text-white" />
                            )}
                            <span className="text-white text-xs font-semibold uppercase tracking-wide">
                                {contentType}
                            </span>
                            {result.platform && (
                                <span className="px-2 py-1 bg-white/20 text-white text-xs rounded-full font-medium">
                                    {result.platform}
                                </span>
                            )}
                            {metadata?.duration_ms && (
                                <span className="text-white/80 text-xs flex items-center gap-1">
                                    <Clock size={12} />
                                    {metadata.duration_ms}ms
                                </span>
                            )}
                        </div>
                        {(result.title || result.content || "").trim() && (
                            outboundUrl ? (
                                <a
                                    href={outboundUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-white font-bold text-xl mb-1 leading-tight underline decoration-white/40 hover:decoration-white"
                                    title="Open post"
                                >
                                    {result.title || result.content}
                                </a>
                            ) : (
                                <h3 className="text-white font-bold text-xl mb-1 leading-tight">
                                    {result.title || result.content}
                                </h3>
                            )
                        )}
                    </div>
                    <div className="flex items-center gap-2">
                        {outboundUrl && (
                            <a
                                href={outboundUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="p-2 hover:bg-white/20 rounded-lg transition-colors"
                                title="View on platform"
                            >
                                <ExternalLink size={18} className="text-white" />
                            </a>
                        )}
                    </div>
                </div>
            </div>

            {/* Content */}
            <div className="px-6 py-5">
                {primaryBodyText && (
                    <div className="mb-4 p-4 bg-white rounded-lg border border-gray-200 shadow-sm">
                        <p className="text-gray-700 text-sm leading-relaxed">{primaryBodyText}</p>
                    </div>
                )}

                {detailRows.length > 0 && (
                    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden mb-4">
                        {detailRows.map((row) => row.value ? (
                            <div key={row.key} className="grid grid-cols-[110px,1fr] gap-3 px-4 py-3 border-b border-gray-100 last:border-b-0">
                                <span className="text-xs text-gray-600 font-semibold uppercase tracking-wide">{row.label}</span>
                                <span className="text-sm text-gray-800 font-medium break-words">
                                    {isNaN(Number(row.value)) ? row.value : formatNumber(row.value)}
                                </span>
                            </div>
                        ) : null)}
                    </div>
                )}
                {/* {result.content && result.content.trim() && (
                    <div className="mb-5 p-4 bg-white rounded-lg border border-gray-200 shadow-sm">
                        <p className="text-gray-700 text-sm leading-relaxed">
                            {result.content}
                        </p>
                    </div>
                )} */}

                {/* Metrics Grid */}
                {/* {metrics.length > 0 && (
                    <div className="mb-5">
                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Performance Metrics</h4>
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                            {metrics.map((metric, idx) => {
                                const Icon = metric.icon
                                return (
                                    <div key={idx} className={`${metric.bgColor} rounded-xl p-4 border ${metric.borderColor} hover:shadow-md transition-shadow`}>
                                        <div className="flex items-center gap-2 mb-2">
                                            <Icon size={16} className={metric.color} />
                                            <span className="text-xs text-gray-600 font-medium">{metric.label}</span>
                                        </div>
                                        <div className={`text-2xl font-bold ${metric.color}`}>
                                            {formatNumber(metric.value)}
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                )} */}

                {/* Additional Metrics */}
                {/* {(result.total_interactions != null || result.total_reach != null || result.reach_engagement_rate != null) && (
                    <div className="mb-5">
                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Additional Insights</h4>
                        <div className="flex gap-3 flex-wrap">
                            {result.total_interactions != null && result.total_interactions > 0 && (
                                <div className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-50 to-indigo-100 rounded-lg border border-indigo-200">
                                    <TrendingUp size={16} className="text-indigo-600" />
                                    <span className="text-xs text-gray-600 font-medium">Interactions:</span>
                                    <span className="text-sm font-bold text-indigo-900">
                                        {formatNumber(result.total_interactions)}
                                    </span>
                                </div>
                            )}
                            {result.total_reach != null && result.total_reach > 0 && (
                                <div className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-cyan-50 to-cyan-100 rounded-lg border border-cyan-200">
                                    <Eye size={16} className="text-cyan-600" />
                                    <span className="text-xs text-gray-600 font-medium">Reach:</span>
                                    <span className="text-sm font-bold text-cyan-900">
                                        {formatNumber(result.total_reach)}
                                    </span>
                                </div>
                            )}
                            {result.reach_engagement_rate != null && (
                                <div className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-50 to-emerald-100 rounded-lg border border-emerald-200">
                                    <TrendingUp size={16} className="text-emerald-600" />
                                    <span className="text-xs text-gray-600 font-medium">Engagement Rate:</span>
                                    <span className="text-sm font-bold text-emerald-900">
                                        {(parseFloat(result.reach_engagement_rate) * 100).toFixed(2)}%
                                    </span>
                                </div>
                            )}
                        </div>
                    </div>
                )} */}

                {/* Video-specific metrics */}
                {/* {isVideo && (result.video_length_sec != null || result.completion_rate != null || result.avg_video_view_time_sec != null) && (
                    <div className="mb-5">
                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Video Analytics</h4>
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                            {result.video_length_sec != null && (
                                <div className="px-4 py-3 bg-gray-50 rounded-lg border border-gray-200">
                                    <div className="text-xs text-gray-600 mb-1">Duration</div>
                                    <div className="text-lg font-bold text-gray-900">
                                        {Math.floor(result.video_length_sec / 60)}:{(result.video_length_sec % 60).toString().padStart(2, '0')}
                                    </div>
                                </div>
                            )}
                            {result.completion_rate != null && (
                                <div className="px-4 py-3 bg-gray-50 rounded-lg border border-gray-200">
                                    <div className="text-xs text-gray-600 mb-1">Completion Rate</div>
                                    <div className="text-lg font-bold text-gray-900">
                                        {(parseFloat(result.completion_rate) * 100).toFixed(1)}%
                                    </div>
                                </div>
                            )}
                            {result.avg_video_view_time_sec != null && (
                                <div className="px-4 py-3 bg-gray-50 rounded-lg border border-gray-200">
                                    <div className="text-xs text-gray-600 mb-1">Avg View Time</div>
                                    <div className="text-lg font-bold text-gray-900">
                                        {Math.floor(result.avg_video_view_time_sec)}s
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )} */}

                {/* Meta Information */}
                {result.date ? <div className="flex flex-wrap gap-4 pt-4 border-t border-gray-200">
                    {result.date && (
                        <div className="flex items-center gap-2 text-sm text-gray-700">
                            <Calendar size={16} className="text-gray-400" />
                            <span className="font-medium">{formatDate(result.date)}</span>
                        </div>
                    )}
                </div> : null}

                {/* Labels */}
                {result.labels && result.labels.trim() && (
                    <div className="mt-4 pt-4 border-t border-gray-200">
                        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Labels</h4>
                        <div className="flex flex-wrap gap-2">
                            {result.labels.split(',').filter((l: string) => l.trim()).map((label: string, idx: number) => (
                                <span key={idx} className="px-3 py-1 bg-blue-100 text-blue-700 text-xs font-medium rounded-full">
                                    {label.trim()}
                                </span>
                            ))}
                        </div>
                    </div>
                )}

                {outboundUrl ? (
                    <div className="mt-4 pt-4 border-t border-gray-200">
                        <a
                            href={outboundUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-sm font-semibold transition-all"
                            title="View on platform"
                        >
                            <ExternalLink size={14} />
                            View on Platform
                        </a>
                    </div>
                ) : null}
            </div>
        </div>
    )
}
