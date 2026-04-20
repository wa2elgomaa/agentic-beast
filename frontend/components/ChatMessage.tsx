'use client'

import { Message as MessageType, QuerySuggestion } from '@/types'
import { motion } from 'framer-motion'
import { Bot, Download, User, Play, Pause, Volume2 } from 'lucide-react'
import ResultCard from './ResultCard'
import DashboardStats from './DashboardStats'
import LoadingSkeleton from './LoadingSkeleton'
import AggregationDashboard from './AggregationDashboard'
import OperationRenderer from './OperationRenderer'
import QuerySuggestions from './QuerySuggestions'
import { exportToCSV } from '@/lib/api'

interface ChatMessageProps {
  message: MessageType
  onSelectSuggestion?: (suggestion: QuerySuggestion) => void
  isPlaying?: boolean
  onPlayToggle?: () => void
}

export default function ChatMessage({ message, onSelectSuggestion, isPlaying, onPlayToggle }: ChatMessageProps) {
  const isUser = message.role === 'user'

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`py-6 ${isUser ? 'bg-transparent' : 'bg-gray-50'}`}
    >
      <div className="max-w-4xl mx-auto px-4 flex gap-6">
        {/* Avatar */}
        <div className="flex-shrink-0">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${isUser
            ? 'bg-blue-600'
            : 'bg-gradient-to-br from-blue-500 to-pink-500'
            }`}>
            {isUser ? <User size={18} color='#fff' /> : <Bot size={18} color='#fff' />}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="mb-2">
            <span className="text-sm font-semibold text-gray-900">
              {isUser ? 'You' : 'The Beast AI'}
            </span>
            <span className="text-xs text-gray-500 ml-2">
              {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
            {!isUser && typeof props !== 'undefined' && (
              <span className="ml-3 inline-flex items-center">
                <button
                  onClick={onPlayToggle}
                  className="p-1 rounded hover:bg-gray-100"
                  aria-label={isPlaying ? 'Pause audio' : 'Play audio'}
                >
                  {isPlaying ? <Pause size={14} /> : <Play size={14} />}
                </button>
              </span>
            )}
          </div>

          {message.isLoading ? (
            <LoadingSkeleton />
          ) : (
            <>
              {(message.content && typeof message.content === 'string') && (
                <div className="text-gray-800 mb-4 prose prose-sm max-w-none">
                  {message.content.split('\n').map((line, idx) => {
                    // Handle bold markdown
                    const boldRegex = /\*\*(.*?)\*\*/g
                    const parts = []
                    let lastIndex = 0
                    let match

                    while ((match = boldRegex.exec(line)) !== null) {
                      if (match.index > lastIndex) {
                        parts.push(line.substring(lastIndex, match.index))
                      }
                      parts.push(<strong key={`bold-${idx}-${match.index}`} className="font-semibold text-gray-900">{match[1]}</strong>)
                      lastIndex = match.index + match[0].length
                    }

                    if (lastIndex < line.length) {
                      parts.push(line.substring(lastIndex))
                    }

                    return (
                      <div key={idx} className={line.startsWith('•') ? 'ml-4' : ''}>
                        {parts.length > 0 ? parts : line || <br />}
                      </div>
                    )
                  })}
                </div>
              )}

              {/* New: Operation-based rendering */}
              {message.operation && message.operationData && (
                <OperationRenderer
                  operation={message.operation}
                  data={message.operationData}
                  metadata={message.operationMetadata || {}}
                />
              )}

              {/* Code Interpreter: chart image */}
              {!isUser && message.metadata?.chart_b64 && (
                <div className="mt-4">
                  <img
                    src={`data:image/png;base64,${message.metadata.chart_b64}`}
                    alt="Analysis chart"
                    className="rounded-lg border border-gray-200 max-w-full shadow-sm"
                  />
                </div>
              )}

              {/* Code Interpreter: code output (non-chart text) */}
              {!isUser && message.metadata?.code_output && !message.metadata?.chart_b64 && (
                <div className="mt-3 bg-gray-900 text-green-300 rounded-lg p-4 text-sm font-mono whitespace-pre-wrap overflow-x-auto">
                  {message.metadata.code_output}
                </div>
              )}

              {/* Query Suggestions */}
              {!isUser && message.operationData?.suggestions && onSelectSuggestion && (
                <QuerySuggestions
                  suggestions={message.operationData.suggestions}
                  onSelectSuggestion={onSelectSuggestion}
                />
              )}
            </>
          )}
        </div>
      </div>
    </motion.div>
  )
}
