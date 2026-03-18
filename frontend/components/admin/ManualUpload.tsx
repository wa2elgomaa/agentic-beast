'use client'

import { useState } from 'react'
import { uploadFileForTask } from '@/lib/api'
import { Upload, AlertCircle, CheckCircle2 } from 'lucide-react'

interface ManualUploadProps {
  taskId?: string
  onColumnsDetected: (file: File) => void
  detectOnly?: boolean
  title?: string
  description?: string
}

export default function ManualUpload({
  taskId,
  onColumnsDetected,
  detectOnly = false,
  title = 'Upload Data File',
  description = 'Upload Excel or CSV files to analyze and map columns',
}: ManualUploadProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)

    const files = e.dataTransfer.files
    if (files.length > 0) {
      handleFile(files[0])
    }
  }

  const handleFile = async (file: File) => {
    // Validate file type
    const validTypes = ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'text/csv']
    if (!validTypes.includes(file.type)) {
      setError('Please upload an Excel (.xlsx, .xls) or CSV file')
      return
    }

    try {
      setIsUploading(true)
      setError(null)
      
      if (!detectOnly) {
        if (!taskId) {
          throw new Error('Task ID is required for file upload')
        }
        // Upload file for manual ingestion tasks
        await uploadFileForTask(taskId, file)
      }
      
      // Detect columns from file
      onColumnsDetected(file)
      
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload file')
    } finally {
      setIsUploading(false)
    }
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.currentTarget.files
    if (files && files.length > 0) {
      handleFile(files[0])
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">{title}</h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">{description}</p>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="flex items-center gap-3 px-4 py-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900 rounded-lg">
          <AlertCircle size={18} className="text-red-600 dark:text-red-400 flex-shrink-0" />
          <p className="text-red-800 dark:text-red-200">{error}</p>
        </div>
      )}

      {/* Success Alert */}
      {success && (
        <div className="flex items-center gap-3 px-4 py-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-900 rounded-lg">
          <CheckCircle2 size={18} className="text-green-600 dark:text-green-400 flex-shrink-0" />
          <p className="text-green-800 dark:text-green-200">
            {detectOnly ? '✓ File parsed and columns detected' : '✓ File uploaded and columns detected'}
          </p>
        </div>
      )}

      {/* Upload Area */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          isDragging
            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
            : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 hover:border-gray-400 dark:hover:border-gray-500'
        }`}
      >
        <input
          type="file"
          id="file-upload"
          onChange={handleFileInput}
          accept=".xlsx,.xls,.csv"
          className="hidden"
          disabled={isUploading}
        />
        
        <label htmlFor="file-upload" className="cursor-pointer">
          <div className="flex flex-col items-center gap-2">
            <Upload size={32} className="text-gray-400 dark:text-gray-600" />
            <p className="font-medium text-gray-900 dark:text-white">
              {isUploading ? 'Uploading...' : 'Drop your file here or click to browse'}
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Supported formats: Excel (.xlsx, .xls), CSV
            </p>
          </div>
        </label>
      </div>

      {/* File Selection Button */}
      <div className="flex gap-3">
        <label htmlFor="file-upload" className="flex-1">
          <div className="inline-flex w-full items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg transition-colors font-medium cursor-pointer">
            <Upload size={16} />
            Select File
          </div>
        </label>
      </div>
    </div>
  )
}
