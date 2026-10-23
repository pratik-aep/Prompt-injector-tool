import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, CopyButton, Empty, ErrorNote, Field, Input, PageHeader, Select, Textarea, VerdictBadge, fmt } from '../components/ui'
import { useApp } from '../hooks/useAppState'
import { useAsync } from '../hooks/useAsync'
import { api } from '../services/api'
import type { AttemptResult, Candidate } from '../types'

const MODES = [['template', 'Template'], ['ai', 'AI-assisted (local LLM)'], ['hybrid', 'Hybrid'], ['manual', 'Manual only']] as const

export default function PromptStudio() {
  const { challenge, target, targets, selectTarget, member, refresh, toast } = useApp()
  const strategies = useAsync(() => api.strategies(challenge?.type), [challenge?.type])
  const [mode, setMode] = useState<string>('template')
  const [picked, setPicked] = useState<string[]>([])
  const [count, setCount] = useState(6)
  const [constraints, setConstraints] = useState('')
  const [llmId, setLlmId] = useState('')
  const [cands, setCands] = useState<Candidate[]>([])
  const [warnings, setWarnings] = useState<string[]>([])
  const [text, setText] = useState('')
  const [loaded, setLoaded] = useState<Candidate | null>(null)
  const [trials, setTrials] = useState(1)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<AttemptResult | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [pasted, setPasted] = useState('')
  const [cmp, setCmp] = useState<string[]>([])
  const [savedOnly, setSavedOnly] = useState(false)

  // Candidate list is restored from the database when the challenge changes.
  useEffect(() => {
    if (!challenge) return
    api.candidates(challenge.id).then((c) => setCands(c.filter((x) => !x.run_id))).catch((e) => setErr(String(e.message ?? e)))
    setResult(null); setLoaded(null)
  }, [challenge?.id])

  const limit = challenge?.max_prompt_length ?? 2000
  const over = text.length > limit
  const turns = text.split('---TURN---').filter((t) => t.trim()).length
  const llmTargets = targets.filter((t) => ['ollama', 'openai', 'anthropic'].includes(t.kind) && t.enabled)
  const canApi = !!challenge?.allowed_methods.includes('api') && target?.kind !== 'manual'
  const canManual = !!challenge?.allowed_methods.includes('manual')
  const visible = useMemo(() => cands.filter((c) => !savedOnly || c.saved), [cands, savedOnly])

  const load = (c: Candidate) => { setText(c.text); setLoaded(c); setResult(null) }
  const guard = async (fn: () => Promise<void>) => {
    setErr(null); setBusy(true)
    try { await fn() } catch (e) { const m = e instanceof Error ? e.message : String(e); setErr(m); toast(m, 'err') } finally { setBusy(false) }
  }

  const generate = () => guard(async () => {
    if (!challenge) return
    const res = await api.generate({ challenge_id: challenge.id, mode, strategy_ids: picked.length ? picked : undefined, count, constraints,
      manual_text: mode === 'manual' ? text : undefined, llm_target_id: llmId || undefined, owner_id: member?.id })
    setWarnings(res.warnings)
    setCands((old) => [...res.candidates, ...old.filter((o) => !res.candidates.some((n) => n.id === o.id))])
    if (res.candidates[0] && mode !== 'manual') load(res.candidates[0])
    toast(`${res.candidates.length} candidate(s) generated`)
  })

  const run = () => guard(async () => {
    if (!challenge || !text.trim()) return
    const same = loaded && loaded.text === text
    const r = await api.runTest({ challenge_id: challenge.id, prompt: text, target_id: target?.id, owner_id: member?.id, trials,
      candidate_id: same ? loaded!.id : undefined, strategy_id: same ? loaded!.strategy_id : undefined })
    setResult(r); await refresh()
  })

  const submitManual = () => guard(async () => {
    if (!challenge) return
    const same = loaded && loaded.text === text
    const r = await api.submitManual({ challenge_id: challenge.id, prompt: text, response: pasted, owner_id: member?.id,
      candidate_id: same ? loaded!.id : undefined, strategy_id: same ? loaded!.strategy_id : undefined })
    setResult(r); setPasted(''); await refresh(); toast('Manual result recorded')
  })

  const toggleSave = async (c: Candidate) => {
    const u = await api.updateCandidate(c.id, { saved: !c.saved })
    setCands((x) => x.map((y) => (y.id === c.id ? u : y)))
  }

  if (!challenge) return <Empty>Select or create a challenge first.</Empty>
  const a = cands.find((c) => c.id === cmp[0]), b = cands.find((c) => c.id === cmp[1])

  return (
    <>
      <PageHeader title="Prompt Studio" sub={`${challenge.name} — build, compare and test candidate prompts. Use a line containing ---TURN--- to split a multi-turn attempt.`}
        actions={<><span className="text-xs text-dim">Target</span><Select aria-label="Test target" className="w-56" value={target?.id ?? ''} onChange={(e) => selectTarget(e.target.value)}>
          {targets.map((t) => <option key={t.id} value={t.id}>{t.name}{t.enabled ? '' : ' (disabled)'}</option>)}</Select></>} />
      <ErrorNote error={err} />
      <div className="grid gap-5 xl:grid-cols-12">
        <div className="space-y-5 xl:col-span-3">
          <Card title="Generate variants">
            <div className="space-y-3">
              <Field label="Mode"><Select aria-label="Generation mode" value={mode} onChange={(e) => setMode(e.target.value)}>{MODES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
              {(mode === 'ai' || mode === 'hybrid') && (
                <Field label="LLM target" hint="Only the public challenge description is sent to it."><Select value={llmId} onChange={(e) => setLlmId(e.target.value)}>
                  <option value="">(none)</option>{llmTargets.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field>
              )}
              <Field label="Strategies" hint="None selected = all applicable">
                <div className="max-h-44 space-y-1 overflow-y-auto rounded-md border border-line p-2">
                  {strategies.data?.map((s) => (
                    <label key={s.id} className="flex items-start gap-2 text-xs"><input type="checkbox" checked={picked.includes(s.id)} onChange={(e) => setPicked(e.target.checked ? [...picked, s.id] : picked.filter((x) => x !== s.id))} /><span title={s.description}>{s.name}</span></label>
                  ))}
                </div>
              </Field>
              <Field label="Count"><Input type="number" min={1} max={30} value={count} onChange={(e) => setCount(Number(e.target.value))} /></Field>
              <Field label="Your constraints (optional)"><Input value={constraints} onChange={(e) => setConstraints(e.target.value)} placeholder="e.g. under 300 characters" /></Field>
              <Button variant="primary" className="w-full" disabled={busy || (mode === 'manual' && !text.trim())} onClick={generate}>{mode === 'manual' ? 'Save my prompt as candidate' : 'Generate variants'}</Button>
              {warnings.map((w) => <p key={w} className="text-xs text-warn">{w}</p>)}
            </div>
          </Card>
        </div>

        <div className="space-y-5 xl:col-span-5">
          <Card title="Prompt editor" actions={<><span className={`text-xs tabular-nums ${over ? 'text-bad' : 'text-dim'}`}>{text.length}/{limit} chars · ≈{Math.ceil(text.length / 4)} tokens{turns > 1 ? ` · ${turns} turns` : ''}</span><CopyButton text={text} label="Copy prompt" /></>}>
            <Textarea className="mono" rows={11} value={text} aria-label="Prompt editor" placeholder="Write a prompt, or pick a candidate…" onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); if (canApi && !over && !busy) run() } }} />
            {loaded && <p className="mt-1 text-xs text-dim">From {loaded.method}{loaded.strategy_id ? ` · ${loaded.strategy_id}` : ''}{loaded.text !== text ? ' · edited (will be recorded as a custom prompt)' : ''}</p>}
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Button variant="ok" disabled={busy || !text.trim() || over || !canApi} onClick={run} title={canApi ? 'Cmd/Ctrl+Enter' : 'Target is manual or API testing is not allowed'}>Run authorized test</Button>
              <label className="flex items-center gap-1.5 text-xs text-dim">Trials <Input type="number" min={1} max={10} className="w-16" value={trials} onChange={(e) => setTrials(Math.max(1, Number(e.target.value)))} /></label>
              <span className="text-xs text-dim">Uses {trials * Math.max(1, turns)} of {challenge.attempts_remaining} remaining queries · target: {target?.name}</span>
            </div>
          </Card>

          {canManual && (
            <Card title="Manual relay (competition chatbot)">
              <p className="mb-2 text-xs text-dim">1) Copy the prompt, 2) submit it yourself on the competition site, 3) paste the reply here. PromptForge never automates third-party sites.</p>
              <Textarea className="mono" rows={5} value={pasted} onChange={(e) => setPasted(e.target.value)} aria-label="Pasted response" placeholder="Paste the chatbot's response…" />
              <Button className="mt-2" variant="primary" disabled={busy || !text.trim() || !pasted.trim() || over} onClick={submitManual}>Evaluate pasted response</Button>
            </Card>
          )}

          {result && (
            <Card title="Result" actions={<Link className="text-xs text-accent" to={`/analyzer?id=${result.experiment_id}`}>Open in analyzer →</Link>}>
              <div className="mb-2 flex flex-wrap items-center gap-2"><VerdictBadge verdict={result.verdict} estimate={result.is_estimate} /><span className="text-xs text-dim">score {result.score.toFixed(2)} · {fmt.ms(result.latency_ms)}{result.trials && result.trials > 1 ? ` · ${Math.round((result.success_rate ?? 0) * 100)}% of ${result.trials} trials succeeded` : ''}</span>
                {result.duplicate_of && <span className="text-xs text-warn">duplicate of an earlier attempt</span>}</div>
              {result.error && <ErrorNote error={result.error} />}
              <ul className="mb-2 list-disc pl-5 text-sm text-dim">{result.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              <pre className="whitespace-pre-wrap break-words rounded bg-bg p-2 text-xs" aria-label="Model response">{result.response_text || '(empty)'}</pre>
            </Card>
          )}
        </div>

        <div className="xl:col-span-4">
          <Card title={`Candidates (${visible.length})`} actions={<><label className="text-xs text-dim"><input type="checkbox" checked={savedOnly} onChange={(e) => setSavedOnly(e.target.checked)} /> saved</label></>}>
            {visible.length === 0 ? <Empty>No candidates yet. Generate some or write your own.</Empty> : (
              <ul className="max-h-[34rem] space-y-2 overflow-y-auto pr-1">
                {visible.map((c) => (
                  <li key={c.id} className={`rounded-md border p-2 text-sm ${loaded?.id === c.id ? 'border-accent bg-accent/5' : 'border-line'}`}>
                    <div className="mb-1 flex items-center justify-between text-xs text-dim"><span>{c.strategy_id ?? c.method} · {c.method}</span><span>≈{c.token_estimate} tok</span></div>
                    <p className="line-clamp-3 whitespace-pre-wrap text-xs">{c.text}</p>
                    <div className="mt-2 flex items-center gap-1.5">
                      <Button small onClick={() => load(c)}>Edit / use</Button>
                      <Button small onClick={() => toggleSave(c)}>{c.saved ? '★ Saved' : '☆ Save'}</Button>
                      <label className="ml-auto text-xs text-dim"><input type="checkbox" checked={cmp.includes(c.id)} onChange={(e) => setCmp(e.target.checked ? [...cmp, c.id].slice(-2) : cmp.filter((x) => x !== c.id))} /> compare</label>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {a && b && (
        <Card title="Candidate comparison" className="mt-5">
          <div className="grid gap-4 md:grid-cols-2">
            {[a, b].map((c) => (
              <div key={c.id}><div className="mb-1 text-xs text-dim">{c.strategy_id ?? c.method} · {c.text.length} chars · ≈{c.token_estimate} tokens</div>
                <pre className="whitespace-pre-wrap rounded bg-bg p-2 text-xs">{c.text}</pre></div>
            ))}
          </div>
        </Card>
      )}
    </>
  )
}
