import { HBars, Lines } from '../components/charts'
import { Card, Empty, ErrorNote, PageHeader, fmt } from '../components/ui'
import { useApp } from '../hooks/useAppState'
import { useAsync } from '../hooks/useAsync'
import { api } from '../services/api'

export default function Analytics() {
  const { challenges } = useApp()
  const { data, error } = useAsync(() => api.analytics(), [])
  const a = data
  const hasData = !!a && a.by_target.length + a.by_strategy.length > 0
  const nm = (id: string) => challenges.find((c) => c.id === id)?.name ?? id
  const improving = a?.runs.filter((r) => r.series.length > 0) ?? []

  return (
    <>
      <PageHeader title="Analytics" sub="Computed from stored experiments only. Nothing here is sample data." />
      <ErrorNote error={error} />
      {a && !hasData && <Empty>No experiments recorded yet — charts will appear once you run tests.</Empty>}
      {hasData && a && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card title="Success rate by attack strategy">
            <HBars label="Success rate by strategy" max={1} format={fmt.pct} rows={a.by_strategy.map((s) => ({ label: s.name, value: s.success_rate, sub: `${s.verified}/${s.attempts - s.invalid}` }))} />
            <p className="mt-2 text-xs text-dim">Verified successes ÷ valid attempts. Small samples are noisy.</p>
          </Card>
          <Card title="Attempts per challenge">
            <HBars label="Attempts per challenge" rows={a.by_challenge.filter((c) => c.attempts > 0).map((c) => ({ label: nm(c.challenge_id), value: c.attempts, sub: `of ${c.budget} · ${c.verified} verified` }))} />
          </Card>
          <Card title="Model comparison">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-dim"><tr><th className="pb-2">Target</th><th className="text-right">Attempts</th><th className="text-right">Success</th><th className="text-right">Avg latency</th><th className="text-right">p95</th></tr></thead>
              <tbody>{a.by_target.map((t) => <tr key={t.target_id} className="border-t border-line"><td className="py-1.5">{t.name}<div className="text-xs text-dim">{t.kind}</div></td><td className="text-right tabular-nums">{t.attempts}</td><td className="text-right tabular-nums">{fmt.pct(t.success_rate)}</td><td className="text-right tabular-nums">{fmt.ms(t.avg_latency_ms)}</td><td className="text-right tabular-nums">{fmt.ms(t.p95_latency_ms)}</td></tr>)}</tbody>
            </table>
          </Card>
          <Card title="Token usage by target">
            {a.by_target.some((t) => t.tokens_in + t.tokens_out > 0)
              ? <HBars label="Token usage" rows={a.by_target.map((t) => ({ label: t.name, value: t.tokens_in + t.tokens_out, sub: `${t.tokens_in} in / ${t.tokens_out} out` }))} />
              : <Empty>Targets have not reported token counts.</Empty>}
          </Card>
          <Card title="Optimization improvement" className="lg:col-span-2">
            {improving.length === 0 ? <Empty>No optimization runs yet.</Empty> : (
              <Lines label="Best fitness per generation by run" series={improving.slice(0, 5).map((r) => ({ name: `${nm(r.challenge_id)} (${r.stop_reason ?? r.state})`, points: r.series.map((s) => ({ x: s.generation, y: s.best_fitness })) }))} />
            )}
          </Card>
        </div>
      )}
    </>
  )
}
