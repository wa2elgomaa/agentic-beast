'use client'

import { ContentResult } from '@/types'
import { motion } from 'framer-motion'
import { formatNumber, formatDate } from '@/lib/api'
import { ExternalLink } from 'lucide-react'

interface ResultCardProps {
  result: ContentResult
  index: number
}

export default function ResultCard({ result, index }: ResultCardProps) {
  const metrics = [
    { label: 'Views', value: result.video_views, icon: '👁️', color: 'from-blue-500 to-cyan-500' },
    { label: 'Impressions', value: result.total_impressions, icon: '📊', color: 'from-purple-500 to-pink-500' },
    { label: 'Engagement', value: result.total_interactions, icon: '❤️', color: 'from-pink-500 to-rose-500' },
    { label: 'Reach', value: result.total_reach, icon: '📈', color: 'from-green-500 to-emerald-500' },
  ].filter(m => m.value != null && m.value > 0)

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="group rounded-xl bg-gray-50 hover:bg-gray-100 border border-gray-200 hover:border-gray-300 p-4 transition-all"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-900 mb-1.5 leading-tight">
            {result.title || result.description || result.content?.substring(0, 80) + '...' || `Post #${result.row_number}`}
          </h3>
          <div className="flex items-center gap-2 flex-wrap text-xs text-gray-400">
            {result.platform && (
              <span className="px-2 py-1 bg-gradient-to-r from-blue-500/20 to-purple-500/20 rounded-md font-medium text-white">
                {result.platform}
              </span>
            )}
            {(result.media_type || result.content_type) && (
              <span>• {result.media_type || result.content_type}</span>
            )}
            {result.date && (
              <span>• {formatDate(result.date)}</span>
            )}
          </div>
        </div>
      </div>

      {/* Metrics Grid */}
      {metrics.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
          {metrics.slice(0, 4).map((metric, i) => (
            <div
              key={i}
              className="rounded-lg p-2.5 bg-white border border-gray-200"
            >
              <div className="text-gray-400 mb-1 text-[10px] font-medium">
                {metric.icon} {metric.label}
              </div>
              <div className={`font-bold text-base bg-gradient-to-r ${metric.color} bg-clip-text text-transparent`}>
                {formatNumber(metric.value)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-gray-200 text-xs">
        <div className="text-gray-600">
          {result.profile_name && (
            <span className="text-gray-900 font-medium">{result.profile_name}</span>
          )}
        </div>
        {result.view_on_platform && (
          <a
            href={result.view_on_platform}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white font-medium transition-all"
          >
            View Post
            <ExternalLink size={12} />
          </a>
        )}
      </div>
    </motion.div>
  )
}
