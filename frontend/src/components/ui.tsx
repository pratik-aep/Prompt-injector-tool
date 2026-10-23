import { useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import type { Verdict } from '../types'

export function Card({ title, actions, children, className = '' }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-line bg-panel ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <h2 className="text-[13px] font-semibold uppercase tracking-wide text-dim">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'danger' | 'ok'; small?: boolean }
export function Button({ variant = 'ghost', small, className = '', ...p }: BtnProps) {
  const v = {
    primary: 'bg-accent text-white hover:brightness-110',
    ok: 'bg-ok/90 text-black hover:brightness-110',
    danger: 'bg-bad/15 text-bad border border-bad/40 hover:bg-bad/25',
    ghost: 'border border-line text-ink hover:bg-panel2',
  }[variant]
  return <button {...p} className={`rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${small ? 'px-2 py-1 text-xs' : 'px-3 py-1.5'} ${v} ${className}`} />
}

const VERDICT: Record<string, { label: string; cls: string; hint: string }> = {
  verified_success: { label: 'Verified', cls: 'bg-ok/15 text-ok border-ok/40', hint: 'Confirmed by the evaluator against the configured ground truth' },
  possible_success: { label: 'Possible', cls: 'bg-warn/15 text-warn border-warn/40', hint: 'Evidence present but NOT verified' },
  failed: { label: 'Failed', cls: 'bg-bad/10 text-bad border-bad/30', hint: 'Objective not met' },
  invalid_test: { label: 'Invalid', cls: 'bg-panel2 text-dim border-line', hint: 'Target error or empty response; not a result' },
  evaluation_error: { label: 'Eval error', cls: 'bg-panel2 text-warn border-line', hint: 'The evaluator could not run' },
}
export function VerdictBadge({ verdict, estimate }: { verdict: Verdict | string | null | undefined; estimate?: boolean | null }) {
  if (!verdict) return <span className="text-dim">—</span>
  const v = VERDICT[verdict] ?? { label: verdict, cls: 'border-line text-dim', hint: '' }
  return <span title={v.hint} className={`inline-block rounded border px-1.5 py-0.5 text-xs font-medium ${v.cls}`}>{v.label}{estimate ? ' (estimate)' : ''}</span>
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-panel px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-dim">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-dim">{sub}</div>}
    </div>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-dim">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-dim/80">{hint}</span>}
    </label>
  )
}
const inputCls = 'w-full rounded-md border border-line bg-bg px-2.5 py-1.5 text-sm text-ink placeholder:text-dim/60 focus:border-accent'
export const Input = (p: React.InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={`${inputCls} ${p.className ?? ''}`} />
export const Textarea = (p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={`${inputCls} ${p.className ?? ''}`} />
export const Select = (p: React.SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={`${inputCls} ${p.className ?? ''}`} />

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [done, setDone] = useState(false)
  const copy = async () => {
    try { await navigator.clipboard.writeText(text) } catch {
      const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove()
    }
    setDone(true); setTimeout(() => setDone(false), 1500)
  }
  return <Button small onClick={copy} aria-label={label}>{done ? 'Copied' : label}</Button>
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null
  return <div role="alert" className="rounded-md border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">{error}</div>
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-dashed border-line px-4 py-8 text-center text-sm text-dim">{children}</div>
}
export function Progress({ value, max, label }: { value: number; max: number; label?: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div>
      <div className="h-2 overflow-hidden rounded bg-panel2" role="progressbar" aria-valuenow={value} aria-valuemax={max} aria-label={label}>
        <div className={`h-full ${pct > 90 ? 'bg-bad' : pct > 70 ? 'bg-warn' : 'bg-accent'}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 text-xs text-dim tabular-nums">{value} / {max}</div>
    </div>
  )
}
export function PageHeader({ title, sub, actions }: { title: string; sub?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-xl font-semibold">{title}</h1>{sub && <p className="mt-0.5 max-w-3xl text-sm text-dim">{sub}</p>}</div>
      <div className="flex items-center gap-2">{actions}</div>
    </div>
  )
}
export const fmt = {
  ms: (n: number | null | undefined) => (n == null ? '—' : n >= 1000 ? `${(n / 1000).toFixed(1)}s` : `${Math.round(n)}ms`),
  pct: (n: number) => `${(n * 100).toFixed(n > 0 && n < 0.1 ? 1 : 0)}%`,
  time: (s: string) => { const d = new Date(s); return isNaN(+d) ? s : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) },
}
