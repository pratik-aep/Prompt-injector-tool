export type Verdict = 'verified_success' | 'possible_success' | 'failed' | 'invalid_test' | 'evaluation_error'

export interface Member { id: string; name: string; role: string }
export interface Target {
  id: string; name: string; kind: string; config: Record<string, any>; secret_ref: string | null
  credential_available: boolean | null; enabled: boolean; allow_private: boolean; remote: boolean
}
export interface OllamaModel { name: string; size_bytes?: number; family?: string; parameter_size?: string; quantization?: string }
export interface OllamaStatus { installed: boolean; server_up: boolean; url: string; models: OllamaModel[]; error: string | null }
export interface VerifiedFlag { flag: string; experiment_id: string | null; member_id: string | null; source: string; created_at: string }
export interface Challenge {
  id: string; name: string; description: string; difficulty: string; type: string; target_id: string | null
  objective: string; allowed_surface: string; scoring: Record<string, any>; query_budget: number; max_prompt_length: number
  allowed_methods: string[]; status: string; builtin: boolean; attempts_used: number; attempts_remaining: number
  has_defender_prompt: boolean; has_local_evaluator: boolean; verified_flags: VerifiedFlag[]
}
export interface Strategy {
  id: string; category: string; name: string; description: string; challenge_types: string[]; template: string
  variants: string[]; required_inputs: string[]; trust_boundary: string; limitations: string; evaluation_criteria: string; builtin: boolean
}
export interface Candidate {
  id: string; challenge_id: string; text: string; strategy_id: string | null; method: string; parent_ids: string[]
  generation: number; run_id: string | null; saved: boolean; tags: string[]; provenance: Record<string, any>; token_estimate: number
}
export interface CheckResult { kind: string; triggered: boolean; progress: number; reason: string; deterministic: boolean }
export interface Experiment {
  id: string; challenge_id: string; candidate_id: string | null; target_id: string | null; owner_id: string | null
  run_id: string | null; session_id: string | null; mode: string; strategy_id: string | null; trial_index: number
  tags: string[]; notes: string; created_at: string; prompt_text: string; verdict: Verdict | null; score: number | null
  is_estimate: boolean | null; latency_ms: number | null; tokens_in: number | null; tokens_out: number | null; error: string | null
  response_text?: string | null; reasons?: string[]; checks?: CheckResult[]
}
export interface AttemptResult {
  experiment_id: string; verdict: Verdict; score: number; reasons: string[]; is_estimate: boolean; response_text: string
  error: string | null; latency_ms: number; tokens_in: number | null; tokens_out: number | null; duplicate_of: string | null
  session_id: string | null; verified: boolean; checks: CheckResult[]; trials?: number; success_rate?: number; queries_used?: number
}
export interface RunCandidate {
  id: string; text: string; strategy_id: string | null; method: string; parent_ids: string[]; generation: number
  fitness: number | null; verdict: Verdict | null; op: string | null; experiment_id: string | null
  components: Record<string, number> | null
}
export interface HistoryEntry {
  generation: number; evaluated: number; attempts_used: number; best_fitness: number; generation_best: number; mean_fitness: number
  verdicts: Record<string, number>; improvements: { child: string; parent: string | null; op: string; delta: number }[]
}
export interface Run {
  id: string; challenge_id: string; target_id: string | null; config: Record<string, any>; state: string; generation: number
  attempts_used: number; best_candidate_id: string | null; best_fitness: number; stop_reason: string | null
  history: HistoryEntry[]; pending_approval: { id: string; text: string; strategy_id: string | null; parent_ids: string[]; op: string | null }[] | null
  candidates?: RunCandidate[]; active?: boolean; created_at: string
}
export interface Overview {
  active_challenges: number; solved_challenges: number; total_attempts: number; verified_successes: number
  possible_successes: number; invalid_tests: number; success_rate: number; remaining_budget: number
  recent_experiments: { id: string; challenge_id: string; created_at: string; mode: string; prompt_preview: string; verdict: Verdict | null }[]
}
export interface Analytics {
  by_strategy: { strategy_id: string; name: string; attempts: number; verified: number; possible: number; invalid: number; success_rate: number }[]
  by_challenge: { challenge_id: string; name: string; budget: number; attempts: number; verified: number }[]
  by_target: { target_id: string; name: string; kind: string; attempts: number; verified: number; avg_latency_ms: number | null; p95_latency_ms: number | null; tokens_in: number; tokens_out: number; success_rate: number }[]
  runs: { run_id: string; challenge_id: string; state: string; stop_reason: string | null; attempts_used: number; series: { generation: number; best_fitness: number; mean_fitness: number }[] }[]
}
export interface Paged<T> { total: number; limit: number; offset: number; items: T[] }
