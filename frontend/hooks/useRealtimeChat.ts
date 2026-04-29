'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { buildRealtimeChatWsUrl } from '@/lib/api'
import { RealtimeClientEvent, RealtimeServerEvent } from '@/types'

type RealtimeConnectionState = 'idle' | 'connecting' | 'connected' | 'error'

interface UseRealtimeChatOptions {
  enabled: boolean
  token: string | null
  conversationId?: string | null
  onEvent?: (event: RealtimeServerEvent) => void
}

interface UseRealtimeChatResult {
  connectionState: RealtimeConnectionState
  lastEvent: RealtimeServerEvent | null
  connect: () => void
  disconnect: () => void
  sendEvent: (event: RealtimeClientEvent) => boolean
  sendText: (text: string) => boolean
  sendInterrupt: () => boolean
}

export function useRealtimeChat({ enabled, token, conversationId, onEvent }: UseRealtimeChatOptions): UseRealtimeChatResult {
  const socketRef = useRef<WebSocket | null>(null)
  const onEventRef = useRef<typeof onEvent>(onEvent)
  const [connectionState, setConnectionState] = useState<RealtimeConnectionState>('idle')
  const [lastEvent, setLastEvent] = useState<RealtimeServerEvent | null>(null)

  useEffect(() => {
    onEventRef.current = onEvent
  }, [onEvent])

  const wsUrl = useMemo(() => {
    if (!enabled || !token) {
      return null
    }
    return buildRealtimeChatWsUrl(token, conversationId)
  }, [enabled, token, conversationId])

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
    setConnectionState('idle')
  }, [])

  const connect = useCallback(() => {
    if (!wsUrl || socketRef.current) {
      return
    }

    const socket = new WebSocket(wsUrl)
    socketRef.current = socket
    setConnectionState('connecting')

    socket.onopen = () => {
      setConnectionState('connected')
    }

    socket.onmessage = (messageEvent) => {
      try {
        const event = JSON.parse(messageEvent.data) as RealtimeServerEvent
        setLastEvent(event)
        onEventRef.current?.(event)
      } catch {
        setConnectionState('error')
      }
    }

    socket.onerror = () => {
      setConnectionState('error')
    }

    socket.onclose = () => {
      socketRef.current = null
      setConnectionState((prev) => (prev === 'error' ? 'error' : 'idle'))
    }
  }, [wsUrl])

  const sendEvent = useCallback((event: RealtimeClientEvent) => {
    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return false
    }

    socket.send(JSON.stringify(event))
    return true
  }, [])

  const sendText = useCallback((text: string) => {
    return sendEvent({ type: 'text', text, conversation_id: conversationId })
  }, [conversationId, sendEvent])

  const sendInterrupt = useCallback(() => {
    return sendEvent({ type: 'interrupt', conversation_id: conversationId })
  }, [conversationId, sendEvent])

  useEffect(() => {
    if (!enabled || !token) {
      disconnect()
      return
    }

    connect()
    return () => {
      disconnect()
    }
  }, [enabled, token, connect, disconnect])

  return {
    connectionState,
    lastEvent,
    connect,
    disconnect,
    sendEvent,
    sendText,
    sendInterrupt,
  }
}