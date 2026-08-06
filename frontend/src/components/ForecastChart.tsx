import {
  Area,
  AreaChart,
  CartesianGrid,
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
  CHART_MUTED,
  TOOLTIP_STYLE,
  thresholdLabel,
} from '../lib/chartTheme'
import type { Forecast } from '../lib/types'

interface Props {
  forecast: Forecast
}

export function ForecastChart({ forecast }: Props) {
  const data = forecast.points.map((point) => ({
    ts: point.target_ts,
    label: formatHour(point.target_ts),
    aqi: point.aqi_pred,
    pm25: point.pm25_pred,
  }))

  return (
    <section className="card">
      <header className="card__head">
        <h2>Прогноз на {forecast.horizon_hours} часов</h2>
        <span className="muted">
          модель <code>{forecast.model_version}</code>
          {forecast.generated_at && ` · рассчитан ${formatTime(forecast.generated_at)}`}
        </span>
      </header>

      {forecast.worst && (
        <p className="forecast__peak">
          <span>
            Пик загрязнения ожидается <b>{formatTime(forecast.worst.target_ts)}</b> —{' '}
            <b>AQI {forecast.worst.aqi_pred}</b>
            {forecast.worst.aqi_category && `, ${forecast.worst.aqi_category.toLowerCase()}`}
          </span>
        </p>
      )}

      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data} margin={{ top: 8, right: 58, bottom: 0, left: -18 }}>
          <defs>
            <linearGradient id="forecastFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART_ACCENT} stopOpacity={0.34} />
              <stop offset="100%" stopColor={CHART_ACCENT} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={CHART_GRID} vertical={false} />
          <XAxis
            dataKey="label"
            minTickGap={40}
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
            formatter={(value: number) => [Math.round(value), 'AQI (прогноз)']}
          />
          {/* Границы категорий «Хорошо» и «Умеренно» — ориентир для чтения графика */}
          <ReferenceLine
            y={50}
            stroke={CHART_MUTED}
            strokeDasharray="4 4"
            label={thresholdLabel('AQI 50')}
          />
          <ReferenceLine
            y={100}
            stroke={CHART_ACCENT}
            strokeOpacity={0.5}
            strokeDasharray="4 4"
            label={thresholdLabel('AQI 100')}
          />
          <Area
            type="monotone"
            dataKey="aqi"
            name="aqi"
            stroke={CHART_ACCENT}
            strokeWidth={2.5}
            fill="url(#forecastFill)"
            activeDot={{ r: 5, strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </section>
  )
}
