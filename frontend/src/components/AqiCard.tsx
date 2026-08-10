import { aqiColor, aqiTextColor, formatTime } from '../lib/api'
import type { Current } from '../lib/types'

interface Props {
  data: Current
}

/**
 * Главная плашка дашборда.
 *
 * Композиция строится вокруг одного гигантского числа — так устроены
 * лендинги, где нужно донести одну цифру раньше всего остального. Здесь
 * этой цифрой служит индекс AQI, а фон плашки окрашен в цвет его категории:
 * ответ считывается по цвету ещё до того, как прочитано число.
 */
export function AqiCard({ data }: Props) {
  const { aqi, recommendation } = data
  const background = aqiColor(aqi)
  const color = aqiTextColor(aqi)

  return (
    <section className="hero" style={{ background, color }} aria-live="polite">
      <header className="hero__head">
        <span>{data.location.title}</span>
        <span className="hero__time">
          обновлено {formatTime(data.ts_local)}
          {data.stale && <span className="badge">данные устарели</span>}
        </span>
      </header>

      <div className="hero__figure">
        <span className="hero__number">{aqi ?? '—'}</span>
        <span className="hero__unit">AQI</span>
      </div>

      <h2 className="hero__category">{data.aqi_category ?? 'нет данных'}</h2>

      {recommendation && (
        <>
          <p className="hero__text">{recommendation.text}</p>

          <div className="hero__chips">
            <Chip ok={recommendation.outdoor_sport} label="Спорт на улице" />
            <Chip ok={recommendation.open_windows} label="Открывать окна" />
            <Chip ok={!recommendation.mask_advised} label="Без маски" />
          </div>

          <p className="hero__note">{recommendation.sensitive_groups_note}</p>
        </>
      )}

      <dl className="hero__stats">
        <Pollutant label="PM2.5" value={data.pm25} />
        <Pollutant label="PM10" value={data.pm10} />
        <Pollutant label="NO₂" value={data.no2} />
        <Pollutant label="O₃" value={data.o3} />
      </dl>
    </section>
  )
}

function Chip({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`chip ${ok ? '' : 'chip--no'}`}>
      <span className="chip__mark" aria-hidden="true">
        {ok ? '✓' : '✕'}
      </span>
      {label}
    </span>
  )
}

function Pollutant({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd>
        {value == null ? '—' : value.toFixed(1)}
        <small>мкг/м³</small>
      </dd>
    </div>
  )
}
