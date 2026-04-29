'use client'

import { useEffect, useMemo, useRef, useState, KeyboardEvent } from 'react'
import { Loader2, Mic, Send, X } from 'lucide-react'
import { motion } from 'framer-motion'
import styles from './ChatArea.module.css'
import ToolSelector, { ToolType } from './ToolSelector'

export type AudioModeState = 'idle' | 'requesting_permission' | 'listening' | 'error'

export interface VoiceCapturePayload {
  audioBase64: string
  durationMs: number
}

type MicVADInstance = {
  start: () => void
  destroy: () => Promise<void> | void
}

interface MessageInputProps {
  onSendMessage: (message: string, toolHint?: ToolType) => void
  isLoading: boolean
  onAudioModeChange?: (state: AudioModeState) => void
  onAnalyserChange?: (analyser: AnalyserNode | null) => void
  onMediaStreamChange?: (stream: MediaStream | null) => void
  onCameraEnabledChange?: (enabled: boolean) => void
  onVoiceCaptured?: (payload: VoiceCapturePayload) => Promise<void> | void
  // When true, the input should stop listening/transcribing; when false,
  // resume if it was previously paused by this external control.
  pauseListening?: boolean
  children?: React.ReactNode
}

function float32ToWavBase64(samples: Float32Array, sampleRate: number = 16000): string {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)

  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i))
    }
  }

  writeString(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, samples.length * 2, true)

  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(44 + i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
  }

  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i])
  }

  return window.btoa(binary)
}

export default function MessageInput({
  onSendMessage,
  isLoading,
  onAudioModeChange,
  onAnalyserChange,
  onMediaStreamChange,
  onCameraEnabledChange,
  onVoiceCaptured,
  pauseListening,
  children,
}: MessageInputProps) {
  const [message, setMessage] = useState('')
  const [audioModeState, setAudioModeState] = useState<AudioModeState>('idle')
  const [audioError, setAudioError] = useState('')
  const [cameraEnabled, setCameraEnabled] = useState(false)
  const [selectedTool, setSelectedTool] = useState<ToolType>(null)

  const mediaStreamRef = useRef<MediaStream | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const micSourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const vadRef = useRef<MicVADInstance | null>(null)
  const utteranceSubmittingRef = useRef(false)
  const wasPausedByExternalRef = useRef(false)
  const isLoadingRef = useRef(isLoading)

  useEffect(() => {
    isLoadingRef.current = isLoading
  }, [isLoading])

  const hasTypedText = useMemo(() => message.trim().length > 0, [message])
  const isAudioActive = audioModeState === 'listening' || audioModeState === 'requesting_permission'

  const setAudioState = (nextState: AudioModeState) => {
    setAudioModeState(nextState)
    onAudioModeChange?.(nextState)
  }

  const ensureAudioCtx = async () => {
    if (!audioContextRef.current) {
      const AudioContextCtor = window.AudioContext || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!AudioContextCtor) {
        return null
      }

      audioContextRef.current = new AudioContextCtor()
      analyserRef.current = audioContextRef.current.createAnalyser()
      analyserRef.current.fftSize = 256
      analyserRef.current.smoothingTimeConstant = 0.75
    }

    if (audioContextRef.current.state === 'suspended') {
      await audioContextRef.current.resume()
    }

    return {
      audioContext: audioContextRef.current,
      analyser: analyserRef.current,
    }
  }

  const cleanupAudioMode = async () => {
    if (vadRef.current) {
      try {
        await vadRef.current.destroy()
      } catch {
        // Best effort destroy.
      }
      vadRef.current = null
    }

    if (micSourceRef.current) {
      try {
        micSourceRef.current.disconnect()
      } catch {
        // Best effort disconnect.
      }
      micSourceRef.current = null
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop())
      mediaStreamRef.current = null
    }

    if (audioContextRef.current) {
      try {
        await audioContextRef.current.close()
      } catch {
        // Best effort close.
      }
      audioContextRef.current = null
    }

    analyserRef.current = null
    onAnalyserChange?.(null)
    onMediaStreamChange?.(null)
  }

  // Pause/resume listening in response to external control (e.g. when the
  // assistant is streaming TTS audio). If `pauseListening` becomes true,
  // stop the current VAD / media stream. When it becomes false and we had
  // paused it previously, attempt to restart listening.
  useEffect(() => {
    if (pauseListening) {
      if (audioModeState === 'listening' || audioModeState === 'requesting_permission') {
        wasPausedByExternalRef.current = true
        void (async () => {
          try {
            await cleanupAudioMode()
          } finally {
            setAudioState('idle')
          }
        })()
      }
    } else {
      if (wasPausedByExternalRef.current) {
        wasPausedByExternalRef.current = false
        void startAudioMode()
      }
    }
    // Intentionally only run when the external pause flag changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pauseListening])

  const detachVideoTracks = () => {
    if (!mediaStreamRef.current) {
      return
    }

    mediaStreamRef.current.getVideoTracks().forEach((track) => {
      mediaStreamRef.current?.removeTrack(track)
      track.stop()
    })

    onMediaStreamChange?.(mediaStreamRef.current)
  }

  const attachVideoTrack = async () => {
    if (!mediaStreamRef.current) {
      return
    }

    const videoOnlyStream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 480, facingMode: 'user' },
    })

    videoOnlyStream.getVideoTracks().forEach((track) => {
      mediaStreamRef.current?.addTrack(track)
    })

    onMediaStreamChange?.(mediaStreamRef.current)
  }

  const handleCameraToggle = async () => {
    const nextEnabled = !cameraEnabled

    if (isAudioActive && mediaStreamRef.current) {
      try {
        if (nextEnabled) {
          await attachVideoTrack()
        } else {
          detachVideoTracks()
        }

        setCameraEnabled(nextEnabled)
        onCameraEnabledChange?.(nextEnabled)
        setAudioError('')
      } catch (error) {
        setAudioError(error instanceof Error ? error.message : 'Camera access failed.')
      }
      return
    }

    setCameraEnabled(nextEnabled)
    onCameraEnabledChange?.(nextEnabled)
  }

  const startAudioMode = async () => {
    if (isLoading || isAudioActive || typeof window === 'undefined') {
      return
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setAudioError('Microphone access is not supported in this browser.')
      setAudioState('error')
      return
    }

    setAudioError('')
    setAudioState('requesting_permission')

    try {
      let stream: MediaStream

      if (cameraEnabled) {
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480, facingMode: 'user' },
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
          })
        } catch {
          stream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
          })
        }
      } else {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        })
      }

      mediaStreamRef.current = stream
      onMediaStreamChange?.(stream)

      const audioRuntime = await ensureAudioCtx()
      if (!audioRuntime?.audioContext || !audioRuntime.analyser) {
        throw new Error('Audio context is not available.')
      }

      if (stream.getAudioTracks().length === 0) {
        throw new Error('No microphone track is available.')
      }

      micSourceRef.current = audioRuntime.audioContext.createMediaStreamSource(stream)
      micSourceRef.current.connect(audioRuntime.analyser)
      onAnalyserChange?.(audioRuntime.analyser)

      const { MicVAD } = await import('@ricky0123/vad-web')
      const vad = await MicVAD.new({
        getStream: async () => new MediaStream(stream.getAudioTracks()),
        positiveSpeechThreshold: 0.5,
        negativeSpeechThreshold: 0.25,
        redemptionMs: 600,
        minSpeechMs: 300,
        preSpeechPadMs: 300,
        onSpeechEnd: async (audio: Float32Array) => {
          if (!onVoiceCaptured || utteranceSubmittingRef.current || isLoadingRef.current) {
            return
          }

          if (audio.length < 1600) {
            return
          }

          utteranceSubmittingRef.current = true

          try {
            const audioBase64 = float32ToWavBase64(audio, 16000)
            const durationMs = Math.round((audio.length / 16000) * 1000)
            await onVoiceCaptured({ audioBase64, durationMs })
          } catch (captureError) {
            setAudioError(captureError instanceof Error ? captureError.message : 'Voice capture failed.')
          } finally {
            utteranceSubmittingRef.current = false
          }
        },
        onVADMisfire: () => {
          // Ignore short noise bursts.
        },
        onnxWASMBasePath: 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/',
        baseAssetPath: 'https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.29/dist/',
      })

      vadRef.current = vad as MicVADInstance
      vad.start()

      setAudioState('listening')
    } catch (error) {
      await cleanupAudioMode()
      setAudioError(error instanceof Error ? error.message : 'Microphone permission was denied.')
      setAudioState('error')
    }
  }

  const handleCancelAudioMode = async () => {
    await cleanupAudioMode()
    setAudioError('')
    setAudioState('idle')
  }

  const handleSubmit = () => {
    if (message.trim() && !isLoading) {
      onSendMessage(message, selectedTool)
      setMessage('')
      setSelectedTool(null)
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  // useEffect(() => {
  //   onCameraEnabledChange?.(cameraEnabled)
  // }, [cameraEnabled, onCameraEnabledChange])

  useEffect(() => {
    return () => {
      void cleanupAudioMode()
    }
  }, [])

  return (
    <div className="border-t border-gray-200 bg-white">
      <div className="max-w-4xl mx-auto px-4 py-2">
        {children}
        <div className="relative flex items-end gap-3">
          <div className='absolute left-2 bottom-0 top-0 m-auto flex items-center gap-2 h-[36px]'>
          <ToolSelector selectedTool={selectedTool} onSelectTool={setSelectedTool} />
          </div>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isAudioActive ? '' : 'Ask about your content performance...'}
            disabled={isLoading}
            rows={1}
            className="flex-1 resize-none bg-gray-50 text-gray-900 rounded-xl px-4 py-3 pl-16 pr-36 focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder:text-gray-400 disabled:opacity-50 max-h-[200px] border border-gray-200"
            style={{
              minHeight: '52px',
              height: 'auto',
            }}
          />
          <div className="absolute right-2 bottom-0 top-0 m-auto flex items-center gap-2 h-[36px]">
            {isAudioActive ? (
              <>
                <span className="w-[36px] h-[36px] rounded-full bg-gray-300 inline-flex items-center justify-center">
                  {audioModeState === 'requesting_permission' ? (
                    <Loader2 size={15} className="animate-spin text-gray-700" />
                  ) : (
                    <Mic size={18} className="text-green-700" />
                  )}
                </span>
                <motion.button
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => void handleCancelAudioMode()}
                  title="Cancel audio mode"
                  aria-label="Cancel audio mode"
                  className="h-[36px] px-5 rounded-full bg-black text-white inline-flex items-center gap-2 font-medium"
                >
                  <X size={15} />
                  <span>Cancel</span>
                </motion.button>
              </>
            ) : (
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={hasTypedText ? handleSubmit : () => void startAudioMode()}
                disabled={isLoading}
                title={hasTypedText ? 'Send message' : 'Start audio mode'}
                aria-label={hasTypedText ? 'Send message' : 'Start audio mode'}
                className={`w-[34px] h-[34px] p-2 rounded-lg transition-colors ${hasTypedText
                  ? 'bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:cursor-not-allowed'
                  : 'bg-teal-600 hover:bg-teal-500 disabled:bg-gray-700 disabled:cursor-not-allowed'
                  }`}
              >
                {hasTypedText ? (
                  <Send size={18} className="text-white" />
                ) : (
                  <Mic size={18} className="text-white" />
                )}
              </motion.button>
            )}
          </div>
        </div>

        {audioError && (
          <p className="text-xs text-red-600 mt-2 text-center">{audioError}</p>
        )}
        {!audioError && audioModeState === 'requesting_permission' && (
          <p className="text-xs text-amber-600 mt-2 text-center">Requesting microphone permission...</p>
        )}
        {!audioError && audioModeState === 'listening' && (
          <p className="text-xs text-teal-600 mt-2 text-center">Listening continuously. Click cancel when you want to stop.</p>
        )}

        <div className={'flex items-center justify-between mt-4 relative'}>
          {audioModeState === 'listening' ? <span className={styles.onDevicePill}>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="4" width="12" height="9" rx="2" /><path d="M5 4V3a3 3 0 0 1 6 0v1" /></svg>
            On-device
          </span> : <div></div>}
          <p className="text-xs text-gray-500 text-center">
            The Beast AI can make mistakes. Please verify important information.
          </p>
          {/* {audioModeState === 'listening' ? <button
            id="cameraToggle"
            type="button"
            onClick={() => void handleCameraToggle()}
            className={`${styles.ctrlBtn} ${cameraEnabled ? styles.active : ''}`}
          >
            {cameraEnabled ? 'Camera On' : 'Camera Off'}
          </button> : <div></div>} */}
          <div></div>
        </div>
      </div>
    </div>
  )
}
