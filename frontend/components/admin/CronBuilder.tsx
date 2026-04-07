'use client'
import { useState, useEffect, useCallback, useRef } from 'react'
import { ChevronDown } from 'lucide-react'
import {
  utcCronToLocalTime,
  localTimeToUtcCron,
  parseCronExpression,
  detectCronFrequency,
  generateCronExpression,
  APP_TIMEZONE,
} from '@/lib/dateUtils'

interface CronBuilderProps {
  value: string
  onChange: (cron: string) => void
}

type Frequency = 'daily' | 'weekly' | 'monthly' | 'hourly'

export default function CronBuilder({ value, onChange }: CronBuilderProps) {
  const [frequency, setFrequency] = useState<Frequency>('daily')
  const [hour, setHour] = useState('9')
  const [minute, setMinute] = useState('0')
  const [dayOfWeek, setDayOfWeek] = useState<number[]>([1, 2, 3, 4, 5]) // Mon-Fri by default
  const [dayOfMonth, setDayOfMonth] = useState('1')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [customCron, setCustomCron] = useState(value)

  // Parse existing cron expression (convert from UTC storage to local display)
  // Only triggered when value prop changes from parent
  useEffect(() => {
    if (value && !showAdvanced) {
      try {
        const { minute: min, hour: hr, day, dow } = parseCronExpression(value)

        // Convert UTC cron time to local time for display
        const { hour: localHour, minute: localMinute } = utcCronToLocalTime(hr === '*' ? '0' : hr, min === '*' ? '0' : min)

        setMinute(min === '*' ? '0' : localMinute)
        setHour(hr === '*' ? '0' : localHour)

        // Detect frequency based on cron pattern
        const frequency = detectCronFrequency(value)
        if (frequency !== 'unknown') {
          setFrequency(frequency as Frequency)
        }

        // Parse day/dow specific values
        if (frequency === 'weekly') {
          const days = dow.split(',').map(Number).filter(n => !isNaN(n))
          setDayOfWeek(days.length > 0 ? days : [1, 2, 3, 4, 5])
        } else if (frequency === 'monthly') {
          setDayOfMonth(day === '?' ? '1' : day)
        }
      } catch {
        // Keep defaults if parse fails
      }
    }
  }, [value, showAdvanced])

  // Generate cron expression based on frequency (store in UTC)
  const generateCron = (): string => {
    // Convert local (Dubai) time to UTC for storage
    const { hour: utcHour, minute: utcMinute } = localTimeToUtcCron(hour, minute)
    return generateCronExpression(frequency, utcHour, utcMinute, dayOfMonth, dayOfWeek)
  }

  // Handle advanced mode toggle
  const handleAdvancedToggle = () => {
    if (showAdvanced) {
      // Switching back to UI mode
      onChange(generateCron())
    } else {
      // Switching to advanced mode - keep current cron
      setCustomCron(value || generateCron())
    }
    setShowAdvanced(!showAdvanced)
  }

  // Handle custom cron change
  const handleCustomCronChange = (cron: string) => {
    setCustomCron(cron)
    onChange(cron)
  }

  const toggleDay = (day: number) => {
    setDayOfWeek((prev: number[]) =>
      prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day]
    )
  }
  const changeCronValue = useCallback(() => {
    onChange(generateCron())
  }, [frequency, hour, minute, dayOfWeek, dayOfMonth])

  useEffect(() => {
    if (!showAdvanced) {
      changeCronValue()
    }
  }, [frequency, hour, minute, dayOfWeek, dayOfMonth])

  const DAYS = [
    { value: 0, short: 'Sun', label: 'Sunday' },
    { value: 1, short: 'Mon', label: 'Monday' },
    { value: 2, short: 'Tue', label: 'Tuesday' },
    { value: 3, short: 'Wed', label: 'Wednesday' },
    { value: 4, short: 'Thu', label: 'Thursday' },
    { value: 5, short: 'Fri', label: 'Friday' },
    { value: 6, short: 'Sat', label: 'Saturday' },
  ]

  if (showAdvanced) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-gray-900 dark:text-white">Cron Expression</label>
          <button
            type="button"
            onClick={handleAdvancedToggle}
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            Back to UI
          </button>
        </div>
        <input
          type="text"
          value={customCron}
          onChange={(e) => handleCustomCronChange(e.target.value)}
          placeholder="0 9 * * * (9 AM daily)"
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
        />
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Format: minute hour day month weekday — See{' '}
          <a
            href="https://crontab.guru"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            crontab.guru
          </a>
        </p>
      </div>
    )
  }

  const hours = Array.from({ length: 24 }, (_, i) => i)
  const minutes = Array.from({ length: 60 }, (_, i) => i)
  const daysOfMonth = Array.from({ length: 31 }, (_, i) => i + 1)

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Frequency</label>
        <div className="flex gap-2">
          {(['hourly', 'daily', 'weekly', 'monthly'] as const).map(freq => (
            <button
              key={freq}
              type="button"
              onClick={() => setFrequency(freq)}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${frequency === freq
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
            >
              {freq.charAt(0).toUpperCase() + freq.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Time Picker */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Hour</label>
          <div className="relative">
            <select
              value={hour}
              onChange={(e) => setHour(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 appearance-none"
            >
              {hours.map(h => (
                <option key={h} value={String(h)}>
                  {String(h).padStart(2, '0')}:00
                </option>
              ))}
            </select>
            <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Minute</label>
          <div className="relative">
            <select
              value={minute}
              onChange={(e) => setMinute(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 appearance-none"
            >
              {minutes.map(m => (
                <option key={m} value={String(m)}>
                  :{String(m).padStart(2, '0')}
                </option>
              ))}
            </select>
            <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          </div>
        </div>
      </div>

      {/* Weekly day selector */}
      {frequency === 'weekly' && (
        <div>
          <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Days</label>
          <div className="grid grid-cols-7 gap-2">
            {DAYS.map(day => (
              <button
                key={day.value}
                type="button"
                onClick={() => toggleDay(day.value)}
                className={`px-2 py-2 rounded text-xs font-medium transition-colors ${dayOfWeek.includes(day.value)
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
                title={day.label}
              >
                {day.short}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Monthly day selector */}
      {frequency === 'monthly' && (
        <div>
          <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">Day of Month</label>
          <div className="relative">
            <select
              value={dayOfMonth}
              onChange={(e) => setDayOfMonth(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 appearance-none"
            >
              {daysOfMonth.map(d => (
                <option key={d} value={String(d)}>
                  {d === 1 ? 'Day 1 (1st)' : d === 2 ? 'Day 2 (2nd)' : d === 3 ? 'Day 3 (3rd)' : `Day ${d} (${d}th)`}
                </option>
              ))}
            </select>
            <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          </div>
        </div>
      )}

      {/* Cron preview */}
      <div className="px-3 py-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Cron Expression (UTC):</p>
        <p className="font-mono text-sm text-gray-900 dark:text-white mb-2">{generateCron()}</p>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Display Time (Asia/Dubai):</p>
        <p className="font-mono text-sm text-gray-900 dark:text-white">{String(hour).padStart(2, '0')}:{String(minute).padStart(2, '0')}</p>
      </div>

      {/* Advanced mode toggle */}
      <button
        type="button"
        onClick={handleAdvancedToggle}
        className="text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium"
      >
        Switch to Advanced Mode
      </button>
    </div>
  )
}
