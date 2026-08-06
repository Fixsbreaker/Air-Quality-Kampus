/**
 * Общие настройки оформления графиков.
 *
 * Вынесены в один модуль, чтобы график истории и график прогноза читались
 * как одна система: одинаковые сетка, подписи осей и всплывающие подсказки.
 * Сетка намеренно бледная — линии данных должны быть заметно контрастнее
 * разметки.
 */

export const CHART_INK = '#121416'
export const CHART_ACCENT = '#ff5000'
export const CHART_MUTED = 'rgba(23, 28, 38, 0.34)'
export const CHART_GRID = 'rgba(23, 28, 38, 0.08)'

export const AXIS_TICK = {
  fontSize: 12,
  fontWeight: 500,
  fill: 'rgba(23, 28, 38, 0.45)',
  letterSpacing: '-0.01em',
} as const

export const TOOLTIP_STYLE = {
  contentStyle: {
    borderRadius: 16,
    border: 'none',
    boxShadow: '0 2px 4px rgb(18 20 22 / 6%), 0 18px 44px rgb(18 20 22 / 12%)',
    padding: '12px 14px',
    fontSize: 13,
    fontWeight: 500,
    letterSpacing: '-0.01em',
  },
  labelStyle: {
    color: 'rgba(23, 28, 38, 0.45)',
    fontSize: 12,
    fontWeight: 600,
    marginBottom: 6,
  },
  itemStyle: {
    padding: '2px 0',
    fontWeight: 600,
    color: CHART_INK,
  },
} as const

/** Подпись пороговой линии на графике. */
export function thresholdLabel(value: string) {
  return {
    value,
    position: 'right' as const,
    fontSize: 11,
    fontWeight: 600,
    fill: 'rgba(23, 28, 38, 0.34)',
  }
}
