import { useCallback, useEffect, useState } from 'react'

import { AqiCard } from './components/AqiCard'
import { CampusMap } from './components/CampusMap'
import { ForecastChart } from './components/ForecastChart'
import { HistoryChart } from './components/HistoryChart'
import { api, ApiError } from './lib/api'
import type { Current, Forecast, HistoryPoint, Location } from './lib/types'

/** Как часто дашборд сам подтягивает свежие данные, мс. */
const REFRESH_INTERVAL = 5 * 60 * 1000

export default function App() {
  const [locations, setLocations] = useState<Location[]>([])
  const [active, setActive] = useState('main')
  const [current, setCurrent] = useState<Current | null>(null)
  const [history, setHistory] = useState<HistoryPoint[]>([])
  const [forecast, setForecast] = useState<Forecast | null>(null)
  const [readings, setReadings] = useState<Record<string, number | null>>({})
  const [hours, setHours] = useState(72)
  const [error, setError] = useState<string | null>(null)
  const [forecastError, setForecastError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .locations()
      .then(setLocations)
      .catch((exc: ApiError) => setError(exc.message))
  }, [])

  const load = useCallback(async () => {
    setError(null)
    try {
      const [currentData, historyData] = await Promise.all([
        api.current(active),
        api.history(active, hours),
      ])
      setCurrent(currentData)
      setHistory(historyData.points)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Не удалось загрузить данные')
    } finally {
      setLoading(false)
    }

    // Прогноз грузится отдельно: пока модель не обучена, эндпоинт отдаёт 404,
    // и это не должно ломать остальной дашборд.
    try {
      setForecast(await api.forecast(active))
      setForecastError(null)
    } catch (exc) {
      setForecast(null)
      setForecastError(exc instanceof Error ? exc.message : 'Прогноз недоступен')
    }
  }, [active, hours])

  useEffect(() => {
    void load()
    const timer = setInterval(() => void load(), REFRESH_INTERVAL)
    return () => clearInterval(timer)
  }, [load])

  // Значения AQI по всем точкам — для раскраски карты.
  useEffect(() => {
    if (locations.length === 0) return
    Promise.all(
      locations.map((location) =>
        api
          .current(location.code)
          .then((data) => [location.code, data.aqi] as const)
          .catch(() => [location.code, null] as const),
      ),
    ).then((pairs) => setReadings(Object.fromEntries(pairs)))
  }, [locations, current])

  return (
    <div className="page">
      <div className="topbar">
        <div className="brand">
          <span className="brand__dot" aria-hidden="true" />
          Воздух кампуса
          <span className="brand__sub">КБТУ</span>
        </div>

        <nav className="pills" aria-label="Точки наблюдения">
          {locations.map((location) => (
            <button
              key={location.code}
              type="button"
              className={`pill ${location.code === active ? 'is-active' : ''}`}
              onClick={() => setActive(location.code)}
            >
              {location.title}
            </button>
          ))}
        </nav>
      </div>

      <header className="masthead">
        <h1>Чем мы дышим на кампусе прямо сейчас</h1>
        <p>
          Можно ли сегодня заниматься спортом на улице и открывать окна в аудиториях — ответ
          обновляется каждый час.
        </p>
      </header>

      <main className="grid">
        {error && <div className="alert alert--error">{error}</div>}
        {loading && !current && <div className="alert">Загружаем данные…</div>}

        {current && <AqiCard data={current} />}

        <HistoryChart points={history} hours={hours} onHoursChange={setHours} />

        <CampusMap
          locations={locations}
          readings={readings}
          active={active}
          onSelect={setActive}
        />

        {forecast ? (
          <ForecastChart forecast={forecast} />
        ) : (
          <section className="card">
            <h2>Прогноз</h2>
            <p className="empty">{forecastError ?? 'Прогноз пока не рассчитан.'}</p>
          </section>
        )}
      </main>

      <footer className="footer">
        <strong>KBTU Air Quality Kampus</strong>
        Источник данных —{' '}
        <a href="https://open-meteo.com/" target="_blank" rel="noreferrer noopener">
          Open-Meteo Air Quality API
        </a>
        . Индекс AQI рассчитан по методике US&nbsp;EPA, прогноз на 48 часов строит градиентный
        бустинг, обученный на архиве наблюдений и погоды.
        <br />
        Учебный проект производственной практики КБТУ.
      </footer>
    </div>
  )
}
