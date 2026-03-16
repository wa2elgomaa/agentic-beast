'use client'

import { useState, KeyboardEvent } from 'react'
import { Send } from 'lucide-react'
import { motion } from 'framer-motion'

interface MessageInputProps {
  onSendMessage: (message: string) => void
  isLoading: boolean
}

export default function MessageInput({ onSendMessage, isLoading }: MessageInputProps) {
  const [message, setMessage] = useState('')

  const handleSubmit = () => {
    if (message.trim() && !isLoading) {
      onSendMessage(message)
      setMessage('')
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="border-t border-gray-200 bg-white">
      <div className="max-w-4xl mx-auto px-4 py-6">
        <div className="relative flex items-end gap-3">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your content performance..."
            disabled={isLoading}
            rows={1}
            className="flex-1 resize-none bg-gray-50 text-gray-900 rounded-xl px-4 py-3 pr-12 focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder:text-gray-400 disabled:opacity-50 max-h-[200px] border border-gray-200"
            style={{
              minHeight: '52px',
              height: 'auto',
            }}
          />
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleSubmit}
            disabled={!message.trim() || isLoading}
            className="absolute right-2 bottom-0 top-0 m-auto w-[34px] h-[34px] p-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:cursor-not-allowed transition-colors"
          >
            <Send size={18} className="text-white" />
          </motion.button>
        </div>
        <p className="text-xs text-gray-500 mt-3 text-center">
          The Beast AI can make mistakes. Please verify important information.
        </p>
      </div>
    </div>
  )
}
