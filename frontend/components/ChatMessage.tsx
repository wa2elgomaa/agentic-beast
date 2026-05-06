'use client'

import { Message as MessageType, QuerySuggestion } from '@/types'
import { motion } from 'framer-motion'
import { Bot, User } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import LoadingSkeleton from './LoadingSkeleton'

interface ChatMessageProps {
  message: MessageType
  onSelectSuggestion?: (suggestion: QuerySuggestion) => void
}

export default function ChatMessage({ message }: ChatMessageProps) {
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
          </div>

          {message.isLoading ? (
            <LoadingSkeleton />
          ) : (
            <>
              <div className="text-gray-800 prose prose-sm max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                  {message.content || ''}
                </ReactMarkdown>
              </div>

              {/* Render assets[] (new path) ---------------------------------------- */}
              {!isUser && (message.metadata?.assets ?? []).length > 0 && (
                <>
                  {(message.metadata!.assets!).map((asset, i) => (
                    <figure key={i} className="mt-4">
                      <img
                        src={asset.source}
                        alt={asset.caption || 'Analysis chart'}
                        className="rounded-lg border border-gray-200 max-w-full shadow-sm"
                      />
                      {asset.caption && (
                        <figcaption className="mt-1 text-xs text-gray-500 text-center">
                          {asset.caption}
                        </figcaption>
                      )}
                    </figure>
                  ))}
                </>
              )}
              {/* Legacy fallback: old messages stored chart_b64 directly ----------- */}
              {!isUser && !((message.metadata?.assets ?? []).length > 0) && message.metadata?.chart_b64 && (
                <figure className="mt-4">
                  <img
                    src={`data:image/png;base64,${message.metadata.chart_b64}`}
                    alt={message.metadata.visualization_caption || 'Analysis chart'}
                    className="rounded-lg border border-gray-200 max-w-full shadow-sm"
                  />
                  {message.metadata.visualization_caption && (
                    <figcaption className="mt-1 text-xs text-gray-500 text-center">
                      {message.metadata.visualization_caption}
                    </figcaption>
                  )}
                </figure>
              )}
              {/* TTS generation indicator */}
              {!isUser && message.isTtsGenerating && (
                <div className="flex items-center gap-2 text-sm text-indigo-500 mt-2">
                  <div className="flex gap-[3px] items-end h-4">
                    {[0, 1, 2, 3].map((i) => (
                      <span
                        key={i}
                        className="w-[3px] rounded-full bg-indigo-400 animate-bounce"
                        style={{ height: '60%', animationDelay: `${i * 0.15}s` }}
                      />
                    ))}
                  </div>
                  <span>Generating voice…</span>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </motion.div>
  )
}
