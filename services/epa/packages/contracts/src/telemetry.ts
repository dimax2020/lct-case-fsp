import { z } from 'zod';
import { TELEMETRY_POLICY, isSafeRelativePath } from '@epa/domain';

export const TELEMETRY_CONTRACT_VERSION = 'telemetry-v1';

const relPath = z.string().min(1).max(512).refine(isSafeRelativePath, { message: 'path must be a safe workspace-relative path' });
const sha256 = z.string().regex(/^[a-f0-9]{64}$/);
const gitSha = z.string().regex(/^[a-f0-9]{40}$/);
const id = z.string().min(1).max(100).regex(/^[A-Za-z0-9_:-]+$/);
const count = z.number().int().min(0).max(1e9);
const shortText = (max: number) => z.string().max(max);

export const telemetryPayloads = {
  session_started: z.strictObject({ client: z.enum(['browser-ide', 'workspace-agent', 'platform', 'vscode']), reason: shortText(200).optional() }),
  session_ended: z.strictObject({ reason: z.enum(['user_closed', 'timeout', 'connection_lost', 'expired', 'submitted', 'teardown']) }),
  file_changed: z.strictObject({
    path: relPath,
    insertedChars: count,
    deletedChars: count,
    insertedLines: count,
    deletedLines: count,
    bytesAfter: count,
  }),
  file_saved: z.strictObject({ path: relPath, contentHash: sha256, bytes: count, workspaceRevision: count.optional() }),
  file_created: z.strictObject({ path: relPath }),
  file_deleted: z.strictObject({ path: relPath }),
  test_started: z.strictObject({ runId: id, command: shortText(TELEMETRY_POLICY.maxCommandLength) }),
  test_finished: z.strictObject({
    runId: id,
    command: shortText(TELEMETRY_POLICY.maxCommandLength),
    status: z.enum(['PASSED', 'FAILED', 'TIMED_OUT', 'UNKNOWN']),
    exitCode: z.number().int().nullable(),
    passed: count,
    failed: count,
    durationMs: count,
    safeLog: shortText(TELEMETRY_POLICY.maxSafeLogBytes),
  }),
  terminal_command: z.strictObject({
    command: shortText(TELEMETRY_POLICY.maxCommandLength),
    exitCode: z.number().int().nullable(),
    durationMs: count,
    timedOut: z.boolean(),
  }),
  git_commit: z.strictObject({
    sha: gitSha,
    message: shortText(2000),
    author: shortText(200),
    changedFiles: z.array(relPath).max(2000),
    snapshotId: id.optional(),
  }),
  snapshot_created: z.strictObject({
    snapshotId: id,
    baseSnapshotId: id.nullable(),
    manifestHash: sha256,
    kind: z.enum(['checkpoint', 'patch']),
    reason: z.enum(['interval', 'significant_save', 'pre_submit', 'git_commit', 'pre_sandbox', 'post_sandbox', 'manual', 'initial']),
  }),
  large_insertion_signal: z.strictObject({
    file: relPath,
    insertedChars: count,
    threshold: count,
    relatedSequence: z.number().int().positive().nullable(),
    interpretation: z.literal('signal_for_additional_review_not_a_verdict'),
  }),
  code_copied: z.strictObject({
    file: relPath,
    chars: count,
    lines: count,
    snippetHash: sha256,
  }),
  code_pasted: z.strictObject({
    file: relPath,
    chars: count,
    lines: count,
    snippetHash: sha256,
    origin: z.enum(['workspace', 'external', 'unknown']),
    interpretation: z.literal('signal_for_additional_review_not_a_verdict'),
  }),
  submit_created: z.strictObject({ submissionId: id, version: z.number().int().positive(), snapshotId: id }),
  review_requested: z.strictObject({ submissionId: id, openComments: count }),
  requirement_changed: z.strictObject({ requirementChangeId: id, baselineSubmissionId: id }),
} as const;

export type TelemetryPayloadType = keyof typeof telemetryPayloads;
export const AGENT_EVENT_TYPES: TelemetryPayloadType[] = [
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
];

export const telemetryEventInput = z.strictObject({
  sequence: z.number().int().min(1).max(Number.MAX_SAFE_INTEGER),
  type: z.enum(Object.keys(telemetryPayloads) as [TelemetryPayloadType, ...TelemetryPayloadType[]]),
  occurredAt: z.iso.datetime({ offset: true }),
  payloadVersion: z.literal(1),
  payload: z.unknown(),
});
export type TelemetryEventInput = z.infer<typeof telemetryEventInput>;

export const telemetryBatch = z.strictObject({
  sessionId: id,
  events: z.array(telemetryEventInput).min(1).max(TELEMETRY_POLICY.maxBatchEvents),
});
export type TelemetryBatch = z.infer<typeof telemetryBatch>;

export function parseTelemetryPayload(type: TelemetryPayloadType, payload: unknown) {
  return telemetryPayloads[type].parse(payload);
}
