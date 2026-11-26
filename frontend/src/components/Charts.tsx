export interface ChartPoint {
  label: string
  value: number
}

interface ChartProps {
  points: ChartPoint[]
  height?: number
  unit?: string
  emptyMessage?: string
}

function normalize(points: ChartPoint[]): ChartPoint[] {
  return points.filter((point) => Number.isFinite(point.value)).slice(-24)
}

function formatValue(value: number, unit?: string): string {
  const text = Number.isInteger(value) ? String(value) : value.toFixed(1)
  return unit ? `${text}${unit}` : text
}

/** Dependency-free line chart for progress series. */
export function LineChart({ points, height = 180, unit, emptyMessage = 'Belum ada data perkembangan.' }: ChartProps) {
  const data = normalize(points)
  if (data.length === 0) return <p className="py-8 text-center text-sm text-slate-400">{emptyMessage}</p>

  const width = 640
  const pad = { top: 16, right: 16, bottom: 28, left: 40 }
  const max = Math.max(...data.map((item) => item.value), 1)
  const min = Math.min(...data.map((item) => item.value), 0)
  const span = max - min || 1
  const x = (index: number) => pad.left + (index * (width - pad.left - pad.right)) / Math.max(1, data.length - 1)
  const y = (value: number) => pad.top + (1 - (value - min) / span) * (height - pad.top - pad.bottom)
  const path = data.map((item, index) => `${index === 0 ? 'M' : 'L'}${x(index).toFixed(1)},${y(item.value).toFixed(1)}`).join(' ')

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label="Grafik perkembangan">
      <title>Grafik perkembangan</title>
      {[0, 0.5, 1].map((ratio) => (
        <line
          key={ratio}
          x1={pad.left}
          x2={width - pad.right}
          y1={pad.top + ratio * (height - pad.top - pad.bottom)}
          y2={pad.top + ratio * (height - pad.top - pad.bottom)}
          stroke="#e2e8f0"
          strokeWidth="1"
        />
      ))}
      <path d={path} fill="none" stroke="#4f46e5" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
      {data.map((item, index) => (
        <g key={`${item.label}-${index}`}>
          <circle cx={x(index)} cy={y(item.value)} r="3.5" fill="#4f46e5" />
          <text x={x(index)} y={height - 8} textAnchor="middle" fontSize="10" fill="#64748b">
            {item.label}
          </text>
        </g>
      ))}
      <text x={pad.left - 6} y={pad.top + 4} textAnchor="end" fontSize="10" fill="#64748b">
        {formatValue(max, unit)}
      </text>
      <text x={pad.left - 6} y={height - pad.bottom} textAnchor="end" fontSize="10" fill="#64748b">
        {formatValue(min, unit)}
      </text>
    </svg>
  )
}

/** Dependency-free horizontal bar chart for per-competency comparison. */
export function BarChart({ points, unit = '%', emptyMessage = 'Belum ada data untuk dibandingkan.' }: ChartProps) {
  const data = normalize(points)
  if (data.length === 0) return <p className="py-8 text-center text-sm text-slate-400">{emptyMessage}</p>

  const max = Math.max(...data.map((item) => item.value), 1)
  return (
    <div className="space-y-3">
      {data.map((item, index) => (
        <div key={`${item.label}-${index}`}>
          <div className="mb-1 flex items-center justify-between gap-3 text-xs text-slate-600">
            <span className="truncate">{item.label}</span>
            <span className="shrink-0 font-semibold text-slate-900">{formatValue(item.value, unit)}</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-brand-500"
              style={{ width: `${Math.max(0, Math.min(100, (item.value / max) * 100))}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
