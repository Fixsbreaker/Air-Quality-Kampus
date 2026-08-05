import type { Current, Forecast, History, Location } from './types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, params: Record<string, string> = {}): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`)
  Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, value))

  const response = await fetch(url.toString())
  if (!response.ok) {
    let detail = `Ошибка ${response.status}`
    try {
      const body = await response.json()
      if (body?.detail) detail = body.detail
    } catch {
      // тело ответа не JSON — оставляем текст по умолчанию
    }
    throw new ApiError(detail, response.status)
  }
  return response.json() as Promise<T>
}

export const api = {
  locations: () => request<Location[]>('/api/locations'),

  current: (location: string) => request<Current>('/api/current', { location }),

  history: (location: string, hours: number) => {
    const to = new Date()
    const from = new Date(to.getTime() - hours * 3600 * 1000)
    return request<History>('/api/history', {
      location,
      from: from.toISOString().slice(0, 19),
      to: to.toISOString().slice(0, 19),
    })
  },

  forecast: (location: string, hours = 48) =>
    request<Forecast>('/api/forecast', { location, hours: String(hours) }),
}

/**
 * Цвет по шкале US EPA — тот же, что использует backend и бот.
 *
 * Эта палитра намеренно не подчиняется брендовой: здесь цвет является
 * данными. Пользователь считывает состояние воздуха по цвету раньше,
 * чем прочитывает цифру, поэтому подменять её акцентным цветом нельзя.
 */
export function aqiColor(aqi: number | null | undefined): string {
  if (aqi == null) return '#94a3b8'
  if (aqi <= 50) return '#009966'
  if (aqi <= 100) return '#ffde33'
  if (aqi <= 150) return '#ff9933'
  if (aqi <= 200) return '#cc0033'
  return '#7e0023'
}

/**
 * Цвет текста поверх плашки AQI.
 *
 * Жёлтая и оранжевая полосы шкалы светлые — на них читается тёмный текст;
 * зелёная, красная и фиолетовая тёмные — на них белый. Без этого разделения
 * на жёлтом фоне белый текст теряет контраст.
 */
export function aqiTextColor(aqi: number | null | undefined): string {
  const INK = '#121416'
  if (aqi == null) return '#ffffff'
  return aqi > 50 && aqi <= 150 ? INK : '#ffffff'
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatHour(iso: string): string {
  return new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}
