'use client'

import { QuerySuggestion } from '@/types'
import { Lightbulb, ChevronRight } from 'lucide-react'

interface QuerySuggestionsProps {
  suggestions: QuerySuggestion[]
  onSelectSuggestion: (suggestion: QuerySuggestion) => void
}

export default function QuerySuggestions({ suggestions, onSelectSuggestion }: QuerySuggestionsProps) {
  if (!suggestions || suggestions.length === 0) {
    return null
  }

  return (
    <div className="mt-6 rounded-xl border border-blue-100 bg-gradient-to-br from-blue-50 to-indigo-50 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Lightbulb size={18} className="text-blue-600" />
        <h3 className="text-sm font-semibold text-blue-900">
          Suggested follow-up questions
        </h3>
      </div>
      
      <div className="space-y-2">
        {suggestions.map((suggestion, index) => (
          <button
            key={index}
            onClick={() => onSelectSuggestion(suggestion)}
            className="w-full text-left px-4 py-3 rounded-lg bg-white hover:bg-blue-50 border border-blue-100 hover:border-blue-300 transition-all duration-200 group"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-700 group-hover:text-blue-700 flex-1">
                {suggestion.question}
              </span>
              <ChevronRight 
                size={16} 
                className="text-gray-400 group-hover:text-blue-600 group-hover:translate-x-1 transition-transform flex-shrink-0 ml-2"
              />
            </div>
          </button>
        ))}
      </div>
      
      <p className="text-xs text-gray-500 mt-3 flex items-center gap-1">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500"></span>
        Click any suggestion for instant results
      </p>
    </div>
  )
}
