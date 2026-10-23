import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../services/api'
import type { Challenge, Member, Target } from '../types'

interface AppState {
  challenges: Challenge[]; targets: Target[]; members: Member[]
  challenge: Challenge | null; target: Target | null; member: Member | null
  selectChallenge: (id: string) => void; selectTarget: (id: string) => void; selectMember: (id: string) => void
  refresh: () => Promise<void>; error: string | null
  toast: (msg: string, kind?: 'ok' | 'err') => void; toasts: { id: number; msg: string; kind: 'ok' | 'err' }[]
}

const Ctx = createContext<AppState | null>(null)
const get = (k: string) => { try { return localStorage.getItem(k) } catch { return null } }
const set = (k: string, v: string) => { try { localStorage.setItem(k, v) } catch { /* private mode */ } }

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [challenges, setChallenges] = useState<Challenge[]>([])
  const [targets, setTargets] = useState<Target[]>([])
  const [members, setMembers] = useState<Member[]>([])
  const [cid, setCid] = useState<string | null>(get('pf.challenge'))
  const [tid, setTid] = useState<string | null>(get('pf.target'))
  const [mid, setMid] = useState<string | null>(get('pf.member'))
  const [error, setError] = useState<string | null>(null)
  const [toasts, setToasts] = useState<AppState['toasts']>([])

  const refresh = useCallback(async () => {
    try {
      const [c, t, m] = await Promise.all([api.challenges(), api.targets(), api.members()])
      setChallenges(c); setTargets(t); setMembers(m); setError(null)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const toast = useCallback((msg: string, kind: 'ok' | 'err' = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts((x) => [...x, { id, msg, kind }])
    setTimeout(() => setToasts((x) => x.filter((y) => y.id !== id)), 4500)
  }, [])

  const value = useMemo<AppState>(() => {
    const challenge = challenges.find((c) => c.id === cid) ?? challenges[0] ?? null
    const target = targets.find((t) => t.id === tid) ?? targets.find((t) => t.id === challenge?.target_id) ?? targets.find((t) => t.kind === 'simulated') ?? targets[0] ?? null
    const member = members.find((m) => m.id === mid) ?? null
    return {
      challenges, targets, members, challenge, target, member, error, refresh, toast, toasts,
      selectChallenge: (id) => { setCid(id); set('pf.challenge', id) },
      selectTarget: (id) => { setTid(id); set('pf.target', id) },
      selectMember: (id) => { setMid(id); set('pf.member', id) },
    }
  }, [challenges, targets, members, cid, tid, mid, error, refresh, toast, toasts])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useApp() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useApp must be used inside AppStateProvider')
  return v
}
