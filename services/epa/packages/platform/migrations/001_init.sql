-- 001_init: core schema for the developer assessment platform.

CREATE TABLE organisations (
  id              text PRIMARY KEY,
  name            text NOT NULL,
  retention_days  integer NOT NULL DEFAULT 90 CHECK (retention_days BETWEEN 1 AND 3650),
  created_at      timestamptz NOT NULL
);

CREATE TABLE employers (
  id               text PRIMARY KEY,
  organisation_id  text NOT NULL REFERENCES organisations(id),
  identity         text NOT NULL,
  role             text NOT NULL DEFAULT 'employer' CHECK (role IN ('employer', 'auditor')),
  password_hash    text,
  created_at       timestamptz NOT NULL,
  UNIQUE (organisation_id, identity)
);

CREATE TABLE candidates (
  id               text PRIMARY KEY,
  identity         text NOT NULL,
  password_hash    text,
  consent_version  text,
  consent_at       timestamptz,
  anonymised_at    timestamptz,
  created_at       timestamptz NOT NULL
);

CREATE TABLE auth_tokens (
  token_hash      text PRIMARY KEY,
  principal_kind  text NOT NULL CHECK (principal_kind IN ('employer', 'auditor', 'candidate', 'agent', 'platform')),
  principal_id    text NOT NULL,
  scope           jsonb NOT NULL DEFAULT '{}'::jsonb,
  expires_at      timestamptz NOT NULL,
  revoked_at      timestamptz,
  created_at      timestamptz NOT NULL
);
CREATE INDEX auth_tokens_principal ON auth_tokens (principal_kind, principal_id);

CREATE TABLE practices (
  id               text PRIMARY KEY,
  organisation_id  text NOT NULL REFERENCES organisations(id),
  employer_id      text NOT NULL REFERENCES employers(id),
  candidate_id     text REFERENCES candidates(id),
  title            text NOT NULL,
  description      text NOT NULL,
  rules            text NOT NULL DEFAULT '',
  template         text NOT NULL,
  task_version     text NOT NULL,
  test_command     jsonb NOT NULL,
  coverage         boolean NOT NULL DEFAULT false,
  snapshot_policy  jsonb NOT NULL,
  workspace_policy jsonb NOT NULL,
  status           text NOT NULL CHECK (status IN ('INVITED','STARTED','IN_PROGRESS','SUBMITTED','REVIEW','COMPLETED','EXPIRED')),
  deadline         timestamptz NOT NULL,
  workspace_id     text,
  consent_id       text,
  terminal_at      timestamptz,
  purged_at        timestamptz,
  created_at       timestamptz NOT NULL,
  updated_at       timestamptz NOT NULL
);
CREATE INDEX practices_org ON practices (organisation_id, created_at DESC, id DESC);
CREATE INDEX practices_candidate ON practices (candidate_id);
CREATE INDEX practices_deadline ON practices (status, deadline);

CREATE TABLE invitations (
  id               text PRIMARY KEY,
  practice_id      text NOT NULL REFERENCES practices(id),
  candidate_email  text NOT NULL,
  token_hash       text NOT NULL UNIQUE,
  expires_at       timestamptz NOT NULL,
  consumed_at      timestamptz,
  consumed_by      text,
  created_at       timestamptz NOT NULL
);

CREATE TABLE consents (
  id               text PRIMARY KEY,
  candidate_id     text NOT NULL REFERENCES candidates(id),
  practice_id      text NOT NULL REFERENCES practices(id),
  consent_version  text NOT NULL,
  text_hash        text NOT NULL,
  accepted_at      timestamptz NOT NULL,
  UNIQUE (practice_id, candidate_id, consent_version)
);

CREATE TABLE workspaces (
  id               text PRIMARY KEY,
  practice_id      text NOT NULL REFERENCES practices(id),
  driver           text NOT NULL,
  runtime_ref      text,
  identity         text NOT NULL UNIQUE,
  lifecycle        text NOT NULL CHECK (lifecycle IN ('PROVISIONING','READY','FAILED','TEARING_DOWN','DESTROYED')),
  policy_version   text NOT NULL,
  policy           jsonb NOT NULL,
  expires_at       timestamptz NOT NULL,
  failure_reason   text,
  created_at       timestamptz NOT NULL,
  ready_at         timestamptz,
  destroyed_at     timestamptz
);

CREATE TABLE dev_sessions (
  id               text PRIMARY KEY,
  practice_id      text NOT NULL REFERENCES practices(id),
  workspace_id     text REFERENCES workspaces(id),
  kind             text NOT NULL CHECK (kind IN ('workspace', 'platform')),
  client           text NOT NULL DEFAULT 'gateway' CHECK (client IN ('gateway', 'sidecar', 'platform', 'vscode')),
  consent_id       text,
  started_at       timestamptz NOT NULL,
  ended_at         timestamptz,
  end_reason       text,
  last_sequence    integer NOT NULL DEFAULT 0,
  last_hash        text,
  last_seen_at     timestamptz
);
CREATE INDEX dev_sessions_practice ON dev_sessions (practice_id, started_at);

CREATE TABLE telemetry_events (
  id               text PRIMARY KEY,
  session_id       text NOT NULL REFERENCES dev_sessions(id),
  practice_id      text NOT NULL REFERENCES practices(id),
  sequence         integer NOT NULL,
  type             text NOT NULL,
  occurred_at      timestamptz NOT NULL,
  received_at      timestamptz NOT NULL,
  payload_version  integer NOT NULL,
  payload          jsonb NOT NULL,
  content_hash     text NOT NULL,
  integrity_hash   text NOT NULL,
  UNIQUE (session_id, sequence)
);
CREATE INDEX telemetry_events_timeline ON telemetry_events (practice_id, occurred_at, session_id, sequence);

CREATE TABLE telemetry_diagnostics (
  id               text PRIMARY KEY,
  session_id       text NOT NULL,
  practice_id      text NOT NULL,
  kind             text NOT NULL,
  detail           jsonb NOT NULL,
  created_at       timestamptz NOT NULL
);

CREATE TABLE snapshots (
  id               text PRIMARY KEY,
  practice_id      text NOT NULL REFERENCES practices(id),
  ordinal          integer NOT NULL,
  base_snapshot_id text REFERENCES snapshots(id),
  checkpoint_id    text,
  kind             text NOT NULL CHECK (kind IN ('checkpoint', 'patch')),
  reason           text NOT NULL,
  chain_length     integer NOT NULL,
  object_key       text NOT NULL,
  object_hash      text NOT NULL,
  manifest_hash    text NOT NULL,
  file_count       integer NOT NULL,
  total_bytes      bigint NOT NULL,
  skipped          jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at       timestamptz NOT NULL,
  purged_at        timestamptz
);
CREATE UNIQUE INDEX snapshots_practice_ordinal ON snapshots (practice_id, ordinal);

CREATE TABLE submissions (
  id                     text PRIMARY KEY,
  practice_id            text NOT NULL REFERENCES practices(id),
  snapshot_id            text NOT NULL REFERENCES snapshots(id),
  version                integer NOT NULL,
  idempotency_key        text NOT NULL,
  commit_sha             text,
  baseline_submission_id text REFERENCES submissions(id),
  requirement_change_id  text,
  submitted_at           timestamptz NOT NULL,
  UNIQUE (practice_id, version),
  UNIQUE (practice_id, idempotency_key)
);

CREATE TABLE git_commits (
  sha              text NOT NULL,
  practice_id      text NOT NULL REFERENCES practices(id),
  message          text NOT NULL,
  author           text NOT NULL,
  changed_files    jsonb NOT NULL,
  snapshot_id      text REFERENCES snapshots(id),
  committed_at     timestamptz NOT NULL,
  PRIMARY KEY (practice_id, sha)
);

CREATE TABLE test_runs (
  id               text PRIMARY KEY,
  practice_id      text NOT NULL REFERENCES practices(id),
  snapshot_id      text REFERENCES snapshots(id),
  submission_id    text REFERENCES submissions(id),
  command          jsonb NOT NULL,
  origin           text NOT NULL CHECK (origin IN ('sandbox', 'workspace')),
  job_id           text,
  status           text NOT NULL,
  summary          jsonb,
  log_object_key   text,
  created_at       timestamptz NOT NULL,
  started_at       timestamptz,
  finished_at      timestamptz
);
CREATE INDEX test_runs_submission ON test_runs (submission_id);

CREATE TABLE review_comments (
  id               text PRIMARY KEY,
  practice_id      text NOT NULL REFERENCES practices(id),
  submission_id    text NOT NULL REFERENCES submissions(id),
  author_kind      text NOT NULL,
  author_id        text NOT NULL,
  file_path        text NOT NULL,
  line_start       integer NOT NULL,
  line_end         integer NOT NULL,
  body             text NOT NULL,
  status           text NOT NULL CHECK (status IN ('OPEN', 'RESOLVED')),
  resolved_by_kind text,
  resolved_by_id   text,
  resolved_at      timestamptz,
  created_at       timestamptz NOT NULL
);
CREATE INDEX review_comments_practice ON review_comments (practice_id, created_at);

CREATE TABLE review_decisions (
  id               text PRIMARY KEY,
  practice_id      text NOT NULL REFERENCES practices(id),
  submission_id    text NOT NULL REFERENCES submissions(id),
  employer_id      text NOT NULL,
  decision         text NOT NULL CHECK (decision IN ('START_REVIEW', 'REQUEST_CHANGES', 'APPROVE')),
  created_at       timestamptz NOT NULL
);

CREATE TABLE requirement_changes (
  id                     text PRIMARY KEY,
  practice_id            text NOT NULL REFERENCES practices(id),
  baseline_submission_id text NOT NULL REFERENCES submissions(id),
  text                   text NOT NULL,
  reason                 text NOT NULL,
  acceptance_criteria    jsonb NOT NULL,
  due_at                 timestamptz NOT NULL,
  created_by_kind        text NOT NULL,
  created_by_id          text NOT NULL,
  revised_submission_id  text REFERENCES submissions(id),
  created_at             timestamptz NOT NULL
);

CREATE TABLE ai_analyses (
  id               text PRIMARY KEY,
  practice_id      text NOT NULL REFERENCES practices(id),
  submission_id    text NOT NULL REFERENCES submissions(id),
  status           text NOT NULL,
  provider_id      text NOT NULL,
  model_id         text NOT NULL,
  template_version text NOT NULL,
  policy_version   text NOT NULL,
  input_hashes     jsonb,
  output           jsonb,
  rejected         jsonb NOT NULL DEFAULT '[]'::jsonb,
  error            text,
  attempts         integer NOT NULL DEFAULT 0,
  created_at       timestamptz NOT NULL,
  finished_at      timestamptz
);

CREATE TABLE interview_questions (
  id                 text PRIMARY KEY,
  practice_id        text NOT NULL REFERENCES practices(id),
  submission_id      text NOT NULL REFERENCES submissions(id),
  analysis_id        text REFERENCES ai_analyses(id),
  parent_question_id text REFERENCES interview_questions(id),
  depth              integer NOT NULL DEFAULT 0,
  text               text NOT NULL,
  rationale          text NOT NULL,
  evidence           jsonb NOT NULL,
  ai_meta            jsonb NOT NULL,
  created_at         timestamptz NOT NULL
);

CREATE TABLE interview_answers (
  id               text PRIMARY KEY,
  question_id      text NOT NULL UNIQUE REFERENCES interview_questions(id),
  candidate_id     text NOT NULL,
  text             text NOT NULL,
  evaluation       jsonb,
  evaluation_status text NOT NULL DEFAULT 'PENDING',
  ai_meta          jsonb,
  created_at       timestamptz NOT NULL
);

CREATE TABLE assessments (
  id               text PRIMARY KEY,
  practice_id      text NOT NULL REFERENCES practices(id),
  rubric_version   text NOT NULL,
  dimensions       jsonb NOT NULL,
  aggregation      jsonb NOT NULL,
  overall_score    integer,
  status           text NOT NULL CHECK (status IN ('DRAFT', 'APPROVED')),
  input_refs       jsonb NOT NULL,
  approved_by      text,
  approved_at      timestamptz,
  created_at       timestamptz NOT NULL
);

CREATE TABLE jobs (
  id               text PRIMARY KEY,
  kind             text NOT NULL,
  payload          jsonb NOT NULL,
  status           text NOT NULL CHECK (status IN ('QUEUED','RUNNING','SUCCEEDED','RETRY','DEAD')),
  attempts         integer NOT NULL DEFAULT 0,
  max_attempts     integer NOT NULL DEFAULT 5,
  run_after        timestamptz NOT NULL,
  last_error       text,
  dedupe_key       text UNIQUE,
  trace_id         text,
  created_at       timestamptz NOT NULL,
  updated_at       timestamptz NOT NULL
);
CREATE INDEX jobs_ready ON jobs (status, run_after);

CREATE TABLE idempotency_keys (
  scope            text NOT NULL,
  key              text NOT NULL,
  request_hash     text NOT NULL,
  response         jsonb NOT NULL,
  created_at       timestamptz NOT NULL,
  PRIMARY KEY (scope, key)
);

CREATE TABLE audit_log (
  seq              integer PRIMARY KEY,
  id               text NOT NULL UNIQUE,
  at               timestamptz NOT NULL,
  actor_kind       text NOT NULL,
  actor_id         text NOT NULL,
  organisation_id  text,
  practice_id      text,
  action           text NOT NULL,
  entity_type      text NOT NULL,
  entity_id        text NOT NULL,
  detail           jsonb NOT NULL,
  prev_hash        text,
  hash             text NOT NULL
);
CREATE INDEX audit_log_practice ON audit_log (practice_id, seq);

-- ---------- Immutability guards ----------

-- Audit log: append-only for every application principal, no bypass.
CREATE FUNCTION epa_forbid_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'table % is append-only', TG_TABLE_NAME USING ERRCODE = 'insufficient_privilege';
END $$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION epa_forbid_mutation();

-- Telemetry, snapshots and submissions: immutable; only the retention purge
-- (transaction-local flag epa.retention_purge = 'on') may delete or mark them purged.
CREATE FUNCTION epa_immutable_except_retention() RETURNS trigger AS $$
BEGIN
  IF current_setting('epa.retention_purge', true) = 'on' THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'table % is immutable', TG_TABLE_NAME USING ERRCODE = 'insufficient_privilege';
END $$ LANGUAGE plpgsql;

CREATE TRIGGER telemetry_events_immutable BEFORE UPDATE OR DELETE ON telemetry_events
  FOR EACH ROW EXECUTE FUNCTION epa_immutable_except_retention();
CREATE TRIGGER snapshots_immutable BEFORE UPDATE OR DELETE ON snapshots
  FOR EACH ROW EXECUTE FUNCTION epa_immutable_except_retention();
CREATE TRIGGER submissions_immutable BEFORE UPDATE OR DELETE ON submissions
  FOR EACH ROW EXECUTE FUNCTION epa_immutable_except_retention();
