'use client'

import { ContentResult, DashboardStats as StatsType } from '@/types'
import { motion } from 'framer-motion'
import { formatNumber } from '@/lib/api'
import { TrendingUp, Eye, Heart, Zap, Download } from 'lucide-react'
import { exportToCSV } from '@/lib/api'

interface DashboardStatsProps {
  results: ContentResult[]
}

export default function DashboardStats({ results }: DashboardStatsProps) {
  const stats: StatsType = {
    totalResults: results.length,
    totalViews: results.reduce((sum, r) => sum + (r.video_views || 0), 0),
    totalEngagement: results.reduce((sum, r) => sum + (r.total_interactions || 0), 0),
    avgCompletion: results.filter(r => r.completion_rate).length > 0
      ? results.reduce((sum, r) => sum + (r.completion_rate || 0), 0) / results.filter(r => r.completion_rate).length
      : 0,
  }

  const statCards = [
    { label: 'Total Results', value: stats.totalResults, icon: TrendingUp, color: 'from-blue-400 to-cyan-400' },
    { label: 'Total Views', value: stats.totalViews, icon: Eye, color: 'from-purple-400 to-pink-400' },
    { label: 'Total Engagement', value: stats.totalEngagement, icon: Heart, color: 'from-pink-400 to-rose-400' },
    { 
      label: 'Avg. Completion', 
      value: stats.avgCompletion > 0 ? `${stats.avgCompletion.toFixed(1)}%` : 'N/A', 
      icon: Zap, 
      color: 'from-green-400 to-emerald-400',
      raw: stats.avgCompletion 
    },
  ]

  return (
    <div className="mb-6">
      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        {statCards.map((stat, index) => (
          <motion.div
            key={index}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.1 }}
            className="rounded-xl bg-gray-50 border border-gray-200 p-4 hover:bg-gray-100 transition-colors"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-600">{stat.label}</span>
              <stat.icon size={16} className="text-gray-400" />
            </div>
            <div className={`text-2xl font-bold bg-gradient-to-r ${stat.color} bg-clip-text text-transparent`}>
              {typeof stat.value === 'number' ? formatNumber(stat.value) : stat.value}
            </div>
          </motion.div>
        ))}
      </div>
      {/* Export Button */}
      <button
        onClick={() => exportToCSV(results, 'tnn-analytics')}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-50 hover:bg-gray-100 border border-gray-200 hover:border-gray-300 text-sm text-gray-700 hover:text-gray-900 transition-all"
      >
        <Download size={16} />
        Export to CSV
      </button>
    </div>
  )
}
