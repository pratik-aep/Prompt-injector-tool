CREATE TABLE team_members (
  id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, role TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE targets (
  id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, kind TEXT NOT NULL,
  config TEXT NOT NULL DEFAULT '{}', secret_ref TEXT, enabled INTEGER NOT NULL DEFAULT 1,
  allow_private INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE challenges (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  difficulty TEXT NOT NULL DEFAULT 'easy', type TEXT NOT NULL,
  target_id TEXT REFERENCES targets(id) ON DELETE SET NULL,
  objective TEXT NOT NULL DEFAULT '', allowed_surface TEXT NOT NULL DEFAULT '',
  scoring TEXT NOT NULL DEFAULT '{}', query_budget INTEGER NOT NULL DEFAULT 50,
  max_prompt_length INTEGER NOT NULL DEFAULT 2000,
  allowed_methods TEXT NOT NULL DEFAULT '["api","manual"]',
  status TEXT NOT NULL DEFAULT 'active',
  evaluator_config TEXT NOT NULL DEFAULT '{}',   -- SECRET: expected flag, schemas, rules
  defender TEXT NOT NULL DEFAULT '{}',           -- SECRET: defender system prompt, injected content
  builtin INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE strategies (
  id TEXT PRIMARY KEY, category TEXT NOT NULL, name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '', challenge_types TEXT NOT NULL DEFAULT '[]',
  template TEXT NOT NULL, required_inputs TEXT NOT NULL DEFAULT '[]',
  variants TEXT NOT NULL DEFAULT '[]',
  trust_boundary TEXT NOT NULL DEFAULT '', limitations TEXT NOT NULL DEFAULT '',
  evaluation_criteria TEXT NOT NULL DEFAULT '', builtin INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE optimization_runs (
  id TEXT PRIMARY KEY, challenge_id TEXT NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
  target_id TEXT REFERENCES targets(id) ON DELETE SET NULL, owner_id TEXT REFERENCES team_members(id) ON DELETE SET NULL,
  config TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'pending',
  generation INTEGER NOT NULL DEFAULT 0, attempts_used INTEGER NOT NULL DEFAULT 0,
  best_candidate_id TEXT, best_fitness REAL NOT NULL DEFAULT 0, stop_reason TEXT,
  history TEXT NOT NULL DEFAULT '[]', pending_approval TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE candidates (
  id TEXT PRIMARY KEY, challenge_id TEXT NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
  text TEXT NOT NULL, fingerprint TEXT NOT NULL, strategy_id TEXT, method TEXT NOT NULL,
  parent_ids TEXT NOT NULL DEFAULT '[]', generation INTEGER NOT NULL DEFAULT 0,
  run_id TEXT REFERENCES optimization_runs(id) ON DELETE SET NULL,
  owner_id TEXT REFERENCES team_members(id) ON DELETE SET NULL,
  saved INTEGER NOT NULL DEFAULT 0, tags TEXT NOT NULL DEFAULT '[]',
  provenance TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE INDEX ix_candidates_challenge ON candidates(challenge_id);
CREATE INDEX ix_candidates_fp ON candidates(challenge_id, fingerprint);
CREATE INDEX ix_candidates_run ON candidates(run_id);
CREATE TABLE conversation_sessions (
  id TEXT PRIMARY KEY, challenge_id TEXT NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
  target_id TEXT REFERENCES targets(id) ON DELETE SET NULL, owner_id TEXT REFERENCES team_members(id) ON DELETE SET NULL,
  parent_session_id TEXT REFERENCES conversation_sessions(id) ON DELETE SET NULL, branch_turn INTEGER,
  messages TEXT NOT NULL DEFAULT '[]', turn_limit INTEGER NOT NULL DEFAULT 10,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE experiments (
  id TEXT PRIMARY KEY, challenge_id TEXT NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
  candidate_id TEXT REFERENCES candidates(id) ON DELETE SET NULL,
  target_id TEXT REFERENCES targets(id) ON DELETE SET NULL,
  owner_id TEXT REFERENCES team_members(id) ON DELETE SET NULL,
  run_id TEXT REFERENCES optimization_runs(id) ON DELETE SET NULL,
  session_id TEXT REFERENCES conversation_sessions(id) ON DELETE SET NULL,
  mode TEXT NOT NULL DEFAULT 'api', prompt_text TEXT NOT NULL, prompt_fingerprint TEXT NOT NULL,
  strategy_id TEXT, trial_index INTEGER NOT NULL DEFAULT 0,
  tags TEXT NOT NULL DEFAULT '[]', notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX ix_exp_challenge ON experiments(challenge_id, created_at);
CREATE INDEX ix_exp_run ON experiments(run_id);
CREATE INDEX ix_exp_fp ON experiments(challenge_id, prompt_fingerprint);
CREATE INDEX ix_exp_owner ON experiments(owner_id);
CREATE TABLE responses (
  id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL UNIQUE REFERENCES experiments(id) ON DELETE CASCADE,
  text TEXT NOT NULL DEFAULT '', latency_ms REAL, tokens_in INTEGER, tokens_out INTEGER,
  error TEXT, meta TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE evaluations (
  id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL UNIQUE REFERENCES experiments(id) ON DELETE CASCADE,
  verdict TEXT NOT NULL, score REAL NOT NULL DEFAULT 0, details TEXT NOT NULL DEFAULT '{}',
  reasons TEXT NOT NULL DEFAULT '[]', is_estimate INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE INDEX ix_eval_verdict ON evaluations(verdict);
CREATE TABLE verified_flags (
  id TEXT PRIMARY KEY, challenge_id TEXT NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
  experiment_id TEXT REFERENCES experiments(id) ON DELETE SET NULL,
  member_id TEXT REFERENCES team_members(id) ON DELETE SET NULL,
  flag TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'evaluator', created_at TEXT NOT NULL,
  UNIQUE (challenge_id, flag)
);
CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
