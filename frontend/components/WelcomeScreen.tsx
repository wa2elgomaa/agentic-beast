'use client'

import { motion } from 'framer-motion'
import { Sparkles } from 'lucide-react'
import LogoIcon from './Logo'

interface WelcomeScreenProps {
  onSendMessage: (message: string) => void
}

const suggestions = [
  {
    icon: '🎯',
    title: 'Analyze Performance',
    description: 'Show me the top 10 most viewed videos',
  },
  {
    icon: '📊',
    title: 'Compare Platforms',
    description: 'Compare Instagram reels vs TikTok videos',
  },
  {
    icon: '💡',
    title: 'Find Trends',
    description: 'What content had highest engagement this month?',
  },
  {
    icon: '🔍',
    title: 'Deep Dive',
    description: 'Show Facebook posts with best reach last week',
  },
]

export default function WelcomeScreen({ onSendMessage }: WelcomeScreenProps) {
  return (
    <div className="h-full flex items-center justify-center p-8">
      <div className="max-w-3xl w-full">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center mb-12"
        >
          <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-gray-200 to-gray-300 rounded-2xl mb-6">
            <LogoIcon color='#fff' width={34} height={34} />
          </div>
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            Welcome to The Beast AI
          </h1>
          <p className="text-gray-600 text-lg">
            Ask me anything about your social media content performance
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2, duration: 0.5 }}
          className="grid grid-cols-1 md:grid-cols-2 gap-4"
        >
          {suggestions.map((suggestion, index) => (
            <motion.button
              key={index}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 * index + 0.3 }}
              onClick={() => onSendMessage(suggestion.description)}
              className="group p-6 rounded-xl bg-gray-50 hover:bg-gray-100 border border-gray-200 hover:border-gray-300 transition-all text-left"
            >
              <div className="text-3xl mb-3">{suggestion.icon}</div>
              <h3 className="text-gray-900 font-semibold mb-2 group-hover:text-blue-600 transition-colors">
                {suggestion.title}
              </h3>
              <p className="text-gray-600 text-sm">{suggestion.description}</p>
            </motion.button>
          ))}
        </motion.div>
      </div>
    </div>
  )
}
