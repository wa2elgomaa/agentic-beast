'use client'

import { Aggregation } from '@/types'
import { motion } from 'framer-motion'
import { TrendingUp, Users, Eye, BarChart3, PieChart, Activity } from 'lucide-react'

interface AggregationDashboardProps {
  aggregations: Aggregation[]
  title?: string
}

const getMetricIcon = (metric: string) => {
  const lowerMetric = metric.toLowerCase()
  if (lowerMetric.includes('view')) return Eye
  if (lowerMetric.includes('impression')) return BarChart3
  if (lowerMetric.includes('interaction') || lowerMetric.includes('engagement')) return Activity
  if (lowerMetric.includes('reach')) return Users
  if (lowerMetric.includes('count')) return PieChart
  return TrendingUp
}

const formatNumber = (num: number, type: string) => {
  if (type === 'avg') {
    return num.toLocaleString('en-US', { maximumFractionDigits: 2 })
  }
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toLocaleString('en-US')
}

const getGradientColors = (index: number) => {
  const gradients = [
    'from-blue-500 to-cyan-500',
    'from-purple-500 to-pink-500',
    'from-green-500 to-emerald-500',
    'from-orange-500 to-red-500',
    'from-indigo-500 to-purple-500',
    'from-teal-500 to-green-500',
  ]
  return gradients[index % gradients.length]
}

export default function AggregationDashboard({ aggregations, title }: AggregationDashboardProps) {
  // Check if this is a grouped aggregation (multiple results with group keys)
  const isGrouped = aggregations.length > 1 || (
    aggregations.length > 0 && 
    Object.keys(aggregations[0]).some(k => !k.startsWith('_aggregated') && !k.startsWith('_aggregation'))
  )

  // Calculate total if grouped
  const totalValue = aggregations.reduce((sum, agg) => sum + (agg._aggregated_total || 0), 0)
  const totalCount = aggregations.reduce((sum, agg) => sum + (agg._aggregated_count || 0), 0)

  // Get aggregation type and metric from first item
  const aggType = aggregations[0]?._aggregation_type || 'sum'
  const aggMetric = aggregations[0]?._aggregation_metric || 'count'
  const metricDisplay = aggMetric.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
  const Icon = getMetricIcon(aggMetric)

  if (!isGrouped && aggregations.length === 1) {
    // Single aggregation - display as large stat card
    const agg = aggregations[0]
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3 }}
        className="my-6"
      >
        <div className={`relative overflow-hidden rounded-2xl bg-gradient-to-br ${getGradientColors(0)} p-8 shadow-xl`}>
          <div className="relative z-10">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-3 bg-white/20 backdrop-blur-sm rounded-xl">
                  <Icon className="text-white" size={32} />
                </div>
                <div>
                  <p className="text-white/80 text-sm font-medium uppercase tracking-wide">
                    {aggType === 'sum' ? 'Total' : aggType === 'avg' ? 'Average' : 'Count'}
                  </p>
                  <h3 className="text-white text-lg font-semibold">{metricDisplay}</h3>
                </div>
              </div>
            </div>
            
            <div className="mt-6">
              <div className="text-5xl font-bold text-white mb-2">
                {formatNumber(agg._aggregated_total, aggType)}
              </div>
              <div className="text-white/70 text-sm">
                Based on {agg._aggregated_count.toLocaleString()} {agg._aggregated_count === 1 ? 'item' : 'items'}
              </div>
            </div>
          </div>
          
          {/* Decorative elements */}
          <div className="absolute top-0 right-0 w-64 h-64 bg-white/10 rounded-full -mr-32 -mt-32"></div>
          <div className="absolute bottom-0 left-0 w-48 h-48 bg-white/10 rounded-full -ml-24 -mb-24"></div>
        </div>
      </motion.div>
    )
  }

  // Grouped aggregation - display as grid of cards
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="my-6"
    >
      {/* Header with total */}
      <div className="mb-6 p-6 bg-gradient-to-r from-gray-800 to-gray-900 rounded-2xl shadow-lg">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-gray-400 text-sm font-medium uppercase tracking-wide mb-1">
              {aggType === 'sum' ? 'Total' : aggType === 'avg' ? 'Average' : 'Total Count'}
            </p>
            <h3 className="text-white text-2xl font-bold">{metricDisplay}</h3>
          </div>
          <div className="text-right">
            <div className="text-4xl font-bold text-white">
              {formatNumber(totalValue, aggType)}
            </div>
            <div className="text-gray-400 text-sm mt-1">
              {totalCount.toLocaleString()} {totalCount === 1 ? 'item' : 'items'} • {aggregations.length} {aggregations.length === 1 ? 'group' : 'groups'}
            </div>
          </div>
        </div>
      </div>

      {/* Group cards grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {aggregations.map((agg, index) => {
          // Extract group labels
          const groupLabels: Record<string, any> = {}
          Object.keys(agg).forEach(key => {
            if (!key.startsWith('_aggregated') && !key.startsWith('_aggregation')) {
              groupLabels[key] = agg[key as keyof Aggregation]
            }
          })

          const groupLabel = Object.entries(groupLabels)
            .map(([key, value]) => `${key}: ${value}`)
            .join(' | ') || 'Group ' + (index + 1)

          // Calculate percentage of total
          const percentage = totalValue > 0 ? (agg._aggregated_total / totalValue * 100) : 0

          return (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: index * 0.05 }}
              className={`relative overflow-hidden rounded-xl bg-gradient-to-br ${getGradientColors(index)} p-6 shadow-lg hover:shadow-xl transition-shadow`}
            >
              <div className="relative z-10">
                <div className="flex items-start justify-between mb-3">
                  <div className="p-2 bg-white/20 backdrop-blur-sm rounded-lg">
                    <Icon className="text-white" size={20} />
                  </div>
                  {percentage > 0 && (
                    <div className="text-white/90 text-xs font-semibold bg-white/20 backdrop-blur-sm px-2 py-1 rounded-full">
                      {percentage.toFixed(1)}%
                    </div>
                  )}
                </div>

                <div className="mb-3">
                  <h4 className="text-white/90 text-sm font-medium mb-1 line-clamp-2">
                    {groupLabel}
                  </h4>
                </div>

                <div className="text-3xl font-bold text-white mb-1">
                  {formatNumber(agg._aggregated_total, aggType)}
                </div>
                
                <div className="text-white/70 text-xs">
                  {agg._aggregated_count.toLocaleString()} {agg._aggregated_count === 1 ? 'item' : 'items'}
                </div>
              </div>

              {/* Progress bar */}
              {percentage > 0 && (
                <div className="mt-3 relative">
                  <div className="w-full h-1.5 bg-white/20 rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${percentage}%` }}
                      transition={{ duration: 0.6, delay: index * 0.05 + 0.3 }}
                      className="h-full bg-white/80 rounded-full"
                    />
                  </div>
                </div>
              )}

              {/* Decorative circle */}
              <div className="absolute -bottom-8 -right-8 w-32 h-32 bg-white/10 rounded-full"></div>
            </motion.div>
          )
        })}
      </div>
    </motion.div>
  )
}
