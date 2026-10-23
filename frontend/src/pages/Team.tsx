import { useState } from 'react'
import { Button, Card, ErrorNote, Field, Input, PageHeader } from '../components/ui'
import { useApp } from '../hooks/useAppState'
import { api } from '../services/api'

export default function Team() {
  const { members, member, selectMember, refresh, toast } = useApp()
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setErr(null)
    try { await fn(); await refresh(); toast(ok) } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
  }
  return (
    <>
      <PageHeader title="Team & Data" sub="Three-member workflow on one Mac. Pick who you are in the sidebar; new experiments and candidates are attributed to that person." />
      <ErrorNote error={err} />
      <div className="grid gap-5 md:grid-cols-2">
        <Card title="Members">
          <ul className="mb-4 divide-y divide-line">
            {members.map((m) => (
              <li key={m.id} className="flex items-center justify-between py-2 text-sm">
                <div><b>{m.name}</b> <span className="text-dim">{m.role}</span>{member?.id === m.id && <span className="ml-2 text-xs text-accent">you</span>}</div>
                <span className="space-x-2"><Button small onClick={() => selectMember(m.id)}>I am {m.name}</Button><Button small variant="danger" onClick={() => act(() => api.deleteMember(m.id), 'Removed')}>Remove</Button></span>
              </li>
            ))}
            {members.length === 0 && <li className="py-2 text-sm text-dim">No members yet.</li>}
          </ul>
          <div className="grid grid-cols-2 gap-2"><Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field><Field label="Responsibility"><Input value={role} onChange={(e) => setRole(e.target.value)} placeholder="e.g. encoding attacks" /></Field></div>
          <Button className="mt-3" variant="primary" disabled={!name.trim()} onClick={() => act(async () => { await api.addMember(name.trim(), role); setName(''); setRole('') }, 'Member added')}>Add member</Button>
        </Card>
        <Card title="Data">
          <p className="mb-3 text-sm text-dim">Share results with teammates via the JSON export on the History page; importing merges new experiments and skips ones you already have. Credentials are never stored in the database or exports.</p>
          <Button onClick={() => act(async () => { const r = await api.backup(); toast(`Backup saved: ${r.path}`) }, 'Backup created')}>Back up database now</Button>
        </Card>
      </div>
    </>
  )
}
