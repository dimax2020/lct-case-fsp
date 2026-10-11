import { DomainError } from './errors.js';

// ---------- Review comments ----------

export type CommentStatus = 'OPEN' | 'RESOLVED';

export function assertCommentTransition(from: CommentStatus, to: CommentStatus): void {
  if (!(from === 'OPEN' && to === 'RESOLVED')) {
    throw new DomainError('INVALID_TRANSITION', `comment transition ${from} -> ${to} is not allowed`);
  }
}

export function assertCommentRange(input: { lineStart: number; lineEnd: number; fileLineCount: number }): void {
  const { lineStart, lineEnd, fileLineCount } = input;
  if (!Number.isInteger(lineStart) || !Number.isInteger(lineEnd) || lineStart < 1 || lineEnd < lineStart) {
    throw new DomainError('VALIDATION', 'invalid line range');
  }
  if (lineEnd > fileLineCount) {
    throw new DomainError('VALIDATION', `line range exceeds file length (${fileLineCount} lines)`);
  }
}

// ---------- Requirement change ----------

export interface RequirementChangeInput {
  text: string;
  reason: string;
  acceptanceCriteria: string[];
  dueAt: Date;
}

export function assertValidRequirementChange(input: RequirementChangeInput, now: Date): void {
  if (input.text.trim().length < 10) throw new DomainError('VALIDATION', 'requirement text is too short');
  if (input.reason.trim().length === 0) throw new DomainError('VALIDATION', 'reason is required');
  const criteria = input.acceptanceCriteria.map((c) => c.trim()).filter(Boolean);
  if (criteria.length === 0) throw new DomainError('VALIDATION', 'at least one acceptance criterion is required');
  if (criteria.length > 20) throw new DomainError('VALIDATION', 'too many acceptance criteria');
  if (new Set(criteria).size !== criteria.length) throw new DomainError('VALIDATION', 'duplicate acceptance criteria');
  if (input.dueAt.getTime() <= now.getTime()) throw new DomainError('VALIDATION', 'due date must be in the future');
}

// ---------- Test runs (sandbox jobs) ----------

export type TestRunStatus = 'QUEUED' | 'RUNNING' | 'PASSED' | 'FAILED' | 'TIMED_OUT' | 'UNKNOWN';

const TEST_RUN_TRANSITIONS: Record<TestRunStatus, TestRunStatus[]> = {
  QUEUED: ['RUNNING', 'UNKNOWN'],
  RUNNING: ['PASSED', 'FAILED', 'TIMED_OUT', 'UNKNOWN', 'QUEUED'],
  PASSED: [],
  FAILED: [],
  TIMED_OUT: [],
  UNKNOWN: [],
};

export function assertTestRunTransition(from: TestRunStatus, to: TestRunStatus): void {
  if (!TEST_RUN_TRANSITIONS[from].includes(to)) {
    throw new DomainError('INVALID_TRANSITION', `test run transition ${from} -> ${to} is not allowed`);
  }
}

/** Maps a raw sandbox outcome to a status. A run is never PASSED unless the process exited 0 and results parsed. */
export function mapSandboxOutcome(o: {
  timedOut: boolean;
  infraError: boolean;
  exitCode: number | null;
  parsed: { passed: number; failed: number } | null;
}): TestRunStatus {
  if (o.infraError) return 'UNKNOWN';
  if (o.timedOut) return 'TIMED_OUT';
  if (o.exitCode === null) return 'UNKNOWN';
  if (o.exitCode === 0 && o.parsed && o.parsed.failed === 0 && o.parsed.passed > 0) return 'PASSED';
  if (o.exitCode === 0 && !o.parsed) return 'UNKNOWN';
  return 'FAILED';
}

// ---------- Jobs ----------

export type JobStatus = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'RETRY' | 'DEAD';

// ---------- Workspace lifecycle ----------

export type WorkspaceLifecycle = 'PROVISIONING' | 'READY' | 'FAILED' | 'TEARING_DOWN' | 'DESTROYED';

// ---------- AI analysis ----------

export type AnalysisStatus = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'RETRYING' | 'FAILED';
