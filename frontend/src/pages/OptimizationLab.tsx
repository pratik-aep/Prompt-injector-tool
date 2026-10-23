import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Lines } from '../components/charts'
import { Button, Card, Empty, ErrorNote, Field, Input, PageHeader, Progress, Select, Stat, VerdictBadge } from '../components/ui'
import { useApp } from '../hooks/useAppState'
import { useAsync } from '../hooks/useAsync'
import { api } from '../services/api'
import type { Run } from '../types'

const ACTIVE = ['pending', 'running', 'paused', 'awaiting_approval']
const REASONS: Record<string, string> = {
  verified_flag: 'A verified flag was obtained', budget_exhausted: 'Attempt budget exhausted', max_generations: 'Maximum generations reached',
  time_limit: 'Time limit reached', no_improvement: 'No meaningful improvement', cancelled: 'Cancelled', search_exhausted: 'No new distinct candidates left',
}

export default function OptimizationLab() {
  const { challenge, target, targets, member, refresh, toast } = useApp()
  const [cfg, setCfg] = useState({ population_size: 6, max_generations: 5, attempt_budget: 30, trials: 1, concurrency: 1, approval: 'auto', seed: '', time_limit_s: '', patience: 5, llm: '' })
  const [runId, setRunId] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [approved, setApproved] = useState<string[] | null>(null)
  const runs = useAsync(() => api.runs(challenge?.id), [challenge?.id], 3000)
  const detail = useAsync(() => (runId ? api.run(runId) : Promise.resolve(null)), [runId], runId ? 1000 : undefined)
  const run: Run | null = detail.data

  useEffect(() => { if (!runId && runs.data?.[0]) setRunId(runs.data[0].id) }, [runs.data, runId])
  useEffect(() => { setApproved(null) }, [run?.pending_approval?.map((p) => p.id).join(',')])

  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    setErr(null)
    try { await fn(); await detail.reload(true); await runs.reload(true); await refresh(); if (ok) toast(ok) } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
  }
  const start = () => act(async () => {
    if (!challenge) return
    const config: Record<string, unknown> = { population_size: cfg.population_size, max_generations: cfg.max_generations, attempt_budget: cfg.attempt_budget,
      trials: cfg.trials, concurrency: cfg.concurrency, approval: cfg.approval, patience: cfg.patience }
    if (cfg.seed !== '') config.seed = Number(cfg.seed)
    if (cfg.time_limit_s !== '') config.time_limit_s = Number(cfg.time_limit_s)
    if (cfg.llm) config.llm_target_id = cfg.llm
    const r = await api.startRun({ challenge_id: challenge.id, target_id: target?.id, owner_id: member?.id, config })
    setRunId(r.id)
  }, 'Optimization started')

  const cands = run?.candidates ?? []
  const byId = useMemo(() => Object.fromEntries(cands.map((c) => [c.id, c])), [cands])
  const isActive = !!run && ACTIVE.includes(run.state)
  const bestC = run?.best_candidate_id ? byId[run.best_candidate_id] : undefined
  const budget = (run?.config.attempt_budget as number) ?? 0
  const llm = targets.filter((t) => t.kind === 'ollama' && t.enabled)

  if (!challenge) return <Empty>Select a challenge first.</Empty>
  return (
    <>
      <PageHeader title="Optimization Lab" sub={`${challenge.name} — population search with feedback-based selection, mutation and a hard attempt budget. Fitness comes from evaluator scores only.`} />
      <ErrorNote error={err ?? detail.error} />
      <div className="grid gap-5 xl:grid-cols-12">
        <Card title="New run" className="xl:col-span-3">
          <div className="space-y-2.5">
            {([['population_size', 'Population size'], ['max_generations', 'Max generations'], ['attempt_budget', 'Attempt budget'], ['trials', 'Trials / candidate'], ['concurrency', 'Concurrency (1–4)'], ['patience', 'Patience (generations)']] as const).map(([k, l]) => (
              <Field key={k} label={l}><Input type="number" aria-label={l} value={cfg[k]} onChange={(e) => setCfg({ ...cfg, [k]: Number(e.target.value) })} /></Field>
            ))}
            <Field label="Time limit (s, optional)"><Input type="number" value={cfg.time_limit_s} onChange={(e) => setCfg({ ...cfg, time_limit_s: e.target.value })} /></Field>
            <Field label="Seed (optional, reproducible)"><Input type="number" value={cfg.seed} onChange={(e) => setCfg({ ...cfg, seed: e.target.value })} /></Field>
            <Field label="Approval"><Select aria-label="Approval mode" value={cfg.approval} onChange={(e) => setCfg({ ...cfg, approval: e.target.value })}><option value="auto">Automatic</option><option value="manual">Approve each generation</option></Select></Field>
            <Field label="LLM rewording (optional)"><Select value={cfg.llm} onChange={(e) => setCfg({ ...cfg, llm: e.target.value })}><option value="">Off (deterministic only)</option>{llm.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field>
            <p className="text-xs text-dim">Target: {target?.name}. Remaining challenge queries: {challenge.attempts_remaining}.</p>
            <Button variant="primary" className="w-full" onClick={start} disabled={isActive || target?.kind === 'manual'}>Start</Button>
          </div>
          <h3 className="mt-5 mb-2 text-xs font-semibold uppercase text-dim">Previous runs</h3>
          <ul className="space-y-1">
            {runs.data?.map((r) => (
              <li key={r.id}><button onClick={() => setRunId(r.id)} className={`w-full rounded px-2 py-1 text-left text-xs ${r.id === runId ? 'bg-accent/15 text-accent' : 'hover:bg-panel2'}`}>{new Date(r.created_at).toLocaleTimeString()} · {r.state} · {r.attempts_used} q</button></li>
            ))}
            {runs.data?.length === 0 && <li className="text-xs text-dim">None yet.</li>}
          </ul>
        </Card>

        <div className="space-y-5 xl:col-span-9">
          {!run ? <Empty>Start a run to see its population, lineage and score history here.</Empty> : (
            <>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <Stat label="State" value={<span className={run.state === 'completed' ? 'text-ok' : run.state === 'failed' ? 'text-bad' : ''}>{run.state.replace('_', ' ')}</span>} sub={run.stop_reason ? (REASONS[run.stop_reason] ?? run.stop_reason) : undefined} />
                <Stat label="Generation" value={`${run.generation + (isActive ? 1 : 0)} / ${run.config.max_generations}`} />
                <Stat label="Best fitness" value={run.best_fitness.toFixed(2)} sub={bestC ? <VerdictBadge verdict={bestC.verdict} /> : undefined} />
                <div className="rounded-lg border border-line bg-panel px-4 py-3"><div className="text-xs uppercase tracking-wide text-dim">Attempts</div><div className="mt-2"><Progress value={run.attempts_used} max={budget} label="Attempt budget" /></div></div>
              </div>

              <Card title="Controls">
                <div className="flex flex-wrap gap-2">
                  <Button disabled={run.state !== 'running'} onClick={() => act(() => api.runAction(run.id, 'pause'))}>Pause</Button>
                  <Button disabled={run.state !== 'paused'} onClick={() => act(() => api.runAction(run.id, 'resume'))}>Resume</Button>
                  <Button variant="danger" disabled={!isActive} onClick={() => act(() => api.runAction(run.id, 'cancel'), 'Cancelling…')}>Cancel</Button>
                  {run.state === 'interrupted' && <Button variant="primary" onClick={() => act(() => api.runAction(run.id, 'continue'), 'Continuing')}>Continue interrupted run</Button>}
                </div>
                {run.state === 'awaiting_approval' && run.pending_approval && (
                  <div className="mt-4 rounded-md border border-warn/40 bg-warn/5 p-3">
                    <div className="mb-2 text-sm font-medium text-warn">Approve generation {run.generation + 1} before any query is sent</div>
                    <ul className="max-h-60 space-y-1.5 overflow-y-auto">
                      {run.pending_approval.map((p) => {
                        const on = (approved ?? run.pending_approval!.map((x) => x.id)).includes(p.id)
                        return (
                          <li key={p.id} className="flex gap-2 text-xs"><input type="checkbox" aria-label={`Approve ${p.id}`} checked={on} onChange={() => {
                            const cur = approved ?? run.pending_approval!.map((x) => x.id); setApproved(on ? cur.filter((x) => x !== p.id) : [...cur, p.id]) }} />
                            <span><b className="text-dim">{p.op ?? p.strategy_id ?? 'seed'}</b> {p.text.slice(0, 160)}{p.text.length > 160 ? '…' : ''}</span></li>)
                      })}
                    </ul>
                    <div className="mt-3 flex gap-2"><Button variant="ok" onClick={() => act(() => api.approveRun(run.id, approved ?? run.pending_approval!.map((x) => x.id)), 'Approved')}>Approve & test</Button>
                      <Button variant="danger" onClick={() => act(() => api.runAction(run.id, 'reject'))}>Reject & stop</Button></div>
                  </div>
                )}
              </Card>

              {run.history.length > 0 && (
                <Card title="Improvement history">
                  <Lines label="Fitness by generation" series={[
                    { name: 'best so far', points: run.history.map((h) => ({ x: h.generation, y: h.best_fitness })) },
                    { name: 'generation mean', points: run.history.map((h) => ({ x: h.generation, y: h.mean_fitness })) }]} />
                </Card>
              )}

              <Card title="Candidate population & lineage" actions={<span className="text-xs text-dim">{cands.length} candidates</span>}>
                {cands.length === 0 ? <Empty>No candidates yet.</Empty> : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-left text-xs text-dim"><tr><th className="pb-2">Gen</th><th>Prompt</th><th>Origin</th><th>Parent(s)</th><th className="text-right">Fitness</th><th>Result</th></tr></thead>
                      <tbody>
                        {cands.map((c) => (
                          <tr key={c.id} className={`border-t border-line align-top ${c.id === run.best_candidate_id ? 'bg-ok/5' : ''}`}>
                            <td className="py-1.5 pr-3 tabular-nums">{c.generation}</td>
                            <td className="max-w-md pr-3">{c.experiment_id ? <Link className="hover:text-accent" to={`/analyzer?id=${c.experiment_id}`}>{c.text.slice(0, 110)}{c.text.length > 110 ? '…' : ''}</Link> : c.text.slice(0, 110)}</td>
                            <td className="pr-3 text-xs text-dim">{c.op ?? c.strategy_id ?? c.method}</td>
                            <td className="pr-3 text-xs text-dim">{c.parent_ids.length ? c.parent_ids.map((p) => `#${p.slice(-4)}${byId[p]?.fitness != null ? ` (${byId[p].fitness!.toFixed(2)})` : ''}`).join(' × ') : '—'}</td>
                            <td className="pr-3 text-right tabular-nums">{c.fitness != null ? c.fitness.toFixed(2) : '—'}</td>
                            <td><VerdictBadge verdict={c.verdict} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              {run.history.at(-1)?.improvements?.length ? (
                <Card title="Best mutation gains (latest generation)">
                  <ul className="space-y-1 text-sm">{run.history.at(-1)!.improvements.map((i) => <li key={i.child}><b>{i.op}</b> <span className={i.delta >= 0 ? 'text-ok' : 'text-bad'}>{i.delta >= 0 ? '+' : ''}{i.delta.toFixed(2)}</span> <span className="text-xs text-dim">vs parent #{i.parent?.slice(-4)}</span></li>)}</ul>
                </Card>
              ) : null}
            </>
          )}
        </div>
      </div>
    </>
  )
}
