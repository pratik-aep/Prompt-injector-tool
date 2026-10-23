import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useApp } from '../hooks/useAppState'
import { Button, Select } from './ui'

export const NAV = [
  { to: '/', label: 'Overview' },
  { to: '/targets', label: 'Targets' },
  { to: '/workspace', label: 'Challenge Workspace' },
  { to: '/studio', label: 'Prompt Studio' },
  { to: '/lab', label: 'Optimization Lab' },
  { to: '/analyzer', label: 'Response Analyzer' },
  { to: '/history', label: 'Experiment History' },
  { to: '/analytics', label: 'Analytics' },
  { to: '/strategies', label: 'Strategies' },
  { to: '/team', label: 'Team & Data' },
]

export default function Layout() {
  const { challenges, challenge, selectChallenge, members, member, selectMember, error, toasts } = useApp()
  const nav = useNavigate()
  const [help, setHelp] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(t?.tagName)
      if (e.altKey && /^[0-9]$/.test(e.key)) {
        const i = e.key === '0' ? 9 : Number(e.key) - 1
        if (NAV[i]) { e.preventDefault(); nav(NAV[i].to) }
      } else if (e.key === '?' && !typing) setHelp((h) => !h)
      else if (e.key === 'Escape') setHelp(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [nav])

  return (
    <div className="flex h-full">
      <aside className="flex w-56 shrink-0 flex-col border-r border-line bg-panel" aria-label="Primary">
        <div className="px-4 py-4"><div className="text-base font-bold tracking-tight">Prompt<span className="text-accent">Forge</span></div><div className="text-xs text-dim">Prompt-injection CTF lab</div></div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2">
          {NAV.map((n, i) => (
            <NavLink key={n.to} to={n.to} end={n.to === '/'} className={({ isActive }) => `flex items-center justify-between rounded-md px-3 py-1.5 text-sm ${isActive ? 'bg-accent/15 text-accent' : 'text-dim hover:bg-panel2 hover:text-ink'}`}>
              <span>{n.label}</span><kbd className="text-[10px] text-dim/60">⌥{(i + 1) % 10}</kbd>
            </NavLink>
          ))}
        </nav>
        <div className="space-y-3 border-t border-line p-3">
          <label className="block text-xs text-dim">Challenge
            <Select aria-label="Active challenge" value={challenge?.id ?? ''} onChange={(e) => selectChallenge(e.target.value)} className="mt-1">
              {challenges.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </label>
          <label className="block text-xs text-dim">Working as
            <Select aria-label="Team member" value={member?.id ?? ''} onChange={(e) => selectMember(e.target.value)} className="mt-1">
              <option value="">(unassigned)</option>
              {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </Select>
          </label>
          <Button small className="w-full" onClick={() => setHelp(true)}>Keyboard shortcuts ?</Button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-7xl p-6">
          {error && <div role="alert" className="mb-4 rounded-md border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">{error}</div>}
          <Outlet />
        </div>
      </main>
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 space-y-2" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={`pointer-events-auto rounded-md border px-3 py-2 text-sm shadow-lg ${t.kind === 'ok' ? 'border-ok/40 bg-panel text-ok' : 'border-bad/40 bg-panel text-bad'}`}>{t.msg}</div>)}
      </div>
      {help && (
        <div role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setHelp(false)}>
          <div className="w-96 rounded-lg border border-line bg-panel p-5" onClick={(e) => e.stopPropagation()}>
            <h2 className="mb-3 font-semibold">Keyboard shortcuts</h2>
            <ul className="space-y-1.5 text-sm">
              <li><kbd>⌥1</kbd>–<kbd>⌥0</kbd> Jump between pages</li>
              <li><kbd>⌘/Ctrl</kbd>+<kbd>Enter</kbd> Run test (Prompt Studio editor)</li>
              <li><kbd>?</kbd> Toggle this help</li>
              <li><kbd>Esc</kbd> Close dialogs</li>
            </ul>
            <Button small className="mt-4" onClick={() => setHelp(false)}>Close</Button>
          </div>
        </div>
      )}
    </div>
  )
}
