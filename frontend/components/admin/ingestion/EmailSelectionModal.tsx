'use client'

import React, { useState, useMemo } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { PreviewEmail } from '@/types'
import { AlertCircle, Mail, Loader2 } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'

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
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Select Emails to Process</DialogTitle>
          <DialogDescription>
            Choose which emails you want to ingest. Each selected email will be processed independently.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">Loading emails...</span>
          </div>
        ) : emails.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <Mail className="h-8 w-8 mb-2" />
            <span>No emails found</span>
          </div>
        ) : (
          <>
            {/* Search and select all controls */}
            <div className="space-y-3 border-b pb-3">
              <Input
                placeholder="Search by subject or sender..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full"
              />
              <div className="flex items-center justify-between">
                <div className="text-sm text-muted-foreground">
                  {selectedIds.size} of {emails.length} selected
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSelectAll}
                >
                  {allVisibleSelected ? 'Deselect All' : 'Select All'}
                </Button>
              </div>
            </div>

            {/* Email list */}
            <div className="space-y-2 overflow-y-auto flex-1 pr-2">
              {filteredEmails.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No emails match your search
                </div>
              ) : (
                filteredEmails.map((email) => (
                  <div
                    key={email.message_id}
                    className="flex items-start space-x-2 p-2 rounded hover:bg-muted transition-colors"
                  >
                    <Checkbox
                      id={email.message_id}
                      checked={selectedIds.has(email.message_id)}
                      onCheckedChange={() => handleToggleEmail(email.message_id)}
                      className="mt-1"
                    />
                    <label
                      htmlFor={email.message_id}
                      className="flex-1 cursor-pointer min-w-0"
                    >
                      <div className="font-medium text-sm truncate">
                        {email.subject || '(No subject)'}
                      </div>
                      <div className="text-xs text-muted-foreground truncate">
                        From: {email.from}
                      </div>
                      {email.attachment_count > 0 && (
                        <div className="text-xs text-muted-foreground">
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

        <DialogFooter>
          <Button
            variant="outline"
            onClick={onClose}
            disabled={isSelecting}
          >
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={selectedIds.size === 0 || isSelecting || isLoading}
            isLoading={isSelecting}
          >
            Process Selected ({selectedIds.size})
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
