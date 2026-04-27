'use client'

interface AudioPlaybackBarProps {
  isPlaying: boolean
  onStop: () => void
}

export default function AudioPlaybackBar({ isPlaying, onStop }: AudioPlaybackBarProps) {
  if (!isPlaying) return null

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-indigo-50 border-t border-indigo-100">
      {/* Animated waveform bars */}
      <div className="flex items-center gap-[3px] h-5" aria-hidden="true">
        {[0, 1, 2, 3, 4].map((i) => (
          <span
            key={i}
            className="w-[3px] rounded-full bg-indigo-500 animate-[soundbar_1s_ease-in-out_infinite]"
            style={{
              height: '100%',
              animationDelay: `${i * 0.15}s`,
              animationName: 'soundbar',
            }}
          />
        ))}
      </div>

      <span className="text-sm text-indigo-700 flex-1">Assistant is speaking…</span>

      <button
        onClick={onStop}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-indigo-700 bg-indigo-100 hover:bg-indigo-200 transition-colors"
        aria-label="Stop audio and resume microphone"
      >
        {/* Stop icon */}
        <svg className="w-3.5 h-3.5" viewBox="0 0 14 14" fill="currentColor" aria-hidden="true">
          <rect x="2" y="2" width="10" height="10" rx="1" />
        </svg>
        Stop &amp; Listen
      </button>

      <style>{`
        @keyframes soundbar {
          0%, 100% { transform: scaleY(0.3); }
          50%       { transform: scaleY(1); }
        }
      `}</style>
    </div>
  )
}
