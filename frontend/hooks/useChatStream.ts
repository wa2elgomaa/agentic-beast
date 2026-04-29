'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { buildChatStreamWsUrl } from '@/lib/api'
import { ChatStreamEvent, ChatStreamState } from '@/types'

interface UseChatStreamOptions {
  token: string | null
  conversationId?: string | null
  onChunk?: (text: string, index: number) => void
  onComplete?: (data: ChatStreamEvent['data']) => void
  onThinking?: () => void
  onError?: (message: string) => void
  onTranscript?: (text: string) => void
  onAudioStart?: (sampleRate: number) => void
  onAudioChunk?: (audio: string) => void
  onAudioEnd?: () => void
}

interface UseChatStreamResult {
  state: ChatStreamState
  sendMessage: (message: string, conversationId?: string | null) => boolean
  sendAudio: (audioBase64: string, conversationId?: string | null) => boolean
  disconnect: () => void
}

export function useChatStream({
  token,
  conversationId,
  onChunk,
  onComplete,
  onThinking,
  onError,
  onTranscript,
  onAudioStart,
  onAudioChunk,
  onAudioEnd,
}: UseChatStreamOptions): UseChatStreamResult {
  const socketRef = useRef<WebSocket | null>(null)
  const [state, setState] = useState<ChatStreamState>('idle')

  // Keep callbacks in refs so sendMessage closure doesn't go stale
  const onChunkRef = useRef(onChunk)
  const onCompleteRef = useRef(onComplete)
  const onThinkingRef = useRef(onThinking)
  const onErrorRef = useRef(onError)
  const onTranscriptRef = useRef(onTranscript)
  const onAudioStartRef = useRef(onAudioStart)
  const onAudioChunkRef = useRef(onAudioChunk)
  const onAudioEndRef = useRef(onAudioEnd)
  useEffect(() => { onChunkRef.current = onChunk }, [onChunk])
  useEffect(() => { onCompleteRef.current = onComplete }, [onComplete])
  useEffect(() => { onThinkingRef.current = onThinking }, [onThinking])
  useEffect(() => { onErrorRef.current = onError }, [onError])
  useEffect(() => { onTranscriptRef.current = onTranscript }, [onTranscript])
  useEffect(() => { onAudioStartRef.current = onAudioStart }, [onAudioStart])
  useEffect(() => { onAudioChunkRef.current = onAudioChunk }, [onAudioChunk])
  useEffect(() => { onAudioEndRef.current = onAudioEnd }, [onAudioEnd])

  const disconnect = useCallback(() => {
    const socket = socketRef.current
    if (socket) {
      socket.onopen = null
      socket.onmessage = null
      socket.onerror = null
      socket.onclose = null
      socket.close()
      socketRef.current = null
    }
    setState('idle')
  }, [])

  // Close on unmount
  useEffect(() => () => disconnect(), [disconnect])

  const ensureConnected = useCallback(
    (targetConversationId?: string | null): Promise<WebSocket> => {
      // Reuse an already-open connection when possible
      const existing = socketRef.current
      if (existing && existing.readyState === WebSocket.OPEN) {
        return Promise.resolve(existing)
      }

      if (!token) {
        return Promise.reject(new Error('No auth token'))
      }

      return new Promise((resolve, reject) => {
        const url = buildChatStreamWsUrl(token, targetConversationId ?? conversationId)
        const socket = new WebSocket(url)
        socketRef.current = socket
        setState('connecting')

        const timeout = window.setTimeout(() => {
          socket.close()
          reject(new Error('WebSocket connection timed out'))
        }, 10_000)

        socket.onopen = () => {
          window.clearTimeout(timeout)
          setState('connected')
        }

        socket.onmessage = (ev) => {
          try {
            const event = JSON.parse(ev.data) as ChatStreamEvent

            if (event.type === 'session_ready') {
              resolve(socket)
              return
            }

            if (event.type === 'thinking') {
              setState('streaming')
              onThinkingRef.current?.()
              return
            }

            if (event.type === 'text_chunk') {
              const text = event.data?.text ?? ''
              const index = event.data?.index ?? 0
              onChunkRef.current?.(text, index)
              return
            }

            if (event.type === 'complete') {
              setState('connected')
              onCompleteRef.current?.(event.data)
              return
            }

            if (event.type === 'error') {
              setState('error')
              onErrorRef.current?.(event.message ?? 'Unknown error')
              return
            }

            if (event.type === 'transcript') {
              onTranscriptRef.current?.(event.data?.text ?? '')
              return
            }

            if (event.type === 'audio_start') {
              onAudioStartRef.current?.(event.data?.sample_rate ?? 24000)
              return
            }

            if (event.type === 'audio_chunk') {
              onAudioChunkRef.current?.(event.data?.audio ?? '')
              return
            }

            if (event.type === 'audio_end') {
              onAudioEndRef.current?.()
              return
            }
          } catch {
            // ignore malformed frames
          }
        }

        socket.onerror = () => {
          window.clearTimeout(timeout)
          setState('error')
          reject(new Error('WebSocket connection error'))
        }

        socket.onclose = () => {
          socketRef.current = null
          setState((prev) => (prev === 'error' ? 'error' : 'idle'))
        }
      })
    },
    [token, conversationId]
  )

  const sendMessage = useCallback(
    (message: string, targetConversationId?: string | null): boolean => {
      const resolvedId = targetConversationId ?? conversationId

      ensureConnected(resolvedId)
        .then((socket) => {
          socket.send(
            JSON.stringify({
              type: 'text',
              message,
              conversation_id: resolvedId ?? undefined,
            })
          )
        })
        .catch((err) => {
          onErrorRef.current?.(err instanceof Error ? err.message : 'Connection failed')
          setState('error')
        })

      return true
    },
    [conversationId, ensureConnected]
  )

  const sendAudio = useCallback(
    (audioBase64: string, targetConversationId?: string | null): boolean => {
      const resolvedId = targetConversationId ?? conversationId

      ensureConnected(resolvedId)
        .then((socket) => {
          socket.send(
            JSON.stringify({
              type: 'audio',
              audio: audioBase64,
              conversation_id: resolvedId ?? undefined,
            })
          )
        })
        .catch((err) => {
          onErrorRef.current?.(err instanceof Error ? err.message : 'Connection failed')
          setState('error')
        })

      return true
    },
    [conversationId, ensureConnected]
  )

  return { state, sendMessage, sendAudio, disconnect }
}
