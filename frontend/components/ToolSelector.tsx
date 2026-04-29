'use client'

import { useState, useRef, useEffect } from 'react'
import { ChevronDown, Search, FileText } from 'lucide-react'
import styles from './ChatArea.module.css'

export type ToolType = 'search' | 'documents' | null

interface ToolOption {
  value: ToolType
  label: string
  description: string
  icon: React.ReactNode
}

interface ToolSelectorProps {
  selectedTool: ToolType
  onSelectTool: (tool: ToolType) => void
}

const TOOL_OPTIONS: ToolOption[] = [
  {
    value: 'search',
    label: 'Search',
    description: 'Search thenationalnews.com',
    icon: <Search size={18} />,
  },
  {
    value: 'documents',
    label: 'Documents',
    description: 'Ask about uploaded documents',
    icon: <FileText size={18} />,
  },
]

export default function ToolSelector({ selectedTool, onSelectTool }: ToolSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  const handleSelectTool = (tool: ToolType) => {
    onSelectTool(tool === selectedTool ? null : tool)
    setIsOpen(false)
  }

  const selectedToolOption = selectedTool
    ? TOOL_OPTIONS.find((opt) => opt.value === selectedTool)
    : null

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Tool selector button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-center w-9 h-9 rounded-lg bg-gray-100 hover:bg-gray-200 transition-colors text-gray-700 border border-gray-200"
        title="Select a tool to help with your query"
        aria-label="Tool selector"
      >
        <span className="text-lg">+</span>
      </button>

      {/* Selected tool badge */}
      {selectedToolOption && (
        <div className="absolute bottom-12 left-0 flex items-center gap-0 bg-blue-50 border border-blue-200 rounded-md px-1 py-1 text-xs text-blue-700 whitespace-nowrap">
          {selectedToolOption.icon}
          {/* <span>{selectedToolOption.label}</span> */}
          <button
            onClick={() => handleSelectTool(null)}
            className="ml-1 text-blue-500 hover:text-blue-700 font-bold"
            title="Clear tool selection"
          >
            ×
          </button>
        </div>
      )}

      {/* Dropdown menu */}
      {isOpen && (
        <div className="absolute bottom-12 left-0 bg-white border border-gray-200 rounded-lg shadow-lg z-50 min-w-max">
          {TOOL_OPTIONS.map((tool) => (
            <button
              key={tool.value}
              onClick={() => handleSelectTool(tool.value)}
              className={`w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-gray-50 transition-colors border-b border-gray-100 last:border-b-0 ${
                selectedTool === tool.value ? 'bg-blue-50' : ''
              }`}
            >
              <div className={`${selectedTool === tool.value ? 'text-blue-600' : 'text-gray-500'}`}>
                {tool.icon}
              </div>
              <div>
                <div className={`font-medium ${selectedTool === tool.value ? 'text-blue-600' : 'text-gray-900'}`}>
                  {tool.label}
                </div>
                <div className="text-xs text-gray-500">{tool.description}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
