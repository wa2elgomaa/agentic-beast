'use client'

import { Suspense, useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { exchangeGmailTaskCode } from '@/lib/api'
import { AlertCircle, Loader2 } from 'lucide-react'
import Link from 'next/link'

function GmailCallbackHandler() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing')
  const [taskId, setTaskId] = useState<string | null>(null)
  // Guard against React StrictMode double-invocation consuming the one-time OAuth code twice
  const exchangeCalledRef = useRef(false)

  useEffect(() => {
    const code = searchParams.get('code')
    const state = searchParams.get('state')
    const oauthError = searchParams.get('error')

    if (oauthError) {
      setError(`Google denied access: ${oauthError}`)
      setStatus('error')
      return
    }

    if (!code || !state) {
      setError('Missing OAuth parameters. Please try connecting again.')
      setStatus('error')
      return
    }

    // state is "{task_id}:{nonce}" — extract the task_id from the first segment
    const colonIdx = state.indexOf(':')
    if (colonIdx === -1) {
      setError('Malformed OAuth state. Please try connecting again.')
      setStatus('error')
      return
    }

    const extractedTaskId = state.substring(0, colonIdx)
    setTaskId(extractedTaskId)

    if (exchangeCalledRef.current) return
    exchangeCalledRef.current = true

    const exchange = async () => {
      try {
        const redirectUri = `${window.location.origin}/admin/ingestion/gmail-callback`
        await exchangeGmailTaskCode(extractedTaskId, { code, state, redirect_uri: redirectUri })
        setStatus('success')
        // Brief pause so the user sees the success state, then redirect
        setTimeout(() => {
          router.replace(`/admin/ingestion/${extractedTaskId}`)
        }, 1500)
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to complete Gmail authorization'
        const isExpired = /expired|already used|invalid.grant/i.test(msg)
        setError(
          isExpired
            ? 'This authorization session expired or was already used. Please go back to the task and click Connect Gmail again.'
            : msg
        )
        setStatus('error')
      }
    }

    exchange()
  }, [searchParams, router])

  if (status === 'processing') {
    return (
      <div className="flex flex-col items-center gap-4 text-center">
        <Loader2 size={40} className="text-blue-600 animate-spin" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Linking Gmail account…</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">Exchanging authorization code with Google</p>
      </div>
    )
  }

  if (status === 'success') {
    return (
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="h-12 w-12 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
          <svg className="h-6 w-6 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Gmail linked successfully!</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">Redirecting to task details…</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-4 text-center">
      <div className="h-12 w-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
        <AlertCircle size={24} className="text-red-600 dark:text-red-400" />
      </div>
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Authorization failed</h2>
      <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      {taskId ? (
        <Link
          href={`/admin/ingestion/${taskId}`}
          className="mt-2 text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400"
        >
          Back to task
        </Link>
      ) : (
        <Link
          href="/admin/ingestion"
          className="mt-2 text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400"
        >
          Back to ingestion tasks
        </Link>
      )}
    </div>
  )
}

export default function GmailCallbackPage() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center p-8">
      <div className="w-full max-w-md bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-10">
        <Suspense
          fallback={
            <div className="flex flex-col items-center gap-4 text-center">
              <Loader2 size={40} className="text-blue-600 animate-spin" />
              <p className="text-sm text-gray-500">Loading…</p>
            </div>
          }
        >
          <GmailCallbackHandler />
        </Suspense>
      </div>
    </div>
  )
}
