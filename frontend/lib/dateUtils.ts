import { toZonedTime, fromZonedTime } from 'date-fns-tz'

// Application timezone configuration
export const APP_TIMEZONE = 'Asia/Dubai'

/**
 * Convert UTC cron hour/minute to local (Dubai) time
 * @param utcHour - Hour in UTC (0-23)
 * @param utcMinute - Minute in UTC (0-59)
 * @returns Object with hour and minute in local timezone
 */
export function utcCronToLocalTime(utcHour: string, utcMinute: string): { hour: string; minute: string } {
  const utcHourNum = parseInt(utcHour, 10)
  const utcMinuteNum = parseInt(utcMinute, 10)

  // Create a proper UTC date using Date.UTC
  const utcDate = new Date(Date.UTC(2024, 0, 1, utcHourNum, utcMinuteNum, 0, 0))

  // Convert to local timezone (Dubai)
  const localDate = toZonedTime(utcDate, APP_TIMEZONE)

  const result = {
    hour: String(localDate.getHours()).padStart(2, '0'),
    minute: String(localDate.getMinutes()).padStart(2, '0'),
  }

  return result
}

/**
 * Convert local (Dubai) time to UTC cron hour/minute
 * @param localHour - Hour in local timezone (0-23)
 * @param localMinute - Minute in local timezone (0-59)
 * @returns Object with hour and minute in UTC
 */
export function localTimeToUtcCron(localHour: string, localMinute: string): { hour: string; minute: string } {
  const localHourNum = parseInt(localHour, 10)
  const localMinuteNum = parseInt(localMinute, 10)

  // Create a test UTC date at midnight to measure timezone offset
  const testUTC = new Date(Date.UTC(2024, 0, 1, 0, 0, 0, 0))

  // See what time this UTC midnight shows in Dubai
  const formatter = new Intl.DateTimeFormat('sv-SE', {
    timeZone: APP_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

  const formatted = formatter.format(testUTC)
  // Format is like: "2024-01-01 04:00" - split by space and then by colon
  const timePart = formatted.split(' ')[1] // Get "04:00"
  const [hourStr] = timePart.split(':')
  const midnightUTCShowsAsDubaiHour = parseInt(hourStr, 10)

  // If UTC 00:00 shows as Dubai 04:00, then Dubai = UTC + 4 hours
  // So to get Dubai HH:MM, we need UTC (HH - 4):(MM)

  const utcHour = localHourNum - midnightUTCShowsAsDubaiHour
  const utcMinute = localMinuteNum // No minute offset for timezone

  // Handle day wraparound
  let finalHour = utcHour
  if (finalHour < 0) finalHour += 24
  if (finalHour >= 24) finalHour -= 24

  const result = {
    hour: String(finalHour).padStart(2, '0'),
    minute: String(utcMinute).padStart(2, '0'),
  }
  return result
}

/**
 * Parse cron expression and return components
 * @param cronExpression - Cron expression string (min hour day month dow)
 * @returns Object with parsed cron components
 */
export function parseCronExpression(cronExpression: string): {
  minute: string
  hour: string
  day: string
  month: string
  dow: string
} {
  const parts = cronExpression.trim().split(/\s+/)
  if (parts.length < 5) {
    throw new Error('Invalid cron expression')
  }

  const [minute, hour, day, month, dow] = parts
  return { minute, hour, day, month, dow }
}

/**
 * Detect cron frequency from expression
 * @param cronExpression - Cron expression string
 * @returns Frequency type ('hourly' | 'daily' | 'weekly' | 'monthly' | 'unknown')
 */
export function detectCronFrequency(cronExpression: string): 'hourly' | 'daily' | 'weekly' | 'monthly' | 'unknown' {
  try {
    const { hour, day, dow } = parseCronExpression(cronExpression)

    // Hourly: minute is set, hour is wildcard
    if (hour === '*' && day === '*' && dow === '*') {
      return 'hourly'
    }

    // Daily: minute and hour are set, day and dow are wildcard
    if (hour !== '*' && day === '*' && dow === '*') {
      return 'daily'
    }

    // Weekly: dow is set, day is wildcard
    if (dow !== '*' && day === '*') {
      return 'weekly'
    }

    // Monthly: day is set, dow is wildcard
    if (day !== '*' && dow === '*') {
      return 'monthly'
    }

    return 'unknown'
  } catch {
    return 'unknown'
  }
}

/**
 * Generate cron expression from parameters
 * @param frequency - Frequency type
 * @param utcHour - Hour in UTC
 * @param utcMinute - Minute in UTC
 * @param dayOfMonth - Day of month (for monthly frequency)
 * @param daysOfWeek - Array of days (0-6, for weekly frequency)
 * @returns Cron expression string
 */
export function generateCronExpression(
  frequency: 'hourly' | 'daily' | 'weekly' | 'monthly',
  utcHour: string,
  utcMinute: string,
  dayOfMonth: string = '1',
  daysOfWeek: number[] = [1, 2, 3, 4, 5]
): string {
  switch (frequency) {
    case 'hourly':
      return `${utcMinute} * * * *`
    case 'daily':
      return `${utcMinute} ${utcHour} * * *`
    case 'weekly': {
      const days = daysOfWeek.sort().join(',')
      return `${utcMinute} ${utcHour} * * ${days}`
    }
    case 'monthly':
      return `${utcMinute} ${utcHour} ${dayOfMonth} * *`
    default:
      return `${utcMinute} ${utcHour} * * *`
  }
}
