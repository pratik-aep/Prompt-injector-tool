import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Empty, ErrorNote, Input, PageHeader, Select, VerdictBadge, fmt } from '../components/ui'
import { useApp } from '../hooks/useAppState'
import { useAsync } from '../hooks/useAsync'
import { api } from '../services/api'
import type { Experiment } from '../types'

const PAGE = 25
export const download = (name: string, text: string, type = 'application/json') => {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type }))
  a.download = name; a.click(); URL.revokeObjectURL(a.href)
}

export default function History() {
  const { challenges, members, toast, refresh } = useApp()
  const [f, setF] = useState({ challenge_id: '', verdict: '', mode: '', owner_id: '', strategy_id: '', tag: '', q: '' })
  const [page, setPage] = useState(0)
  const [sel, setSel] = useState<string[]>([])
  const [cmp, setCmp] = useState<Experiment[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const file = useRef<HTMLInputElement>(null)
  const res = useAsync(() => api.experiments({ ...f, limit: PAGE, offset: page * PAGE }), [JSON.stringify(f), page])
  const name = (id: string) => challenges.find((c) => c.id === id)?.name ?? id
  const set = (k: string, v: string) => { setF({ ...f, [k]: v }); setPage(0) }
  const pages = Math.max(1, Math.ceil((res.data?.total ?? 0) / PAGE))

  const doCompare = async () => { try { setCmp(await api.compare(sel)) } catch (e) { setErr(e instanceof Error ? e.message : String(e)) } }
  const onImport = async (file: File | undefined) => {
    if (!file) return
    try { const r = await api.importJson(JSON.parse(await file.text())); toast(`Imported ${r.experiments} experiment(s), skipped ${r.skipped}`); await res.reload(); await refresh() }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
  }

  return (
    <>
      <PageHeader title="Experiment History" sub="Every attempt is stored. Filter, annotate, compare and export."
        actions={<>
          <Button onClick={async () => download('promptforge-experiments.json', JSON.stringify(await api.exportJson(f.challenge_id || undefined), null, 2))}>Export JSON</Button>
          <Button onClick={async () => download('promptforge-experiments.csv', await api.exportCsv(f.challenge_id || undefined), 'text/csv')}>Export CSV</Button>
          <Button onClick={() => file.current?.click()}>Import JSON</Button>
          <input ref={file} type="file" accept="application/json" hidden aria-label="Import file" onChange={(e) => onImport(e.target.files?.[0])} />
        </>} />
      <ErrorNote error={err ?? res.error} />
      <Card className="mb-4">
        <div className="grid gap-2 md:grid-cols-4 lg:grid-cols-7">
          <Input placeholder="Search prompt / response / notes" aria-label="Search" value={f.q} onChange={(e) => set('q', e.target.value)} className="lg:col-span-2" />
          <Select aria-label="Challenge filter" value={f.challenge_id} onChange={(e) => set('challenge_id', e.target.value)}><option value="">All challenges</option>{challenges.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
          <Select aria-label="Verdict filter" value={f.verdict} onChange={(e) => set('verdict', e.target.value)}><option value="">Any verdict</option>{['verified_success', 'possible_success', 'failed', 'invalid_test', 'evaluation_error'].map((v) => <option key={v}>{v}</option>)}</Select>
          <Select aria-label="Mode filter" value={f.mode} onChange={(e) => set('mode', e.target.value)}><option value="">api + manual</option><option>api</option><option>manual</option></Select>
          <Select aria-label="Owner filter" value={f.owner_id} onChange={(e) => set('owner_id', e.target.value)}><option value="">Any owner</option>{members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</Select>
          <Input placeholder="tag" aria-label="Tag filter" value={f.tag} onChange={(e) => set('tag', e.target.value)} />
        </div>
      </Card>
      <Card title={`${res.data?.total ?? 0} experiment(s)`} actions={<Button small disabled={sel.length < 2} onClick={doCompare}>Compare selected ({sel.length})</Button>}>
        {res.data?.items.length === 0 ? <Empty>No experiments match.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-dim"><tr><th /><th className="pb-2">When</th><th>Challenge</th><th>Prompt</th><th>Mode</th><th>Result</th><th className="text-right">Latency</th><th>Owner</th></tr></thead>
              <tbody>
                {res.data?.items.map((x) => (
                  <tr key={x.id} className="border-t border-line">
                    <td className="py-1.5 pr-2"><input type="checkbox" aria-label={`Select ${x.id}`} checked={sel.includes(x.id)} onChange={(e) => setSel(e.target.checked ? [...sel, x.id].slice(-5) : sel.filter((s) => s !== x.id))} /></td>
                    <td className="pr-3 whitespace-nowrap text-dim">{fmt.time(x.created_at)}</td>
                    <td className="pr-3 whitespace-nowrap">{name(x.challenge_id)}</td>
                    <td className="max-w-sm truncate pr-3"><Link className="hover:text-accent" to={`/analyzer?id=${x.id}`}>{x.prompt_text}</Link>{x.tags.map((t) => <span key={t} className="ml-1 rounded bg-panel2 px-1 text-[10px] text-dim">{t}</span>)}</td>
                    <td className="pr-3 text-dim">{x.mode}</td><td className="pr-3"><VerdictBadge verdict={x.verdict} estimate={x.is_estimate} /></td>
                    <td className="pr-3 text-right tabular-nums text-dim">{fmt.ms(x.latency_ms)}</td>
                    <td className="text-dim">{members.find((m) => m.id === x.owner_id)?.name ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-3 flex items-center justify-between text-xs text-dim">
          <span>Page {page + 1} of {pages}</span>
          <span className="space-x-2"><Button small disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button><Button small disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Next</Button></span>
        </div>
      </Card>
      {cmp && (
        <Card title="Comparison" className="mt-5" actions={<Button small onClick={() => setCmp(null)}>Close</Button>}>
          <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${cmp.length}, minmax(0, 1fr))` }}>
            {cmp.map((c) => (
              <div key={c.id} className="min-w-0 text-xs">
                <div className="mb-2 flex items-center gap-2"><VerdictBadge verdict={c.verdict} /><span className="text-dim">score {c.score?.toFixed(2)} · {fmt.ms(c.latency_ms)}</span></div>
                <div className="mb-1 font-semibold text-dim">Prompt</div><pre className="mb-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-bg p-2">{c.prompt_text}</pre>
                <div className="mb-1 font-semibold text-dim">Response</div><pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-bg p-2">{c.response_text}</pre>
              </div>
            ))}
          </div>
        </Card>
      )}
    </>
  )
}
