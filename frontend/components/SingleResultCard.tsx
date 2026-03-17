'use client'

import { formatNumber } from '@/lib/api'
import { TrendingUp, Eye, MessageCircle, Heart, Share2, Calendar, User, ExternalLink, Video, FileText, Clock, Copy } from 'lucide-react'
import { useState } from 'react'

interface SingleResultCardProps {
    result: any
    metadata?: any
}

export default function SingleResultCard({ result, metadata }: SingleResultCardProps) {
    const [copied, setCopied] = useState(false)


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

    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
    }

    const metrics = [
        { label: 'Video Views', value: result.video_views, icon: Eye, color: 'text-blue-600', bgColor: 'bg-blue-50', borderColor: 'border-blue-200' },
        { label: 'Impressions', value: result.total_impressions, icon: TrendingUp, color: 'text-purple-600', bgColor: 'bg-purple-50', borderColor: 'border-purple-200' },
        { label: 'Reactions', value: result.total_reactions, icon: Heart, color: 'text-red-600', bgColor: 'bg-red-50', borderColor: 'border-red-200' },
        { label: 'Comments', value: result.total_comments, icon: MessageCircle, color: 'text-green-600', bgColor: 'bg-green-50', borderColor: 'border-green-200' },
        { label: 'Shares', value: result.total_shares, icon: Share2, color: 'text-orange-600', bgColor: 'bg-orange-50', borderColor: 'border-orange-200' },
    ].filter(m => m.value != null && m.value > 0)

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
                        {result.title && result.title.trim() && (
                            <h3 className="text-white font-bold text-xl mb-1 leading-tight">
                                {result.title}
                            </h3>
                        )}
                        {result.description && result.description.trim() && (
                            <p className="text-white/90 text-sm line-clamp-2">
                                {result.description}
                            </p>
                        )}
                    </div>
                    <div className="flex items-center gap-2">
                        {result.view_on_platform && (
                            <a
                                href={result.view_on_platform}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="p-2 hover:bg-white/20 rounded-lg transition-colors"
                                title="View on platform"
                            >
                                <ExternalLink size={18} className="text-white" />
                            </a>
                        )}
                        <button
                            onClick={() => copyToClipboard(JSON.stringify(result, null, 2))}
                            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
                            title="Copy data"
                        >
                            <Copy size={18} className="text-white" />
                        </button>
                    </div>
                </div>
            </div>

            {/* Content */}
            <div className="px-6 py-5">
                {
                    Object.entries(result).map(([key, value], idx) => (
                        (typeof value === 'string' && value.trim() && key !== 'title') ? (
                            <div key={idx} className={`rounded-xl p-4 border hover:shadow-md transition-shadow mb-4`}>
                                <div className="flex items-center gap-2 mb-2">
                                    <span className="text-xs text-gray-600 font-medium">{formatLabel(key)}</span>
                                </div>
                                <div className={`text-2xl font-bold`}>
                                    {isNaN(Number(value)) ? value : formatNumber(value) }
                                </div>
                            </div>
                        ) : null
                    ))
                }
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
                <div className="flex flex-wrap gap-4 pt-4 border-t border-gray-200">
                    {result.date && (
                        <div className="flex items-center gap-2 text-sm text-gray-700">
                            <Calendar size={16} className="text-gray-400" />
                            <span className="font-medium">{formatDate(result.date)}</span>
                        </div>
                    )}
                    {result.profile_name && (
                        <div className="flex items-center gap-2 text-sm text-gray-700">
                            <User size={16} className="text-gray-400" />
                            <span className="font-medium">{result.profile_name}</span>
                        </div>
                    )}
                    {result.author_name && result.author_name !== result.profile_name && (
                        <div className="flex items-center gap-2 text-sm text-gray-700">
                            <User size={16} className="text-gray-400" />
                            <span>by <span className="font-medium">{result.author_name}</span></span>
                        </div>
                    )}
                </div>

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
            </div>

            {/* Copy Success Message */}
            {copied && (
                <div className="px-6 py-3 bg-green-50 border-t border-green-200">
                    <p className="text-xs text-green-700 font-medium">
                        ✓ Result data copied to clipboard!
                    </p>
                </div>
            )}
        </div>
    )
}
