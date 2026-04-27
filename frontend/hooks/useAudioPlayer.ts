import { useCallback, useRef } from 'react'

type StreamState = 'idle' | 'playing' | 'ended'

interface UseAudioPlayerOptions {
  onStreamStart?: (streamId: string) => void
  onStreamEnd?: (streamId: string) => void
}

export default function useAudioPlayer(opts: UseAudioPlayerOptions = {}) {
  const { onStreamStart, onStreamEnd } = opts
  const audioCtxRef = useRef<AudioContext | null>(null)
  const streamsRef = useRef(new Map<string, {
    sampleRate: number
    playbackOffset: number
    state: StreamState
    pendingTimeout?: number
    sources: AudioBufferSourceNode[]
  }>())

  const ensureAudioContext = useCallback(async () => {
    if (typeof window === 'undefined') return null
    if (!audioCtxRef.current || audioCtxRef.current.state === 'closed') {
      audioCtxRef.current = new AudioContext()
    }
    if (audioCtxRef.current.state === 'suspended') {
      try {
        await audioCtxRef.current.resume()
      } catch {
        // resume may fail when not triggered by user gesture — caller can prompt user
      }
    }
    return audioCtxRef.current
  }, [])

  const resume = useCallback(async () => {
    if (typeof window === 'undefined') return false
    if (!audioCtxRef.current) audioCtxRef.current = new AudioContext()
    try {
      await audioCtxRef.current.resume()
      return audioCtxRef.current.state === 'running'
    } catch {
      return false
    }
  }, [])

  const getAudioState = useCallback(() => {
    return audioCtxRef.current?.state ?? 'closed'
  }, [])

  const decodeBase64ToInt16 = useCallback((base64: string) => {
    const binary = atob(base64)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
    return new Int16Array(bytes.buffer)
  }, [])

  const startStream = useCallback(async (streamId: string, sampleRate = 24000) => {
    const audioCtx = await ensureAudioContext()
    if (!audioCtx) return
    streamsRef.current.set(streamId, {
      sampleRate,
      playbackOffset: audioCtx.currentTime + 0.05,
      state: 'playing',
      sources: [],
    })
    onStreamStart?.(streamId)
  }, [ensureAudioContext, onStreamStart])

  const appendChunk = useCallback(async (streamId: string, pcmChunkBase64: string) => {
    const audioCtx = await ensureAudioContext()
    if (!audioCtx) return
    const meta = streamsRef.current.get(streamId)
    if (!meta) {
      // auto-start stream with default sample rate
      await startStream(streamId)
    }
    const effective = streamsRef.current.get(streamId)!
    const PCM_MAX_INT16 = 32768
    const pcm = decodeBase64ToInt16(pcmChunkBase64)
    const audioBuffer = audioCtx.createBuffer(1, pcm.length, effective.sampleRate)
    const channel = audioBuffer.getChannelData(0)
    for (let i = 0; i < pcm.length; i += 1) channel[i] = pcm[i] / PCM_MAX_INT16

    const source = audioCtx.createBufferSource()
    source.buffer = audioBuffer
    source.connect(audioCtx.destination)

    const now = audioCtx.currentTime
    const startAt = Math.max(now, effective.playbackOffset || now)
    source.start(startAt)
    effective.playbackOffset = startAt + audioBuffer.duration
    effective.sources.push(source)
    streamsRef.current.set(streamId, effective)
  }, [ensureAudioContext, decodeBase64ToInt16, startStream])

  const endStream = useCallback(async (streamId: string) => {
    const audioCtx = await ensureAudioContext()
    if (!audioCtx) return
    const meta = streamsRef.current.get(streamId)
    if (!meta) return
    meta.state = 'ended'
    // schedule cleanup after buffer finished playing
    const timeLeft = Math.max(0, meta.playbackOffset - audioCtx.currentTime)
    const timeoutId = window.setTimeout(() => {
      streamsRef.current.delete(streamId)
      onStreamEnd?.(streamId)
    }, (timeLeft + 0.05) * 1000)
    meta.pendingTimeout = timeoutId
    streamsRef.current.set(streamId, meta)
  }, [ensureAudioContext, onStreamEnd])

  const stopStream = useCallback((streamId: string) => {
    const meta = streamsRef.current.get(streamId)
    if (!meta) return
    if (meta.pendingTimeout) {
      clearTimeout(meta.pendingTimeout)
    }
    streamsRef.current.delete(streamId)
    onStreamEnd?.(streamId)
  }, [onStreamEnd])

  const stopAll = useCallback(() => {
    for (const [streamId, meta] of streamsRef.current) {
      if (meta.pendingTimeout) clearTimeout(meta.pendingTimeout)
      for (const src of meta.sources) {
        try { src.stop() } catch { /* already stopped or not yet started */ }
      }
      streamsRef.current.delete(streamId)
      onStreamEnd?.(streamId)
    }
  }, [onStreamEnd])

  const isPlaying = useCallback((streamId: string) => {
    const meta = streamsRef.current.get(streamId)
    return !!meta && meta.state === 'playing'
  }, [])

  return {
    startStream,
    appendChunk,
    endStream,
    stopStream,
    stopAll,
    isPlaying,
    ensureAudioContext,
    resume,
    getAudioState,
  }
}
