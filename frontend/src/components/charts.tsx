/** Small dependency-free SVG charts. They render only real data passed in; empty input renders nothing. */
const COLORS = ['#5b8cff', '#3ecf8e', '#f2b84b', '#c084fc', '#f2647c', '#22d3ee']

export function HBars({ rows, format = (n: number) => String(n), max, label }: { rows: { label: string; value: number; sub?: string }[]; format?: (n: number) => string; max?: number; label: string }) {
  const top = max ?? Math.max(...rows.map((r) => r.value), 0.0001)
  return (
    <ul className="space-y-2" aria-label={label}>
      {rows.map((r) => (
        <li key={r.label}>
          <div className="mb-0.5 flex justify-between text-xs"><span className="truncate pr-2">{r.label}</span><span className="tabular-nums text-dim">{format(r.value)}{r.sub ? ` · ${r.sub}` : ''}</span></div>
          <div className="h-2 rounded bg-panel2"><div className="h-full rounded bg-accent" style={{ width: `${Math.max(1.5, (r.value / top) * 100)}%` }} /></div>
        </li>
      ))}
    </ul>
  )
}

export function Lines({ series, height = 140, label }: { series: { name: string; points: { x: number; y: number }[] }[]; height?: number; label: string }) {
  const all = series.flatMap((s) => s.points)
  if (!all.length) return null
  const W = 480, pad = 24
  const xs = all.map((p) => p.x), ys = all.map((p) => p.y)
  const x0 = Math.min(...xs), x1 = Math.max(...xs, x0 + 1), y0 = Math.min(0, ...ys), y1 = Math.max(...ys, y0 + 0.1)
  const sx = (x: number) => pad + ((x - x0) / (x1 - x0)) * (W - pad * 2)
  const sy = (y: number) => height - pad - ((y - y0) / (y1 - y0)) * (height - pad * 2)
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={label} className="w-full">
        <line x1={pad} y1={height - pad} x2={W - pad} y2={height - pad} stroke="#243049" />
        <line x1={pad} y1={pad} x2={pad} y2={height - pad} stroke="#243049" />
        <text x={pad - 4} y={pad + 4} textAnchor="end" fontSize="10" fill="#93a0b8">{y1.toFixed(1)}</text>
        <text x={pad - 4} y={height - pad} textAnchor="end" fontSize="10" fill="#93a0b8">{y0.toFixed(1)}</text>
        {series.map((s, i) => (
          <g key={s.name}>
            <polyline fill="none" stroke={COLORS[i % COLORS.length]} strokeWidth="2" points={s.points.map((p) => `${sx(p.x)},${sy(p.y)}`).join(' ')} />
            {s.points.map((p) => <circle key={p.x} cx={sx(p.x)} cy={sy(p.y)} r="3" fill={COLORS[i % COLORS.length]}><title>{`${s.name} gen ${p.x}: ${p.y}`}</title></circle>)}
          </g>
        ))}
        {xs.length > 0 && Array.from(new Set(xs)).map((x) => <text key={x} x={sx(x)} y={height - 8} textAnchor="middle" fontSize="10" fill="#93a0b8">{x}</text>)}
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-3 text-xs text-dim">
        {series.map((s, i) => <span key={s.name}><span className="mr-1 inline-block h-2 w-2 rounded-sm align-middle" style={{ background: COLORS[i % COLORS.length] }} />{s.name}</span>)}
      </figcaption>
    </figure>
  )
}
