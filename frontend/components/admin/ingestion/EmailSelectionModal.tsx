'use client'

import React, { useState, useMemo } from 'react'
import { PreviewEmail } from '@/types'
import { AlertCircle, Mail, Loader2, X } from 'lucide-react'

interface EmailSelectionModalProps {
  isOpen: boolean
  isLoading: boolean
  emails: PreviewEmail[]
  error?: string
  onClose: () => void
  onSelect: (selectedIds: string[]) => Promise<void>
  taskAdaptorType?: string
}

export function EmailSelectionModal({
  isOpen,
  isLoading,
  emails,
  error,
  onClose,
  onSelect,
  taskAdaptorType,
}: EmailSelectionModalProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [isSelecting, setIsSelecting] = useState(false)

  // Filter emails based on search query
  const filteredEmails = useMemo(() => {
    if (!searchQuery.trim()) return emails
    const query = searchQuery.toLowerCase()
    return emails.filter(
      (email) =>
        email.subject.toLowerCase().includes(query) ||
        email.from.toLowerCase().includes(query)
    )
  }, [emails, searchQuery])

  const handleToggleEmail = (messageId: string) => {
    const updated = new Set(selectedIds)
    if (updated.has(messageId)) {
      updated.delete(messageId)
    } else {
      updated.add(messageId)
    }
    setSelectedIds(updated)
  }

  const handleSelectAll = () => {
    if (selectedIds.size === filteredEmails.length && filteredEmails.length > 0) {
      // If all visible are selected, deselect all
      setSelectedIds(new Set())
    } else {
      // Select all visible
      setSelectedIds(new Set(filteredEmails.map((e) => e.message_id)))
    }
  }

  const handleConfirm = async () => {
    if (selectedIds.size === 0) return

    setIsSelecting(true)
    try {
      const selectedArray = Array.from(selectedIds)
      await onSelect(selectedArray)
      setSelectedIds(new Set())
      setSearchQuery('')
    } finally {
      setIsSelecting(false)
    }
  }

  const allVisibleSelected =
    selectedIds.size === filteredEmails.length && filteredEmails.length > 0

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-2xl max-h-[80vh] flex flex-col bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Select Emails to Process</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              Choose which emails you want to ingest. Each selected email will be processed independently.
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={isSelecting}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 disabled:opacity-50"
          >
            <X size={24} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {error && (
            <div className="mb-4 flex items-start gap-3 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900 rounded-lg">
              <AlertCircle size={18} className="text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
              <span className="text-sm text-red-800 dark:text-red-200">{error}</span>
            </div>
          )}

          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-gray-400 dark:text-gray-600 mb-2" />
              <span className="text-sm text-gray-600 dark:text-gray-400">Loading emails...</span>
            </div>
          ) : emails.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Mail className="h-8 w-8 mb-2 text-gray-400 dark:text-gray-600" />
              <span className="text-sm text-gray-600 dark:text-gray-400">No emails found</span>
            </div>
          ) : (
            <>
              {/* Search and select all controls */}
              <div className="space-y-3 mb-4 pb-4 border-b border-gray-200 dark:border-gray-700">
                <input
                  type="text"
                  placeholder="Search by subject or sender..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <div className="flex items-center justify-between">
                  <div className="text-sm text-gray-600 dark:text-gray-400">
                    {selectedIds.size} of {emails.length} selected
                  </div>
                  <button
                    onClick={handleSelectAll}
                    className="px-3 py-1.5 text-sm font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
                  >
                    {allVisibleSelected ? 'Deselect All' : 'Select All'}
                  </button>
                </div>
              </div>

              {/* Email list */}
              <div className="space-y-2">
                {filteredEmails.length === 0 ? (
                  <div className="text-center py-8 text-gray-600 dark:text-gray-400">
                    No emails match your search
                  </div>
                ) : (
                  filteredEmails.map((email) => (
                    <div
                      key={email.message_id}
                      className="flex items-start space-x-3 p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors cursor-pointer"
                      onClick={() => handleToggleEmail(email.message_id)}
                    >
                      <input
                        type="checkbox"
                        id={email.message_id}
                        checked={selectedIds.has(email.message_id)}
                        onChange={() => {}} // Controlled by parent div click
                        className="mt-1 w-4 h-4 cursor-pointer accent-blue-600"
                      />
                      <label
                        htmlFor={email.message_id}
                        className="flex-1 cursor-pointer min-w-0"
                      >
                        <div className="font-medium text-sm text-gray-900 dark:text-white truncate">
                          {email.subject || '(No subject)'}
                        </div>
                        <div className="text-xs text-gray-600 dark:text-gray-400 truncate">
                          From: {email.from}
                        </div>
                        {email.attachment_count > 0 && (
                          <div className="text-xs text-gray-600 dark:text-gray-400">
                            {email.attachment_count} attachment{email.attachment_count > 1 ? 's' : ''}
                          </div>
                        )}
                      </label>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-6 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50">
          <button
            onClick={onClose}
            disabled={isSelecting}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={selectedIds.size === 0 || isSelecting || isLoading}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg transition-colors flex items-center gap-2"
          >
            {isSelecting ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Processing...
              </>
            ) : (
              `Process Selected (${selectedIds.size})`
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
