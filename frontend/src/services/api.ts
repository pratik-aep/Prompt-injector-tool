import type { Analytics, AttemptResult, Candidate, Challenge, Experiment, Member, OllamaStatus, Overview, Paged, Run, Strategy, Target } from '../types'

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the PromptForge backend. Is it running on 127.0.0.1:8000?')
  }
  if (!res.ok) {
    let detail = res.statusText
    try { const j = await res.json(); detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  const ct = res.headers.get('content-type') || ''
  return (ct.includes('json') ? res.json() : res.text()) as Promise<T>
}

const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams()
  Object.entries(o).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') p.set(k, String(v)) })
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  health: () => req<{ status: string; bind_host: string; lan_enabled: boolean; ollama_binary: boolean }>('GET', '/health'),
  ollama: () => req<OllamaStatus>('GET', '/ollama'),
  overview: () => req<Overview>('GET', '/analytics/overview'),
  analytics: () => req<Analytics>('GET', '/analytics'),
  members: () => req<Member[]>('GET', '/members'),
  addMember: (name: string, role: string) => req<Member>('POST', '/members', { name, role }),
  deleteMember: (id: string) => req<void>('DELETE', `/members/${id}`),
  targets: () => req<Target[]>('GET', '/targets'),
  addTarget: (t: Record<string, unknown>) => req<Target>('POST', '/targets', t),
  updateTarget: (id: string, t: Record<string, unknown>) => req<Target>('PATCH', `/targets/${id}`, t),
  deleteTarget: (id: string) => req<void>('DELETE', `/targets/${id}`),
  checkTarget: (id: string) => req<{ ok: boolean; detail: string }>('POST', `/targets/${id}/check`),
  challenges: () => req<Challenge[]>('GET', '/challenges'),
  createChallenge: (c: Record<string, unknown>) => req<Challenge>('POST', '/challenges', c),
  updateChallenge: (id: string, c: Record<string, unknown>) => req<Challenge>('PATCH', `/challenges/${id}`, c),
  duplicates: (id: string) => req<{ fingerprint: string; count: number; experiment_ids: string[] }[]>('GET', `/challenges/${id}/duplicates`),
  strategies: (challengeType?: string) => req<Strategy[]>('GET', `/strategies${qs({ challenge_type: challengeType })}`),
  createStrategy: (s: Partial<Strategy>) => req<Strategy>('POST', '/strategies', s),
  updateStrategy: (id: string, s: Partial<Strategy>) => req<Strategy>('PATCH', `/strategies/${id}`, s),
  duplicateStrategy: (id: string) => req<Strategy>('POST', `/strategies/${id}/duplicate`),
  deleteStrategy: (id: string) => req<void>('DELETE', `/strategies/${id}`),
  exportStrategies: () => req<Partial<Strategy>[]>('GET', '/strategies/export'),
  importStrategies: (items: unknown[]) => req<Strategy[]>('POST', '/strategies/import', items),
  generate: (b: Record<string, unknown>) => req<{ candidates: Candidate[]; warnings: string[] }>('POST', '/generate', b),
  candidates: (challengeId: string, saved?: boolean) => req<Candidate[]>('GET', `/candidates${qs({ challenge_id: challengeId, saved })}`),
  updateCandidate: (id: string, b: Record<string, unknown>) => req<Candidate>('PATCH', `/candidates/${id}`, b),
  runTest: (b: Record<string, unknown>) => req<AttemptResult>('POST', '/experiments/run', b),
  submitManual: (b: Record<string, unknown>) => req<AttemptResult>('POST', '/experiments/manual', b),
  confirmFlag: (id: string, flag: string, memberId?: string) => req<{ verdict: string }>('POST', `/experiments/${id}/confirm-flag`, { flag, member_id: memberId }),
  experiments: (f: Record<string, string | number | undefined>) => req<Paged<Experiment>>('GET', `/experiments${qs(f)}`),
  experiment: (id: string) => req<Experiment>('GET', `/experiments/${id}`),
  annotate: (id: string, b: Record<string, unknown>) => req<Experiment>('PATCH', `/experiments/${id}`, b),
  compare: (ids: string[]) => req<Experiment[]>('POST', '/experiments/compare', { ids }),
  runs: (challengeId?: string) => req<Run[]>('GET', `/runs${qs({ challenge_id: challengeId })}`),
  run: (id: string) => req<Run>('GET', `/runs/${id}`),
  startRun: (b: Record<string, unknown>) => req<Run>('POST', '/runs', b),
  runAction: (id: string, action: 'pause' | 'resume' | 'cancel' | 'reject' | 'continue') => req<{ ok: boolean }>('POST', `/runs/${id}/${action}`),
  approveRun: (id: string, ids: string[]) => req<{ ok: boolean }>('POST', `/runs/${id}/approve`, { approved_ids: ids }),
  exportJson: (challengeId?: string) => req<unknown>('GET', `/export/json${qs({ challenge_id: challengeId })}`),
  exportCsv: (challengeId?: string) => req<string>('GET', `/export/csv${qs({ challenge_id: challengeId })}`),
  importJson: (data: unknown) => req<Record<string, number>>('POST', '/import/json', data),
  backup: () => req<{ path: string }>('POST', '/backup'),
}
