import { Link } from 'react-router-dom'
import { Card, Empty, ErrorNote, PageHeader, Progress, Stat, VerdictBadge, fmt } from '../components/ui'
import { useApp } from '../hooks/useAppState'
import { useAsync } from '../hooks/useAsync'
import { api } from '../services/api'

export default function Overview() {
  const { challenges, targets, challenge } = useApp()
  const ov = useAsync(() => api.overview(), [challenges.length], 5000)
  const ol = useAsync(() => api.ollama(), [])
  const o = ov.data
  const name = (id: string) => challenges.find((c) => c.id === id)?.name ?? id

  return (
    <>
      <PageHeader title="Overview" sub="Live totals from the local database. Only evaluator-verified outcomes count as successes." />
      <ErrorNote error={ov.error} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Active challenges" value={o?.active_challenges ?? '—'} sub={o ? `${o.solved_challenges} solved` : undefined} />
        <Stat label="Total attempts" value={o?.total_attempts ?? '—'} sub={o ? `${o.invalid_tests} invalid` : undefined} />
        <Stat label="Verified successes" value={o?.verified_successes ?? '—'} sub={o ? `${o.possible_successes} possible (unverified)` : undefined} />
        <Stat label="Success rate" value={o ? fmt.pct(o.success_rate) : '—'} sub="verified ÷ valid attempts" />
        <Stat label="Remaining budget" value={o?.remaining_budget ?? '—'} sub="queries, active challenges" />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <Card title="Recent experiments" className="lg:col-span-2" actions={<Link className="text-xs text-accent" to="/history">View all</Link>}>
          {o && o.recent_experiments.length === 0 ? <Empty>No experiments yet. Open <Link className="text-accent" to="/studio">Prompt Studio</Link> to run your first test.</Empty> : (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-dim"><tr><th className="pb-2">When</th><th>Challenge</th><th>Prompt</th><th>Result</th></tr></thead>
              <tbody>
                {o?.recent_experiments.map((e) => (
                  <tr key={e.id} className="border-t border-line">
                    <td className="py-1.5 pr-3 text-dim whitespace-nowrap">{fmt.time(e.created_at)}</td>
                    <td className="pr-3 whitespace-nowrap">{name(e.challenge_id)}</td>
                    <td className="max-w-xs truncate pr-3"><Link className="hover:text-accent" to={`/analyzer?id=${e.id}`}>{e.prompt_preview}</Link></td>
                    <td><VerdictBadge verdict={e.verdict} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <div className="space-y-5">
          <Card title="Target status">
            <ul className="space-y-2 text-sm">
              <li className="flex items-center justify-between"><span>Ollama</span>
                <span className={ol.data?.server_up ? 'text-ok' : 'text-warn'}>{ol.loading ? 'checking…' : ol.data?.server_up ? `running · ${ol.data.models.length} model(s)` : ol.data?.installed ? 'installed, server not running' : 'not installed'}</span></li>
              {targets.map((t) => (
                <li key={t.id} className="flex items-center justify-between"><span className="truncate pr-2">{t.name}</span>
                  <span className={t.enabled ? 'text-dim' : 'text-warn'}>{t.kind}{t.enabled ? '' : ' · disabled'}</span></li>
              ))}
            </ul>
            <Link className="mt-3 inline-block text-xs text-accent" to="/targets">Configure targets →</Link>
          </Card>
          {challenge && (
            <Card title="Selected challenge">
              <div className="font-medium">{challenge.name}</div>
              <div className="mb-3 text-xs text-dim">{challenge.type.replace(/_/g, ' ')} · {challenge.difficulty}</div>
              <Progress value={challenge.attempts_used} max={challenge.query_budget} label="Query budget used" />
              <div className="mt-2 text-xs text-dim">{challenge.verified_flags.length} verified flag(s)</div>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
