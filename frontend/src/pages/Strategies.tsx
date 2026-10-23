import { useRef, useState } from 'react'
import { Button, Card, Empty, ErrorNote, Field, Input, PageHeader, Textarea } from '../components/ui'
import { useApp } from '../hooks/useAppState'
import { useAsync } from '../hooks/useAsync'
import { api } from '../services/api'
import type { Strategy } from '../types'
import { download } from './History'

const TYPES = ['secret_extraction', 'instruction_hierarchy', 'format_enforcement', 'indirect_injection', 'tool_output_trust']
const blank = { name: '', category: 'Custom', description: '', template: '', variants: '', challenge_types: [] as string[], trust_boundary: '', limitations: '', evaluation_criteria: '' }

export default function Strategies() {
  const { toast } = useApp()
  const list = useAsync(() => api.strategies(), [])
  const [selId, setSelId] = useState<string | null>(null)
  const [form, setForm] = useState<typeof blank | null>(null)
  const [editId, setEditId] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const file = useRef<HTMLInputElement>(null)
  const sel = list.data?.find((s) => s.id === selId)
  const groups = Object.entries((list.data ?? []).reduce<Record<string, Strategy[]>>((a, s) => ((a[s.category] ||= []).push(s), a), {}))

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setErr(null)
    try { await fn(); await list.reload(true); toast(ok) } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
  }
  const edit = (s: Strategy) => { setEditId(s.id); setForm({ ...s, variants: s.variants.join('\n====\n') }) }
  const save = () => act(async () => {
    const body = { ...form!, variants: form!.variants.split('\n====\n').map((v) => v.trim()).filter(Boolean) }
    const s = editId ? await api.updateStrategy(editId, body) : await api.createStrategy(body)
    setSelId(s.id); setForm(null); setEditId(null)
  }, 'Strategy saved')

  return (
    <>
      <PageHeader title="Strategy Library" sub="Prompt templates live in templates/strategies/*.json, separate from application code. Built-ins are read-only — duplicate one to customise it. Use {{goal}} and other {{variables}}."
        actions={<>
          <Button variant="primary" onClick={() => { setEditId(null); setForm({ ...blank }) }}>New strategy</Button>
          <Button onClick={async () => download('promptforge-strategies.json', JSON.stringify(await api.exportStrategies(), null, 2))}>Export custom</Button>
          <Button onClick={() => file.current?.click()}>Import</Button>
          <input ref={file} hidden type="file" accept="application/json" aria-label="Import strategies" onChange={async (e) => { const f = e.target.files?.[0]; if (f) act(async () => { await api.importStrategies(JSON.parse(await f.text())) }, 'Imported') }} />
        </>} />
      <ErrorNote error={err ?? list.error} />
      {form && (
        <Card title={editId ? 'Edit strategy' : 'New strategy'} className="mb-5" actions={<Button small onClick={() => setForm(null)}>Cancel</Button>}>
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Category"><Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} /></Field>
            <div className="md:col-span-2"><Field label="Description"><Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field></div>
            <div className="md:col-span-2"><Field label="Prompt template" hint="Variables: {{goal}}, {{context}}, {{b64_goal}}, {{rot13_goal}}, {{reversed_goal}}, {{filler}}. Separate turns with ---TURN---."><Textarea className="mono" rows={4} value={form.template} onChange={(e) => setForm({ ...form, template: e.target.value })} /></Field></div>
            <div className="md:col-span-2"><Field label="Variants (separate with a line containing ====)"><Textarea className="mono" rows={3} value={form.variants} onChange={(e) => setForm({ ...form, variants: e.target.value })} /></Field></div>
            <Field label="Trust boundary"><Input value={form.trust_boundary} onChange={(e) => setForm({ ...form, trust_boundary: e.target.value })} /></Field>
            <Field label="Known limitations"><Input value={form.limitations} onChange={(e) => setForm({ ...form, limitations: e.target.value })} /></Field>
            <div className="md:col-span-2"><Field label="Evaluation criteria"><Input value={form.evaluation_criteria} onChange={(e) => setForm({ ...form, evaluation_criteria: e.target.value })} /></Field></div>
            <div className="flex flex-wrap gap-3 text-sm md:col-span-2"><span className="text-dim">Applies to:</span>
              {TYPES.map((t) => <label key={t}><input type="checkbox" checked={form.challenge_types.includes(t)} onChange={(e) => setForm({ ...form, challenge_types: e.target.checked ? [...form.challenge_types, t] : form.challenge_types.filter((x) => x !== t) })} /> {t.replace(/_/g, ' ')}</label>)}</div>
          </div>
          <Button className="mt-4" variant="primary" disabled={!form.name || !form.template} onClick={save}>Save strategy</Button>
        </Card>
      )}
      <div className="grid gap-5 lg:grid-cols-3">
        <Card title={`${list.data?.length ?? 0} strategies`} className="lg:col-span-1">
          {groups.map(([cat, items]) => (
            <div key={cat} className="mb-3"><div className="mb-1 text-xs font-semibold uppercase text-dim">{cat}</div>
              {items.map((s) => <button key={s.id} onClick={() => setSelId(s.id)} className={`flex w-full justify-between rounded px-2 py-1.5 text-left text-sm ${s.id === selId ? 'bg-accent/15 text-accent' : 'hover:bg-panel2'}`}><span>{s.name}</span>{s.builtin && <span className="text-[10px] text-dim">built-in</span>}</button>)}
            </div>
          ))}
        </Card>
        <div className="lg:col-span-2">
          {!sel ? <Empty>Select a strategy to inspect it.</Empty> : (
            <Card title={sel.name} actions={<>
              <Button small onClick={() => act(async () => { const d = await api.duplicateStrategy(sel.id); setSelId(d.id) }, 'Duplicated')}>Duplicate</Button>
              {!sel.builtin && <><Button small onClick={() => edit(sel)}>Edit</Button><Button small variant="danger" onClick={() => act(async () => { await api.deleteStrategy(sel.id); setSelId(null) }, 'Deleted')}>Delete</Button></>}</>}>
              <p className="mb-3 text-sm text-dim">{sel.description}</p>
              <h3 className="text-xs font-semibold uppercase text-dim">Template</h3>
              <pre className="mb-2 whitespace-pre-wrap rounded bg-bg p-2 text-xs">{sel.template}</pre>
              {sel.variants.map((v, i) => <pre key={i} className="mb-2 whitespace-pre-wrap rounded bg-bg p-2 text-xs"><span className="text-dim">variant {i + 1}: </span>{v}</pre>)}
              <dl className="mt-3 grid gap-3 text-sm md:grid-cols-2">
                <div><dt className="text-xs text-dim">Applicable challenge types</dt><dd>{sel.challenge_types.join(', ') || 'all'}</dd></div>
                <div><dt className="text-xs text-dim">Required inputs</dt><dd>{sel.required_inputs.join(', ') || '—'}</dd></div>
                <div><dt className="text-xs text-dim">Trust boundary</dt><dd>{sel.trust_boundary}</dd></div>
                <div><dt className="text-xs text-dim">Known limitations</dt><dd>{sel.limitations}</dd></div>
                <div className="md:col-span-2"><dt className="text-xs text-dim">Evaluation criteria</dt><dd>{sel.evaluation_criteria}</dd></div>
              </dl>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
