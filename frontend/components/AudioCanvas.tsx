'use client'

import { useCallback, useEffect, useRef } from 'react'

export type AudioCanvasState = 'loading' | 'listening' | 'processing' | 'speaking'

interface AudioCanvasProps {
    state: AudioCanvasState
    analyser?: AnalyserNode | null
}

const BAR_COUNT = 40
const BAR_GAP = 3

export default function AudioCanvas({ state, analyser = null }: AudioCanvasProps) {
    const waveformCanvasRef = useRef<HTMLCanvasElement | null>(null)
    const waveformRAFRef = useRef<number>(0)
    const ambientPhaseRef = useRef(0)

    const initWaveformCanvas = useCallback(() => {
        const waveformCanvas = waveformCanvasRef.current
        if (!waveformCanvas) {
            return null
        }

        const waveformCtx = waveformCanvas.getContext('2d')
        if (!waveformCtx) {
            return null
        }

        const dpr = window.devicePixelRatio || 1
        const rect = waveformCanvas.getBoundingClientRect()
        waveformCanvas.width = rect.width * dpr
        waveformCanvas.height = rect.height * dpr
        waveformCtx.setTransform(1, 0, 0, 1, 0, 0)
        waveformCtx.scale(dpr, dpr)

        return waveformCtx
    }, [])

    const getStateColor = useCallback(() => {
        const colors: Record<AudioCanvasState, string> = {
            listening: '#259e51',
            processing: '#f59e0b',
            speaking: '#818cf8',
            loading: '#3a3d46',
        }

        return colors[state] || colors.loading
    }, [state])

    const drawWaveform = useCallback(() => {
        const waveformCanvas = waveformCanvasRef.current
        if (!waveformCanvas) {
            return
        }

        const waveformCtx = waveformCanvas.getContext('2d')
        if (!waveformCtx) {
            return
        }

        const w = waveformCanvas.getBoundingClientRect().width
        const h = waveformCanvas.getBoundingClientRect().height
        waveformCtx.clearRect(0, 0, w, h)

        const barWidth = (w - (BAR_COUNT - 1) * BAR_GAP) / BAR_COUNT
        const color = getStateColor()
        waveformCtx.fillStyle = color

        let dataArray: Uint8Array<ArrayBuffer> | null = null
        if (analyser) {
            dataArray = new Uint8Array(analyser.frequencyBinCount) as Uint8Array<ArrayBuffer>
            analyser.getByteFrequencyData(dataArray)
        }

        for (let i = 0; i < BAR_COUNT; i++) {
            let amplitude = 0

            if (dataArray) {
                const binIndex = Math.floor((i / BAR_COUNT) * dataArray.length * 0.6)
                amplitude = dataArray[binIndex] / 255
            }

            if (!dataArray || amplitude < 0.02) {
                ambientPhaseRef.current += 0.0001
                const drift = Math.sin(ambientPhaseRef.current * 3 + i * 0.4) * 0.5 + 0.5
                amplitude = 0.03 + drift * 0.04
            }

            const barH = Math.max(2, amplitude * (h - 4))
            const x = i * (barWidth + BAR_GAP)
            const y = (h - barH) / 2

            waveformCtx.globalAlpha = 0.3 + amplitude * 0.7
            waveformCtx.beginPath()
            const r = Math.min(barWidth / 2, barH / 2, 3)
            waveformCtx.roundRect(x, y, barWidth, barH, r)
            waveformCtx.fill()
        }

        waveformCtx.globalAlpha = 1
        waveformRAFRef.current = requestAnimationFrame(drawWaveform)
    }, [analyser, getStateColor])

    useEffect(() => {
        initWaveformCanvas()
        waveformRAFRef.current = requestAnimationFrame(drawWaveform)

        const handleResize = () => {
            initWaveformCanvas()
        }

        window.addEventListener('resize', handleResize)

        return () => {
            window.removeEventListener('resize', handleResize)
            cancelAnimationFrame(waveformRAFRef.current)
        }
    }, [drawWaveform, initWaveformCanvas])

    return (
        <div className='w-full flex items-center justify-center relative h-[52px] pointer-events-none shrink-0'>
            <canvas ref={waveformCanvasRef} className={'w-full h-full block'}></canvas>
        </div>
    )
}
