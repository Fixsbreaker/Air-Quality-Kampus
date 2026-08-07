import 'leaflet/dist/leaflet.css'

import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip } from 'react-leaflet'

import { aqiColor, aqiTextColor } from '../lib/api'
import type { Location } from '../lib/types'

interface Props {
  locations: Location[]
  readings: Record<string, number | null>
  active: string
  onSelect: (code: string) => void
}

/**
 * Карта города с точками наблюдения: учебный корпус и два общежития.
 *
 * Вместо стандартных маркеров Leaflet используются CircleMarker: они
 * красятся в цвет AQI прямо из данных и не требуют подключения файлов
 * с иконками, которые в сборке Vite пришлось бы патчить вручную.
 */
export function CampusMap({ locations, readings, active, onSelect }: Props) {
  if (locations.length === 0) return null

  const center: [number, number] = [
    locations.reduce((sum, item) => sum + item.lat, 0) / locations.length,
    locations.reduce((sum, item) => sum + item.lon, 0) / locations.length,
  ]

  // Источник отдаёт данные по расчётной сетке, а не с датчиков. Если выбранные
  // точки попали в одну её ячейку, значения совпадут. Молча показывать одинаковые
  // числа — значит вводить в заблуждение, поэтому совпадение проговаривается.
  const values = Object.values(readings).filter((value) => value != null)
  const sameGridCell = values.length > 1 && new Set(values).size === 1

  // Точки с неподтверждёнными координатами проговариваются явно: показывать
  // приблизительное положение как точное — значит выдавать догадку за факт.
  const unverified = locations.filter((item) => !item.verified)

  return (
    <section className="card card--side">
      <header className="card__head">
        <h2>Точки наблюдения</h2>
        <span className="muted">Кликните по точке</span>
      </header>

      {sameGridCell && (
        <p className="note">
          Показанные точки попали в один узел расчётной сетки источника (0.1°, около
          10&nbsp;км), поэтому значения совпадают. Различия внутри такой ячейки покажут
          только наземные датчики.
        </p>
      )}

      {unverified.length > 0 && (
        <p className="note">
          Координаты уточняются: {unverified.map((item) => item.title.toLowerCase()).join(', ')}.
          Положение задано приблизительно, по району расположения.
        </p>
      )}

      <MapContainer center={center} zoom={12} className="map" scrollWheelZoom={false}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {locations.map((location) => {
          const aqi = readings[location.code] ?? null
          const isActive = location.code === active

          return (
            <CircleMarker
              key={location.code}
              center={[location.lat, location.lon]}
              radius={isActive ? 19 : 14}
              pathOptions={{
                color: isActive ? '#121416' : '#ffffff',
                weight: isActive ? 3 : 2,
                fillColor: aqiColor(aqi),
                fillOpacity: 0.9,
              }}
              eventHandlers={{ click: () => onSelect(location.code) }}
            >
              {/*
                Подпись закреплена только у активной точки: учебный корпус и
                общежитие на Толе би стоят близко, и на масштабе, где в кадр
                попадает общежитие в Медеу, их постоянные подписи накладывались
                бы одна на другую. Состояние остальных точек читается по цвету.
              */}
              <Tooltip
                permanent={isActive}
                direction="center"
                className="map-label"
                opacity={1}
                offset={[0, 0]}
              >
                <span style={{ color: aqiTextColor(aqi) }}>{aqi ?? '—'}</span>
              </Tooltip>
              <Popup>
                <b>{location.title}</b>
                <br />
                {location.description}
                <br />
                AQI: <b>{aqi ?? 'нет данных'}</b>
              </Popup>
            </CircleMarker>
          )
        })}
      </MapContainer>
    </section>
  )
}
