import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button, Card, CopyButton, Empty, ErrorNote, Field, Input, PageHeader, Textarea, VerdictBadge, fmt } from '../components/ui'
import { useApp } from '../hooks/useAppState'
import { useAsync } from '../hooks/useAsync'
import { api } from '../services/api'

export default function ResponseAnalyzer() {
  const { challenge, members, member, toast } = useApp()
  const [sp, setSp] = useSearchParams()
  const id = sp.get('id')
  const recent = useAsync(() => api.experiments({ challenge_id: challenge?.id, limit: 25 }), [challenge?.id])
  const exp = useAsync(() => (id ? api.experiment(id) : Promise.resolve(null)), [id])
  const [notes, setNotes] = useState('')
  const [tags, setTags] = useState('')
  const [flag, setFlag] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const e = exp.data

  useEffect(() => { if (e) { setNotes(e.notes); setTags(e.tags.join(', ')) } }, [e?.id])
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setErr(null)
    try { await fn(); await exp.reload(true); toast(ok) } catch (x) { setErr(x instanceof Error ? x.message : String(x)) }
  }
  const owner = members.find((m) => m.id === e?.owner_id)?.name

  return (
    <>
      <PageHeader title="Response Analyzer" sub="Complete model response and the evaluator's reasoning. Responses are untrusted data and are rendered as plain text only." />
      <ErrorNote error={err ?? exp.error} />
      <div className="grid gap-5 lg:grid-cols-4">
        <Card title="Recent" className="lg:col-span-1">
          {recent.data?.items.length === 0 && <Empty>No experiments for this challenge.</Empty>}
          <ul className="max-h-[36rem] space-y-1 overflow-y-auto">
            {recent.data?.items.map((x) => (
              <li key={x.id}><button onClick={() => setSp({ id: x.id })} className={`w-full rounded px-2 py-1.5 text-left text-xs ${x.id === id ? 'bg-accent/15' : 'hover:bg-panel2'}`}>
                <div className="flex items-center justify-between"><VerdictBadge verdict={x.verdict} /><span className="text-dim">{fmt.time(x.created_at)}</span></div>
                <div className="mt-1 truncate text-dim">{x.prompt_text}</div></button></li>
            ))}
          </ul>
        </Card>

        <div className="space-y-5 lg:col-span-3">
          {!e ? <Empty>Select an experiment{id ? '…' : ' to inspect it.'}</Empty> : (
            <>
              <Card title="Verdict" actions={<VerdictBadge verdict={e.verdict} estimate={e.is_estimate} />}>
                <div className="mb-3 grid grid-cols-2 gap-3 text-sm md:grid-cols-5">
                  <div><div className="text-xs text-dim">Score</div>{e.score?.toFixed(2)}</div>
                  <div><div className="text-xs text-dim">Latency</div>{fmt.ms(e.latency_ms)}</div>
                  <div><div className="text-xs text-dim">Tokens in/out</div>{e.tokens_in ?? '—'} / {e.tokens_out ?? '—'}</div>
                  <div><div className="text-xs text-dim">Mode</div>{e.mode}</div>
                  <div><div className="text-xs text-dim">Owner</div>{owner ?? '—'}</div>
                </div>
                {e.is_estimate && <p className="mb-2 rounded border border-warn/40 bg-warn/5 p-2 text-xs text-warn">This verdict includes an AI-judge estimate. It is not a verified success.</p>}
                {e.error && <ErrorNote error={e.error} />}
                <h3 className="mb-1 text-xs font-semibold uppercase text-dim">Why this score</h3>
                <ul className="list-disc space-y-1 pl-5 text-sm">{e.reasons?.map((r) => <li key={r}>{r}</li>)}</ul>
                {e.checks && e.checks.length > 0 && (
                  <table className="mt-3 w-full text-xs">
                    <thead className="text-left text-dim"><tr><th>Check</th><th>Triggered</th><th>Progress</th><th>Deterministic</th></tr></thead>
                    <tbody>{e.checks.map((c, i) => <tr key={i} className="border-t border-line"><td className="py-1">{c.kind}</td><td>{c.triggered ? 'yes' : 'no'}</td><td className="tabular-nums">{c.progress.toFixed(2)}</td><td>{c.deterministic ? 'yes' : 'no (estimate)'}</td></tr>)}</tbody>
                  </table>
                )}
                {e.verdict === 'possible_success' && e.mode === 'manual' && (
                  <div className="mt-4 rounded-md border border-line p-3">
                    <p className="mb-2 text-xs text-dim">Confirm only after the competition's own verifier accepted the flag.</p>
                    <div className="flex gap-2"><Input className="mono" value={flag} onChange={(x) => setFlag(x.target.value)} placeholder="CTF{...}" aria-label="Flag to confirm" />
                      <Button variant="ok" disabled={!flag} onClick={() => act(() => api.confirmFlag(e.id, flag, member?.id), 'Flag recorded as verified')}>Confirm verified</Button></div>
                  </div>
                )}
              </Card>
              <div className="grid gap-5 md:grid-cols-2">
                <Card title="Prompt" actions={<CopyButton text={e.prompt_text} />}><pre className="whitespace-pre-wrap text-xs">{e.prompt_text}</pre></Card>
                <Card title="Complete response" actions={<CopyButton text={e.response_text ?? ''} />}><pre className="whitespace-pre-wrap text-xs" aria-label="Complete response">{e.response_text || '(empty)'}</pre></Card>
              </div>
              <Card title="Notes & tags">
                <div className="grid gap-3 md:grid-cols-2">
                  <Field label="Notes"><Textarea rows={3} value={notes} onChange={(x) => setNotes(x.target.value)} /></Field>
                  <Field label="Tags (comma separated)"><Input value={tags} onChange={(x) => setTags(x.target.value)} /></Field>
                </div>
                <Button className="mt-3" onClick={() => act(() => api.annotate(e.id, { notes, tags: tags.split(',').map((t) => t.trim()).filter(Boolean), owner_id: member?.id ?? e.owner_id ?? '' }), 'Saved')}>Save annotations</Button>
              </Card>
            </>
          )}
        </div>
      </div>
    </>
  )
}
