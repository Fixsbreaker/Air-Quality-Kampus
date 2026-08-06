import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { formatHour, formatTime } from '../lib/api'
import {
  AXIS_TICK,
  CHART_ACCENT,
  CHART_GRID,
  CHART_INK,
  CHART_MUTED,
  TOOLTIP_STYLE,
} from '../lib/chartTheme'
import type { HistoryPoint } from '../lib/types'

interface Props {
  points: HistoryPoint[]
  hours: number
  onHoursChange: (hours: number) => void
}

const RANGES = [
  { label: '24 ч', value: 24 },
  { label: '3 дня', value: 72 },
  { label: 'Неделя', value: 168 },
  { label: 'Месяц', value: 720 },
]

/** Порог «умеренно» — визуальный ориентир: выше него воздух уже не идеален. */
const MODERATE_THRESHOLD = 50

export function HistoryChart({ points, hours, onHoursChange }: Props) {
  const data = points.map((point) => ({
    ts: point.ts,
    label: hours <= 48 ? formatHour(point.ts) : formatTime(point.ts),
    aqi: point.aqi,
    pm25: point.pm25,
    pm10: point.pm10,
  }))

  return (
    <section className="card card--half">
      <header className="card__head">
        <h2>История наблюдений</h2>
        <div className="pills" role="group" aria-label="Период">
          {RANGES.map((range) => (
            <button
              key={range.value}
              type="button"
              className={`pill ${range.value === hours ? 'is-active' : ''}`}
              onClick={() => onHoursChange(range.value)}
            >
              {range.label}
            </button>
          ))}
        </div>
      </header>

      {data.length === 0 ? (
        <p className="empty">За выбранный период данных нет.</p>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={data} margin={{ top: 8, right: 20, bottom: 0, left: -18 }}>
            <CartesianGrid stroke={CHART_GRID} vertical={false} />
            <XAxis
              dataKey="label"
              minTickGap={44}
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={{ stroke: CHART_GRID }}
            />
            <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={52} />
            <Tooltip
              {...TOOLTIP_STYLE}
              cursor={{ stroke: CHART_MUTED, strokeDasharray: '4 4' }}
              labelFormatter={(_, payload) =>
                payload?.[0] ? formatTime(String(payload[0].payload.ts)) : ''
              }
              formatter={(value: number, name: string) => [value?.toFixed?.(1) ?? value, name]}
            />
            <Legend
              iconType="plainline"
              wrapperStyle={{ fontSize: 13, fontWeight: 600, paddingTop: 12 }}
            />
            {/* Подпись не нужна: значение 50 и так подписано на оси Y,
                а на узком экране она наезжала на линию данных. */}
            <ReferenceLine y={MODERATE_THRESHOLD} stroke={CHART_MUTED} strokeDasharray="4 4" />
            <Line
              type="monotone"
              dataKey="aqi"
              name="AQI"
              stroke={CHART_INK}
              strokeWidth={2.5}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 0 }}
            />
            <Line
              type="monotone"
              dataKey="pm25"
              name="PM2.5"
              stroke={CHART_ACCENT}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
            />
            <Line
              type="monotone"
              dataKey="pm10"
              name="PM10"
              stroke={CHART_MUTED}
              strokeWidth={1.5}
              strokeDasharray="5 4"
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </section>
  )
}
