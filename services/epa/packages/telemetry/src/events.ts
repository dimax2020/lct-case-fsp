import { createHash } from 'node:crypto';
import { TELEMETRY_POLICY } from '@epa/domain';

export const TELEMETRY_EVENT_TYPES = [
  'session_started',
  'session_ended',
  'file_changed',
  'file_saved',
  'file_created',
  'file_deleted',
  'test_started',
  'test_finished',
  'terminal_command',
  'git_commit',
  'snapshot_created',
  'large_insertion_signal',
  'code_copied',
  'code_pasted',
  'submit_created',
  'review_requested',
  'requirement_changed',
] as const;
export type TelemetryEventType = (typeof TELEMETRY_EVENT_TYPES)[number];

export const PAYLOAD_VERSION = 1;

/** Deterministic JSON serialisation (sorted keys) used for integrity hashes. */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value ?? null);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(',')}}`;
}

export function sha256Hex(data: string | Buffer): string {
  return createHash('sha256').update(data).digest('hex');
}

export interface HashableEvent {
  sessionId: string;
  sequence: number;
  type: string;
  occurredAt: string;
  payloadVersion: number;
  payload: unknown;
}

/** Content hash of an event as submitted by the agent; identical retries produce identical hashes. */
export function eventContentHash(e: HashableEvent): string {
  return sha256Hex(
    canonicalJson({
      sessionId: e.sessionId,
      sequence: e.sequence,
      type: e.type,
      occurredAt: e.occurredAt,
      payloadVersion: e.payloadVersion,
      payload: e.payload,
    }),
  );
}

/** Chain hash: binds an event to its predecessor in the session so silent edits are detectable. */
export function chainHash(prevHash: string | null, contentHash: string): string {
  return sha256Hex(`${prevHash ?? 'genesis'}:${contentHash}`);
}

// ---------- Large insertion signal ----------

export interface LargeInsertionSignal {
  file: string;
  insertedChars: number;
  threshold: number;
  relatedSequence: number | null;
  interpretation: 'signal_for_additional_review_not_a_verdict';
}

export function classifyLargeInsertion(input: {
  file: string;
  insertedChars: number;
  threshold?: number;
  relatedSequence?: number | null;
}): LargeInsertionSignal | null {
  const threshold = input.threshold ?? TELEMETRY_POLICY.largeInsertionThresholdChars;
  if (!Number.isFinite(input.insertedChars) || input.insertedChars < threshold) return null;
  return {
    file: input.file,
    insertedChars: input.insertedChars,
    threshold,
    relatedSequence: input.relatedSequence ?? null,
    interpretation: 'signal_for_additional_review_not_a_verdict',
  };
}

// ---------- Edit statistics ----------

export interface EditStats {
  insertedChars: number;
  deletedChars: number;
  insertedLines: number;
  deletedLines: number;
}

/** Aggregated change metadata between two versions of a file (common prefix/suffix trimming on lines). */
export function computeEditStats(before: string, after: string): EditStats {
  const a = before.length ? before.split('\n') : [];
  const b = after.length ? after.split('\n') : [];
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let endA = a.length - 1;
  let endB = b.length - 1;
  while (endA >= start && endB >= start && a[endA] === b[endB]) {
    endA--;
    endB--;
  }
  const removed = a.slice(start, endA + 1);
  const added = b.slice(start, endB + 1);
  const chars = (lines: string[]) => lines.reduce((n, l) => n + l.length, 0) + Math.max(0, lines.length - 1);
  return {
    insertedChars: chars(added),
    deletedChars: chars(removed),
    insertedLines: added.length,
    deletedLines: removed.length,
  };
}
