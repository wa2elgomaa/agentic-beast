'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Message, OrchestratorResponse, QuerySuggestion } from '@/types'
import AudioCanvas from './AudioCanvas'
import ChatMessage from './ChatMessage'
import MessageInput, { AudioModeState, VoiceCapturePayload } from './MessageInput'
import WelcomeScreen from './WelcomeScreen'
import { buildRealtimeChatWsUrl, chat, getAccessToken } from '@/lib/api'
import useAudioPlayer from '@/hooks/useAudioPlayer'
import { useRealtimeChat } from '@/hooks/useRealtimeChat'
import clsx from 'clsx'

type VoiceState = 'loading' | 'listening' | 'processing' | 'speaking'

interface ChatAreaProps {
  messages: Message[]
  onNewMessage: (message: Message) => Promise<string | undefined>
  onConversationReady?: (conversationId: string, firstUserMessage: string) => Promise<void> | void
  onUpdateMessage: (id: string, updates: Partial<Message>) => void
  onAddMessage: (message: Message) => void
  currentConversationId: string | null
  hasMoreMessages: boolean
  onLoadMoreMessages: () => void
  isLoadingMore: boolean
  pendingQuestion?: string | null
  onQuestionProcessed?: () => void
}

export default function ChatArea({
  messages,
  onNewMessage,
  onConversationReady,
  onUpdateMessage,
  onAddMessage,
  currentConversationId,
  hasMoreMessages,
  onLoadMoreMessages,
  isLoadingMore,
  pendingQuestion,
  onQuestionProcessed
}: ChatAreaProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [audioModeState, setAudioModeState] = useState<AudioModeState>('idle')
  const [cameraEnabled, setCameraEnabled] = useState(false)
  const [mediaStream, setMediaStream] = useState<MediaStream | null>(null)
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null)
  const [playingStreams, setPlayingStreams] = useState<Record<string, boolean>>({})
  const audioPlayer = useAudioPlayer({
    onStreamStart: (id) => setPlayingStreams((s) => ({ ...s, [id]: true })),
    onStreamEnd: (id) => setPlayingStreams((s) => ({ ...s, [id]: false })),
  })
  const [pauseListening, setPauseListening] = useState(false)

  const messagesRef = useRef<Message[]>(messages)
  useEffect(() => { messagesRef.current = messages }, [messages])

  const token = getAccessToken()
  // const realtime = useRealtimeChat({
  //   enabled: !!token,
  //   token,
  //   conversationId: currentConversationId,
  //   onEvent: (event) => {
  //     try {
  //       if (!event || typeof event.type !== 'string') return

  //       if (event.type === 'audio_start') {
  //         // Pause local listening/transcription while assistant TTS streams
  //         setPauseListening(true)
  //         const streamId = (event.data && (event.data as any).stream_id) || null
  //         const sampleRate = (event.data && (event.data as any).sample_rate) || 24000
  //         const targetId = streamId || (messagesRef.current.slice().reverse().find(m => m.role === 'assistant')?.id)
  //         if (targetId) {
  //           void audioPlayer.startStream(targetId, sampleRate)
  //         }
  //         return
  //       }

  //       if (event.type === 'audio_chunk') {
  //         const chunk = event.data && (event.data as any).audio
  //         const streamId = (event.data && (event.data as any).stream_id) || null
  //         const targetId = streamId || (messagesRef.current.slice().reverse().find(m => m.role === 'assistant')?.id)
  //         if (typeof chunk === 'string' && targetId) {
  //           void audioPlayer.appendChunk(targetId, chunk)
  //         }
  //         return
  //       }

  //       if (event.type === 'audio_end') {
  //         // Resume listening/transcription after assistant TTS finished
  //         setPauseListening(false)
  //         const streamId = (event.data && (event.data as any).stream_id) || null
  //         const targetId = streamId || (messagesRef.current.slice().reverse().find(m => m.role === 'assistant')?.id)
  //         if (targetId) {
  //           void audioPlayer.endStream(targetId)
  //         }
  //         return
  //       }
  //     } catch {
  //       // ignore event processing errors
  //     }
  //   }
  // })
  const [audioAvailable, setAudioAvailable] = useState<boolean | null>(null)

  useEffect(() => {
    let mounted = true
    ;(async () => {
      try {
        const ctx = await audioPlayer.ensureAudioContext()
        if (!mounted) return
        setAudioAvailable(ctx?.state === 'running')
      } catch {
        if (!mounted) return
        setAudioAvailable(false)
      }
    })()
    return () => { mounted = false }
  }, [audioPlayer])

  const handleEnableAudio = async () => {
    const ok = await audioPlayer.resume()
    setAudioAvailable(!!ok)
  }
  const voiceState: VoiceState = isLoading
    ? 'processing'
    : audioModeState === 'listening'
      ? 'listening'
      : 'loading'

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    const videoEl = document.getElementById('video') as HTMLVideoElement | null
    if (!videoEl) {
      return
    }

    if (mediaStream && cameraEnabled && mediaStream.getVideoTracks().length > 0) {
      videoEl.srcObject = mediaStream
      videoEl.style.opacity = '1'
      return
    }

    videoEl.srcObject = null
    videoEl.style.opacity = cameraEnabled ? '1' : '0.3'
  }, [mediaStream, cameraEnabled])

  // Handle pending quick question
  useEffect(() => {
    if (pendingQuestion && !isLoading) {
      handleSendMessage(pendingQuestion)
      onQuestionProcessed?.()
    }
  }, [pendingQuestion, currentConversationId, isLoading])

  useEffect(() => {
    const handleQuickQuestion = (event: Event) => {
      const customEvent = event as CustomEvent<string>
      handleSendMessage(customEvent.detail)
    }

    window.addEventListener('quickQuestion', handleQuickQuestion)
    return () => window.removeEventListener('quickQuestion', handleQuickQuestion)
  }, [currentConversationId])  // Add dependency to update when conversation changes

  const buildAssistantContent = useCallback((response: OrchestratorResponse) => {
    switch (response.operation) {
      case 'suggest_tags_for_article_id':
      case 'suggest_tags_for_article_body': {
        const tagCount = response.data.results?.length || 0
        return `Found ${tagCount} relevant tags${response.data.article_id ? ` for article ${response.data.article_id}` : ''}.`
      }
      case 'query_documents':
        return response.data.answer || response.data.refined_query || response.data.note || 'Query processed successfully.'
      default:
        return response.data.note || response.data.answer || 'Operation completed successfully.'
    }
  }, [])

  const captureFrame = useCallback(() => {
    if (!cameraEnabled) {
      return null
    }

    const videoEl = document.getElementById('video') as HTMLVideoElement | null
    if (!videoEl || !videoEl.videoWidth || !videoEl.videoHeight) {
      return null
    }

    const canvas = document.createElement('canvas')
    const scale = 320 / videoEl.videoWidth
    canvas.width = 320
    canvas.height = videoEl.videoHeight * scale

    const context = canvas.getContext('2d')
    if (!context) {
      return null
    }

    context.drawImage(videoEl, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/jpeg', 0.7).split(',')[1]
  }, [cameraEnabled])

  // audioPlayer provides scheduling and playback lifecycle

  const runRealtimeVoiceTurn = useCallback(async (payload: {
    audioBase64: string
    imageBase64?: string | null
    durationMs: number
  }, streamId?: string) => {
    const token = getAccessToken()
    if (!token) {
      throw new Error('Missing authentication token for realtime chat.')
    }

    return new Promise<{ transcript: string | null; assistantText: string }>((resolve, reject) => {
      let finalized = false
      let transcript: string | null = null
      let assistantText = ''
      let sampleRate = 24000
      let audioStarted = false
        let assistantTextTimeout: number | null = null

      const wsUrl = buildRealtimeChatWsUrl(token, currentConversationId)
      const socket = new WebSocket(wsUrl)
      console.debug('[realtime] opening websocket', wsUrl)
      const timeoutId = window.setTimeout(() => {
        if (finalized) {
          return
        }
        finalized = true
        socket.close()
        reject(new Error('Realtime voice response timed out.'))
      }, 45000)

      const finishSuccess = () => {
        if (finalized) {
          return
        }
        finalized = true
        window.clearTimeout(timeoutId)
        socket.close()
        resolve({
          transcript,
          assistantText: assistantText.trim(),
        })
      }

      const finishError = (message: string) => {
        if (finalized) {
          return
        }
        finalized = true
        window.clearTimeout(timeoutId)
        socket.close()
        reject(new Error(message || 'Realtime voice processing failed.'))
      }

      socket.onopen = () => {
        console.debug('[realtime] websocket open, sending audio event')
        try {
          socket.send(JSON.stringify({
            type: 'audio',
            audio: payload.audioBase64,
            image: payload.imageBase64 || undefined,
            conversation_id: currentConversationId,
            metadata: {
              media_duration_ms: payload.durationMs,
            },
          }))
        } catch (err) {
          console.error('[realtime] failed to send audio event', err)
        }
      }

      socket.onmessage = (event) => {
        console.debug('[realtime] websocket message received', event.data)
        try {
          let parsed: any
          try {
            parsed = JSON.parse(event.data)
          } catch (err) {
            console.error('[realtime] failed to parse incoming message as JSON', event.data, err)
            throw err
          }

          if (parsed.type === 'error') {
            finishError(parsed.message || 'Realtime provider returned an error.')
            return
          }

          if (parsed.type === 'transcript') {
            transcript = parsed.message || transcript
            return
          }

          if (parsed.type === 'assistant_text') {
            assistantText = parsed.message || assistantText
            // Wait briefly for a possible audio_start to arrive; if none arrives
            // within the grace period, finalize the turn so speechless providers
            // still return promptly.
            if (assistantTextTimeout) {
              clearTimeout(assistantTextTimeout)
            }
            assistantTextTimeout = window.setTimeout(() => {
              if (!audioStarted && !finalized) {
                finishSuccess()
              }
            }, 300)
            return
          }
          if (parsed.type === 'audio_start') {
            audioStarted = true
            // If assistant begins streaming audio for this voice turn,
            // pause local listening/transcription while playback occurs.
            setPauseListening(true)
            const maybeRate = parsed.data?.sample_rate
            if (typeof maybeRate === 'number' && maybeRate > 0) {
              sampleRate = maybeRate
            }
            if (assistantTextTimeout) {
              clearTimeout(assistantTextTimeout)
              assistantTextTimeout = null
            }
            // map incoming audio stream to provided streamId (assistant message id)
            if (streamId) {
              void audioPlayer.startStream(streamId, sampleRate)
            }
            return
          }

          if (parsed.type === 'audio_chunk') {
            const chunk = parsed.data?.audio
            if (typeof chunk === 'string' && chunk.length > 0) {
              if (streamId) {
                void audioPlayer.appendChunk(streamId, chunk)
              }
            }
            return
          }

          if (parsed.type === 'audio_end') {
            // Resume listening/transcription once the assistant finishes.
            setPauseListening(false)
            if (streamId) {
              void audioPlayer.endStream(streamId)
            }
            finishSuccess()
          }
        } catch {
          finishError('Received invalid realtime response payload.')
        }
      }

      socket.onerror = (ev) => {
        console.error('[realtime] websocket error', ev)
        finishError('Realtime websocket connection failed.')
      }

      socket.onclose = (ev) => {
        console.debug('[realtime] websocket closed', ev)
        if (!finalized) {
          if (assistantText.trim()) {
            finishSuccess()
          } else {
            finishError('Realtime websocket closed before a response was completed.')
          }
        }
      }
    })
  }, [currentConversationId, audioPlayer, setPauseListening])
  

  const handleVoiceCaptured = useCallback(async ({ audioBase64, durationMs }: VoiceCapturePayload) => {
    // Prevent capturing new voice inputs while already processing or
    // while assistant TTS is streaming from the backend.
    if (isLoading || pauseListening) {
      return
    }
    
    const userMessageId = `${Date.now()}-voice-user`
    const assistantMessageId = `${Date.now()}-voice-assistant`
    const imageFrame = captureFrame()

    onAddMessage({
      id: userMessageId,
      role: 'user',
      content: 'Transcribing your voice question...',
      timestamp: new Date(),
      conversation_id: currentConversationId || undefined,
    })

    onAddMessage({
      id: assistantMessageId,
      role: 'assistant',
      content: 'Working on your question...',
      timestamp: new Date(),
      conversation_id: currentConversationId || undefined,
      isLoading: true,
    })

    setIsLoading(true)

    try {
      const result = await runRealtimeVoiceTurn({
        audioBase64,
        imageBase64: imageFrame,
        durationMs,
      }, assistantMessageId)

      onUpdateMessage(userMessageId, {
        content: result.transcript || 'Voice message',
        conversation_id: currentConversationId || undefined,
        metadata: {
          input_type: imageFrame ? 'camera_audio' : 'audio',
          transcript_source: 'polar_runtime',
          has_visual_context: Boolean(imageFrame),
          media_duration_ms: durationMs,
          modality_pipeline: 'polar_realtime_websocket',
        },
      })

      onUpdateMessage(assistantMessageId, {
        content: result.assistantText || 'No response generated.',
        conversation_id: currentConversationId || undefined,
        isLoading: false,
      })
    } catch (error) {
      onUpdateMessage(assistantMessageId, {
        content: `Error: ${error instanceof Error ? error.message : 'Voice processing failed.'}`,
        isLoading: false,
      })
    } finally {
      setIsLoading(false)
    }
  }, [captureFrame, currentConversationId, isLoading, onAddMessage, onUpdateMessage, runRealtimeVoiceTurn, pauseListening])

  const handleSendMessage = async (content: string) => {
    if (!content.trim() || isLoading) return

    // Add user message and get the conversation ID
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date(),
    }
    const conversationId = await onNewMessage(userMessage)

    // Add loading assistant message directly with the conversation ID
    const assistantMessageId = (Date.now() + 1).toString()
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isLoading: true,
      conversation_id: conversationId,
    }
    // Add assistant message directly without creating a conversation
    onAddMessage(assistantMessage)

    setIsLoading(true)

    const resolvedConversationId = conversationId || currentConversationId || null
    if (!currentConversationId && resolvedConversationId) {
      await onConversationReady?.(resolvedConversationId, content)
    }

    try {
      // Use new orchestrator API with conversation ID
      const response: OrchestratorResponse = await chat(
        content,
        conversationId,
        true,  // include context
        2      // context window (last 2 messages)
      )

      const backendConversationId = response.data.conversation_id || conversationId

      if (!response.success) {
        // Handle error response
        onUpdateMessage(assistantMessageId, {
          content: `Error: ${response.data.error || 'Operation failed'}`,
          isLoading: false,
        })
        return
      }

      const messageContent = buildAssistantContent(response)

      // Update assistant message with operation data
      onUpdateMessage(assistantMessageId, {
        content: messageContent,
        operation: response.operation,
        operationData: response.data,
        operationMetadata: response.metadata,
        // Expose chart/code interpreter output via typed metadata field
        metadata: response.metadata.chart_b64 || response.metadata.code_output ? {
          chart_b64: response.metadata.chart_b64,
          code_output: response.metadata.code_output,
          generated_sql: response.metadata.generated_sql,
        } : undefined,
        conversation_id: backendConversationId,
        isLoading: false,
      })
    } catch (error) {
      onUpdateMessage(assistantMessageId, {
        content: `Error: ${error instanceof Error ? error.message : 'Unknown error occurred'}`,
        isLoading: false,
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleSuggestionClick = async (suggestion: QuerySuggestion) => {
    if (isLoading || !currentConversationId) return

    // Add user message with the suggestion question
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: suggestion.question,
      timestamp: new Date(),
      conversation_id: currentConversationId,
    }
    await onNewMessage(userMessage)

    // Add assistant message with instant results (no AI call)
    const assistantMessageId = (Date.now() + 1).toString()
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isLoading: true,
      conversation_id: currentConversationId,
    }
    onAddMessage(assistantMessage)

    setIsLoading(true)

    try {
      // Execute the pre-generated SQL directly using chat
      const data: OrchestratorResponse = await chat(
        suggestion.question,
        currentConversationId,
        false,  // No need for context since SQL is pre-generated
        2,
        suggestion.sql  // Pass pre-generated SQL
      )

      if (!data.success) {
        onUpdateMessage(assistantMessageId, {
          content: `Error: ${data.data.error || 'Operation failed'}`,
          isLoading: false,
        })
        return
      }

      const messageContent = data.data.answer || 'Query processed successfully.'

      onUpdateMessage(assistantMessageId, {
        content: messageContent,
        operation: data.operation,
        operationData: data.data,
        operationMetadata: data.metadata,
        metadata: data.metadata.chart_b64 || data.metadata.code_output ? {
          chart_b64: data.metadata.chart_b64,
          code_output: data.metadata.code_output,
          generated_sql: data.metadata.generated_sql,
        } : undefined,
        isLoading: false,
      })
    } catch (error) {
      onUpdateMessage(assistantMessageId, {
        content: `Error: ${error instanceof Error ? error.message : 'Unknown error occurred'}`,
        isLoading: false,
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex-1 flex flex-col h-screen">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <WelcomeScreen onSendMessage={handleSendMessage} />
        ) : (
          <div className="max-w-4xl mx-auto px-4 py-8">
            {/* Load More Messages Button */}
            {hasMoreMessages && (
              <div className="flex justify-center mb-4">
                <button
                  onClick={onLoadMoreMessages}
                  disabled={isLoadingMore}
                  className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                >
                  {isLoadingMore ? 'Loading...' : 'Load More Messages'}
                </button>
              </div>
            )}

            {messages.map((message) => (
              <ChatMessage
                key={message.id}
                message={message}
                onSelectSuggestion={handleSuggestionClick}
                isPlaying={!!playingStreams[message.id]}
                onPlayToggle={() => {
                  if (playingStreams[message.id]) {
                    audioPlayer.stopStream(message.id)
                  } else {
                    void audioPlayer.startStream(message.id)
                  }
                }}
              />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>
      {/* Input Area */}
      <div className="border-t border-gray-200 bg-white">
        {(cameraEnabled && audioModeState === 'listening') ? <div
          id="viewportWrap"
          className={clsx(`block w-full max-w-[200px] max-h-[150px] top-[10px] right-[10px] h-full object-cover rounded-xl overflow-hidden bg-black fixed z-2`,
            voiceState === 'processing'
              ? '[box-shadow:0_0_80px_20px_rgba(245,158,11,0.18)] '
              : voiceState === 'listening'
                ? '[box-shadow:0_0_80px_20px_rgba(74,222,128,0.16)] '
                : '[box-shadow:0_0_80px_20px_rgba(58,61,70,0.12)]'
          )}
        >
          <div
            className={clsx(
              'pointer-events-none absolute inset-[-6px] z-[1] rounded-[22px] transition-[box-shadow,opacity] duration-300',
              voiceState === 'processing'
                ? '[box-shadow:0_0_80px_20px_rgba(245,158,11,0.18)] opacity-30'
                : voiceState === 'listening'
                  ? '[box-shadow:0_0_80px_20px_rgba(74,222,128,0.16)] opacity-40'
                  : '[box-shadow:0_0_80px_20px_rgba(58,61,70,0.12)] opacity-20'
            )}
          ></div>
          <video id="video" autoPlay muted playsInline></video>
        </div> : null}

        {/* Audio enable banner when autoplay is blocked */}
        {audioAvailable === false && (
          <div className="p-3 bg-yellow-50 border-t border-yellow-200 text-yellow-800 flex items-center justify-center">
            <span className="mr-3">Audio is blocked by the browser.</span>
            <button onClick={handleEnableAudio} className="px-3 py-1 bg-yellow-200 rounded">Enable audio</button>
          </div>
        )}

        <MessageInput
          onSendMessage={handleSendMessage}
          isLoading={isLoading}
          onAudioModeChange={setAudioModeState}
          onAnalyserChange={setAnalyser}
          onMediaStreamChange={setMediaStream}
          onCameraEnabledChange={setCameraEnabled}
          onVoiceCaptured={handleVoiceCaptured}
          pauseListening={pauseListening}
        >
          {voiceState === 'listening' ? <AudioCanvas state={voiceState} analyser={analyser} /> : null}
        </MessageInput>
      </div>
    </div>
  )
}
