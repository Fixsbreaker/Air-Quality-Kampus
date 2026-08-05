export interface Location {
  code: string
  title: string
  lat: number
  lon: number
  description: string
  /** Координаты сверены с официальным адресом, а не заданы приблизительно. */
  verified: boolean
}

export interface Recommendation {
  aqi: number
  category: string
  color: string
  text: string
  outdoor_sport: boolean
  open_windows: boolean
  mask_advised: boolean
  sensitive_groups_note: string
}

export interface Current {
  location: Location
  ts: string
  ts_local: string
  source: string
  pm25: number | null
  pm10: number | null
  no2: number | null
  o3: number | null
  aqi: number | null
  aqi_category: string | null
  dominant_pollutant: string | null
  recommendation: Recommendation | null
  stale: boolean
}

export interface HistoryPoint {
  ts: string
  pm25: number | null
  pm10: number | null
  aqi: number | null
  aqi_category: string | null
}

export interface History {
  location: string
  from_ts: string
  to_ts: string
  count: number
  points: HistoryPoint[]
}

export interface ForecastPoint {
  target_ts: string
  horizon_h: number
  pm25_pred: number
  aqi_pred: number
  aqi_category: string | null
}

export interface Forecast {
  location: string
  model_version: string
  generated_at: string | null
  horizon_hours: number
  points: ForecastPoint[]
  worst: ForecastPoint | null
}
