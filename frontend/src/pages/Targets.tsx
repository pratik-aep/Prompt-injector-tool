import { useState } from 'react'
import { Button, Card, CopyButton, Empty, ErrorNote, Field, Input, PageHeader, Select } from '../components/ui'
import { useApp } from '../hooks/useAppState'
import { useAsync } from '../hooks/useAsync'
import { api } from '../services/api'

const gb = (n?: number) => (n ? `${(n / 1e9).toFixed(1)} GB` : '—')

export default function Targets() {
  const { targets, refresh, toast } = useApp()
  const ol = useAsync(() => api.ollama(), [])
  const [checks, setChecks] = useState<Record<string, { ok: boolean; detail: string }>>({})
  const [err, setErr] = useState<string | null>(null)
  const [kind, setKind] = useState('http_api')
  const [f, setF] = useState({ name: '', model: '', url: '', method: 'POST', auth: 'bearer', secret_ref: '', response_path: 'choices.0.message.content',
    body_template: '{"messages": "{{messages}}"}', headers: '{}', timeout_s: '30', rate: '20', retries: '1', allow_private: false })
  const set = (k: string, v: string | boolean) => setF((x) => ({ ...x, [k]: v }))

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setErr(null)
    try { await fn(); toast(ok); await refresh() } catch (e) { const m = e instanceof Error ? e.message : String(e); setErr(m); toast(m, 'err') }
  }
  const useModel = (model: string) => run(() => api.addTarget({ name: `Ollama · ${model}`, kind: 'ollama', config: { model, max_tokens: 400, temperature: 0.7, think: false } }), `Registered ${model}`)

  const addTarget = () => run(async () => {
    let config: Record<string, unknown>
    if (kind === 'http_api') {
      config = { url: f.url, method: f.method, auth: { type: f.auth }, response_path: f.response_path, timeout_s: Number(f.timeout_s),
        rate_limit_per_min: Number(f.rate), retries: Number(f.retries), body_template: JSON.parse(f.body_template), headers: JSON.parse(f.headers) }
    } else config = { model: f.model }
    await api.addTarget({ name: f.name, kind, config, secret_ref: f.secret_ref || null, allow_private: f.allow_private })
  }, 'Target registered')

  const o = ol.data
  return (
    <>
      <PageHeader title="Target Configuration" sub="Targets must be registered and enabled before any request is sent. Remote endpoints are validated against SSRF rules and never scanned or discovered." />
      <ErrorNote error={err} />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Local Ollama" actions={<Button small onClick={() => ol.reload()}>Re-detect</Button>}>
          <ul className="mb-3 space-y-1 text-sm">
            <li>Installed: <b className={o?.installed ? 'text-ok' : 'text-warn'}>{o ? (o.installed ? 'yes' : 'no') : '…'}</b></li>
            <li>Server ({o?.url ?? '127.0.0.1:11434'}): <b className={o?.server_up ? 'text-ok' : 'text-warn'}>{o ? (o.server_up ? 'running' : 'not reachable') : '…'}</b></li>
          </ul>
          {o && !o.server_up && <p className="mb-3 text-sm text-dim">Start it with <code className="mono">ollama serve</code> (or open the Ollama app).</p>}
          {o?.server_up && o.models.length === 0 && (
            <Empty>No models installed. A small, 16 GB-friendly option (about 2 GB):
              <div className="mt-2 flex items-center justify-center gap-2"><code className="mono">ollama pull llama3.2:3b</code><CopyButton text="ollama pull llama3.2:3b" /></div>
              <div className="mt-1 text-xs">PromptForge never downloads models for you.</div></Empty>
          )}
          {o?.models.map((m) => {
            const registered = targets.some((t) => t.kind === 'ollama' && t.config.model === m.name)
            return (
              <div key={m.name} className="flex items-center justify-between border-t border-line py-2 text-sm">
                <div><div className="font-medium">{m.name}</div><div className="text-xs text-dim">{[m.parameter_size, m.quantization, m.family, gb(m.size_bytes)].filter(Boolean).join(' · ')}</div></div>
                <Button small variant="primary" disabled={registered} onClick={() => useModel(m.name)}>{registered ? 'Registered' : 'Use this model'}</Button>
              </div>
            )
          })}
          {o && (o.models.some((m) => (m.size_bytes ?? 0) > 8e9)) && <p className="mt-2 text-xs text-warn">Models above ~8 GB may be slow or crowd memory on a 16 GB Mac. Concurrency is limited to 1 by default.</p>}
        </Card>

        <Card title="Register a target">
          <div className="space-y-3">
            <Field label="Type">
              <Select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Target type">
                <option value="http_api">Authorized CTF API (HTTP)</option><option value="ollama">Ollama model (manual name)</option>
                <option value="openai">OpenAI (optional)</option><option value="anthropic">Anthropic (optional)</option>
              </Select>
            </Field>
            <Field label="Name"><Input value={f.name} onChange={(e) => set('name', e.target.value)} placeholder="e.g. Competition bot – round 1" /></Field>
            {kind === 'http_api' ? (
              <>
                <div className="grid grid-cols-3 gap-2">
                  <div className="col-span-2"><Field label="Endpoint URL"><Input value={f.url} onChange={(e) => set('url', e.target.value)} placeholder="https://ctf.example.edu/api/chat" /></Field></div>
                  <Field label="Method"><Select value={f.method} onChange={(e) => set('method', e.target.value)}><option>POST</option><option>GET</option><option>PUT</option><option>PATCH</option></Select></Field>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Authorization"><Select value={f.auth} onChange={(e) => set('auth', e.target.value)}><option value="bearer">Bearer token</option><option value="header">Custom header</option><option value="none">None</option></Select></Field>
                  <Field label="Credential reference" hint="env:NAME or keychain:SERVICE — never the key itself"><Input value={f.secret_ref} onChange={(e) => set('secret_ref', e.target.value)} placeholder="env:CTF_TOKEN" /></Field>
                </div>
                <Field label="Request body template (JSON)" hint="{{prompt}} = last user message, {{messages}} = full history"><Input className="mono" value={f.body_template} onChange={(e) => set('body_template', e.target.value)} /></Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Response path"><Input className="mono" value={f.response_path} onChange={(e) => set('response_path', e.target.value)} /></Field>
                  <Field label="Extra headers (JSON)"><Input className="mono" value={f.headers} onChange={(e) => set('headers', e.target.value)} /></Field>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <Field label="Timeout (s)"><Input type="number" value={f.timeout_s} onChange={(e) => set('timeout_s', e.target.value)} /></Field>
                  <Field label="Rate limit / min"><Input type="number" value={f.rate} onChange={(e) => set('rate', e.target.value)} /></Field>
                  <Field label="Retries"><Input type="number" value={f.retries} onChange={(e) => set('retries', e.target.value)} /></Field>
                </div>
                <label className="flex items-center gap-2 text-sm text-dim"><input type="checkbox" checked={f.allow_private} onChange={(e) => set('allow_private', e.target.checked)} /> Endpoint is a local/LAN competition server I am authorised to test (allows private addresses)</label>
              </>
            ) : (
              <>
                <Field label="Model"><Input value={f.model} onChange={(e) => set('model', e.target.value)} placeholder={kind === 'ollama' ? 'llama3.2:3b' : 'model id'} /></Field>
                {kind !== 'ollama' && <Field label="Credential reference" hint={`Defaults to env:${kind === 'openai' ? 'OPENAI_API_KEY' : 'ANTHROPIC_API_KEY'}`}><Input value={f.secret_ref} onChange={(e) => set('secret_ref', e.target.value)} /></Field>}
              </>
            )}
            <Button variant="primary" onClick={addTarget} disabled={!f.name}>Register target</Button>
          </div>
        </Card>
      </div>

      <Card title="Registered targets" className="mt-5">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-dim"><tr><th className="pb-2">Name</th><th>Kind</th><th>Detail</th><th>Status</th><th /></tr></thead>
          <tbody>
            {targets.map((t) => (
              <tr key={t.id} className="border-t border-line">
                <td className="py-2 pr-3">{t.name}</td><td className="pr-3 text-dim">{t.kind}</td>
                <td className="pr-3 text-xs text-dim">{t.config.model ?? t.config.url ?? '—'}{t.secret_ref ? ` · ${t.secret_ref}${t.credential_available === false ? ' (not set)' : ''}` : ''}</td>
                <td className="pr-3 text-xs">{checks[t.id] ? <span className={checks[t.id].ok ? 'text-ok' : 'text-warn'}>{checks[t.id].detail}</span> : <span className="text-dim">—</span>}</td>
                <td className="space-x-2 whitespace-nowrap text-right">
                  <Button small onClick={() => run(async () => { const r = await api.checkTarget(t.id); setChecks((c) => ({ ...c, [t.id]: r })) }, 'Checked')}>Test connection</Button>
                  <Button small onClick={() => run(() => api.updateTarget(t.id, { enabled: !t.enabled }), t.enabled ? 'Disabled' : 'Enabled')}>{t.enabled ? 'Disable' : 'Enable'}</Button>
                  {!['t_simulated', 't_manual'].includes(t.id) && <Button small variant="danger" onClick={() => run(() => api.deleteTarget(t.id), 'Removed')}>Remove</Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs text-dim">“Local simulator” is a deterministic rule-based defender for practice and tests — it is not a language model.</p>
      </Card>
    </>
  )
}
