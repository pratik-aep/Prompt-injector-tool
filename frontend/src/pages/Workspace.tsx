import { useState } from 'react'
import { Button, Card, Empty, ErrorNote, Field, Input, PageHeader, Progress, Select, Textarea, VerdictBadge } from '../components/ui'
import { useApp } from '../hooks/useAppState'
import { useAsync } from '../hooks/useAsync'
import { api } from '../services/api'

const TYPES = ['secret_extraction', 'instruction_hierarchy', 'format_enforcement', 'indirect_injection', 'tool_output_trust']

export default function Workspace() {
  const { challenges, challenge, selectChallenge, targets, refresh, toast } = useApp()
  const [showNew, setShowNew] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [n, setN] = useState({ name: '', type: 'secret_extraction', difficulty: 'easy', objective: '', surface: 'Single user message', budget: '50', maxLen: '2000', api: true, manual: true, flag: '', defender: '' })
  const dups = useAsync(() => (challenge ? api.duplicates(challenge.id) : Promise.resolve([])), [challenge?.id, challenge?.attempts_used])

  const create = async () => {
    setErr(null)
    const methods = [n.api && 'api', n.manual && 'manual'].filter(Boolean)
    const body: Record<string, unknown> = {
      name: n.name, type: n.type, difficulty: n.difficulty, objective: n.objective, allowed_surface: n.surface,
      query_budget: Number(n.budget), max_prompt_length: Number(n.maxLen), allowed_methods: methods,
    }
    if (n.flag) body.evaluator_config = { checks: [{ kind: 'exact_flag', flag: n.flag }] }
    if (n.defender) body.defender = { system_prompt: n.defender.replace('{{flag}}', n.flag), user_template: '{{attack}}' }
    try {
      const c = await api.createChallenge(body)
      await refresh(); selectChallenge(c.id); setShowNew(false); toast(`Created ${c.name}`)
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
  }
  const setTarget = async (tid: string) => {
    if (!challenge) return
    try { await api.updateChallenge(challenge.id, { target_id: tid || null }); await refresh(); toast('Target updated') } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
  }
  const setStatus = async (status: string) => { if (challenge) { await api.updateChallenge(challenge.id, { status }); await refresh() } }

  return (
    <>
      <PageHeader title="Challenge Workspace" sub="Scope, scoring criteria and restrictions for the selected challenge. Expected flags and defender prompts are never shown here."
        actions={<Button variant="primary" onClick={() => setShowNew((s) => !s)}>{showNew ? 'Close form' : 'New challenge'}</Button>} />
      <ErrorNote error={err} />
      {showNew && (
        <Card title="Create challenge" className="mb-5">
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Name"><Input value={n.name} onChange={(e) => setN({ ...n, name: e.target.value })} /></Field>
            <Field label="Type"><Select value={n.type} onChange={(e) => setN({ ...n, type: e.target.value })}>{TYPES.map((t) => <option key={t}>{t}</option>)}</Select></Field>
            <Field label="Difficulty"><Select value={n.difficulty} onChange={(e) => setN({ ...n, difficulty: e.target.value })}><option>easy</option><option>medium</option><option>hard</option></Select></Field>
            <div className="md:col-span-3"><Field label="Objective (shown to attackers)"><Textarea rows={2} value={n.objective} onChange={(e) => setN({ ...n, objective: e.target.value })} /></Field></div>
            <Field label="Allowed attack surface"><Input value={n.surface} onChange={(e) => setN({ ...n, surface: e.target.value })} /></Field>
            <Field label="Query budget"><Input type="number" value={n.budget} onChange={(e) => setN({ ...n, budget: e.target.value })} /></Field>
            <Field label="Max prompt length"><Input type="number" value={n.maxLen} onChange={(e) => setN({ ...n, maxLen: e.target.value })} /></Field>
            <Field label="Expected flag (optional)" hint="Leave empty for an external competition challenge: flag-shaped output then stays unverified until you confirm it."><Input className="mono" value={n.flag} onChange={(e) => setN({ ...n, flag: e.target.value })} placeholder="CTF{practice_example_01}" /></Field>
            <div className="md:col-span-2"><Field label="Defender system prompt (optional, local testing)" hint="Use {{flag}} to embed the expected flag. Stored server-side and never returned by the API."><Textarea rows={2} value={n.defender} onChange={(e) => setN({ ...n, defender: e.target.value })} /></Field></div>
            <div className="flex items-center gap-4 text-sm md:col-span-3">
              <span className="text-dim">Allowed methods:</span>
              <label><input type="checkbox" checked={n.api} onChange={(e) => setN({ ...n, api: e.target.checked })} /> API</label>
              <label><input type="checkbox" checked={n.manual} onChange={(e) => setN({ ...n, manual: e.target.checked })} /> Manual</label>
            </div>
          </div>
          <Button className="mt-4" variant="primary" disabled={!n.name || !n.objective} onClick={create}>Create challenge</Button>
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="Challenges" className="lg:col-span-1">
          <ul className="space-y-1">
            {challenges.map((c) => (
              <li key={c.id}>
                <button onClick={() => selectChallenge(c.id)} className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm ${c.id === challenge?.id ? 'bg-accent/15 text-accent' : 'hover:bg-panel2'}`}>
                  <span className="truncate pr-2">{c.name}</span>
                  <span className="shrink-0 text-xs text-dim">{c.status === 'solved' ? '✔ solved' : c.difficulty}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        {challenge ? (
          <div className="space-y-5 lg:col-span-2">
            <Card title={challenge.name} actions={<span className="text-xs text-dim">{challenge.id}</span>}>
              <p className="mb-3 text-sm text-dim">{challenge.description}</p>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm md:grid-cols-3">
                <div><dt className="text-xs text-dim">Type</dt><dd>{challenge.type.replace(/_/g, ' ')}</dd></div>
                <div><dt className="text-xs text-dim">Difficulty</dt><dd>{challenge.difficulty}</dd></div>
                <div><dt className="text-xs text-dim">Status</dt><dd>
                  <Select aria-label="Status" value={challenge.status} onChange={(e) => setStatus(e.target.value)}><option>active</option><option>solved</option><option>archived</option></Select></dd></div>
                <div className="col-span-2 md:col-span-3"><dt className="text-xs text-dim">Objective</dt><dd>{challenge.objective}</dd></div>
                <div className="col-span-2 md:col-span-3"><dt className="text-xs text-dim">Allowed attack surface</dt><dd>{challenge.allowed_surface || '—'}</dd></div>
                <div className="col-span-2 md:col-span-3"><dt className="text-xs text-dim">Scoring criteria</dt><dd>{challenge.scoring?.success ?? (challenge.has_local_evaluator ? 'Locally evaluated' : 'External: flag-shaped output is unverified until confirmed with the competition verifier.')}</dd></div>
              </dl>
            </Card>
            <div className="grid gap-5 md:grid-cols-2">
              <Card title="Restrictions">
                <div className="mb-3"><div className="mb-1 text-xs text-dim">Query budget</div><Progress value={challenge.attempts_used} max={challenge.query_budget} label="Query budget" /></div>
                <ul className="space-y-1 text-sm">
                  <li>Max prompt length: <b>{challenge.max_prompt_length}</b> chars</li>
                  <li>Allowed methods: <b>{challenge.allowed_methods.join(', ')}</b></li>
                  <li>Local evaluator: <b>{challenge.has_local_evaluator ? 'yes' : 'no (external)'}</b></li>
                </ul>
                <div className="mt-3"><Field label="Target"><Select aria-label="Challenge target" value={challenge.target_id ?? ''} onChange={(e) => setTarget(e.target.value)}>
                  <option value="">(default: local simulator)</option>{targets.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field></div>
              </Card>
              <Card title="Verified flags">
                {challenge.verified_flags.length === 0 ? <Empty>None yet.</Empty> : (
                  <ul className="space-y-2">{challenge.verified_flags.map((f) => (
                    <li key={f.flag} className="rounded border border-ok/30 bg-ok/5 p-2 text-sm"><code className="mono text-ok">{f.flag}</code>
                      <div className="text-xs text-dim">{f.source === 'competition_verifier' ? 'confirmed by competition verifier' : 'verified by evaluator'} · {new Date(f.created_at).toLocaleString()}</div></li>))}</ul>
                )}
                <h3 className="mt-4 text-xs font-semibold uppercase text-dim">Duplicate attempts</h3>
                {dups.data && dups.data.length > 0
                  ? <p className="mt-1 text-sm text-warn">{dups.data.length} prompt(s) were tested more than once ({dups.data.reduce((a, d) => a + d.count - 1, 0)} wasted queries).</p>
                  : <p className="mt-1 text-sm text-dim">No duplicate prompts tested.</p>}
              </Card>
            </div>
          </div>
        ) : <Empty>No challenge selected.</Empty>}
      </div>
    </>
  )
}
