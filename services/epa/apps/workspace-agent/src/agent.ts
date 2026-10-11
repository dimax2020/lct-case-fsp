import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import type { TelemetryEventInput, TelemetryPayloadType } from '@epa/contracts';
import { TELEMETRY_POLICY, backoffMs, normalizeWorkspacePath } from '@epa/domain';
import { classifyLargeInsertion, computeEditStats, redactSecrets, safeLog, sha256Hex, PAYLOAD_VERSION } from '@epa/telemetry';

export interface TransportResult {
  accepted: number;
  duplicates: number;
  nextExpectedSequence: number;
  gap: { expected: number; received: number } | null;
}

export interface TelemetryTransport {
  send(batch: { sessionId: string; events: TelemetryEventInput[] }): Promise<TransportResult>;
}

interface OutboxState {
  sessionId: string;
  nextSequence: number;
  pending: TelemetryEventInput[];
}

export interface AgentOptions {
  sessionId: string;
  outboxDir: string;
  transport: TelemetryTransport;
  now?: () => Date;
  batchSize?: number;
  largeInsertionThreshold?: number;
  /** Retry scheduling; tests can disable timers and call flush() explicitly. */
  autoRetry?: boolean;
}

/**
 * Workspace-scoped telemetry agent. It only knows workspace-relative paths, assigns a gap-free
 * sequence per session, persists events in a durable outbox before sending, and retries with
 * backoff. Server-side deduplication by (session, sequence) makes retries safe.
 */
export class WorkspaceAgent {
  private state!: OutboxState;
  private flushing: Promise<void> | null = null;
  private failures = 0;
  private retryTimer: NodeJS.Timeout | null = null;
  private readonly now: () => Date;
  private readonly file: string;
  lastError: string | null = null;

  private constructor(private readonly opts: AgentOptions) {
    this.now = opts.now ?? (() => new Date());
    this.file = path.join(opts.outboxDir, `outbox-${opts.sessionId}.json`);
  }

  static async open(opts: AgentOptions): Promise<WorkspaceAgent> {
    const a = new WorkspaceAgent(opts);
    await mkdir(opts.outboxDir, { recursive: true });
    try {
      a.state = JSON.parse(await readFile(a.file, 'utf8'));
    } catch {
      a.state = { sessionId: opts.sessionId, nextSequence: 1, pending: [] };
    }
    return a;
  }

  get pendingCount(): number {
    return this.state.pending.length;
  }

  get sessionId(): string {
    return this.opts.sessionId;
  }

  private persistChain: Promise<void> = Promise.resolve();

  private persist(): Promise<void> {
    const snapshot = JSON.stringify(this.state);
    this.persistChain = this.persistChain.then(async () => {
      const tmp = `${this.file}.tmp`;
      await writeFile(tmp, snapshot);
      await rename(tmp, this.file);
    });
    return this.persistChain;
  }

  /** Records an event durably and returns its sequence number. */
  async record(type: TelemetryPayloadType, payload: Record<string, unknown>, occurredAt = this.now()): Promise<number> {
    const sequence = this.state.nextSequence++;
    this.state.pending.push({ sequence, type, occurredAt: occurredAt.toISOString(), payloadVersion: PAYLOAD_VERSION, payload });
    await this.persist();
    void this.flush().catch(() => undefined);
    return sequence;
  }

  /** Sends pending events in order. Failures keep events in the outbox for a later retry. */
  async flush(): Promise<void> {
    if (this.flushing) return this.flushing;
    this.flushing = this.drain().finally(() => {
      this.flushing = null;
    });
    return this.flushing;
  }

  private async drain(): Promise<void> {
        while (this.state.pending.length > 0) {
          const batch = this.state.pending.slice(0, this.opts.batchSize ?? 100);
          let res: TransportResult;
          try {
            res = await this.opts.transport.send({ sessionId: this.opts.sessionId, events: batch });
          } catch (e) {
            this.failures++;
            this.lastError = e instanceof Error ? e.message : String(e);
            this.scheduleRetry();
            return;
          }
          this.failures = 0;
          this.lastError = null;
          this.state.pending = this.state.pending.filter((e) => e.sequence >= res.nextExpectedSequence);
          await this.persist();
          if (res.gap && this.state.pending[0]?.sequence !== res.nextExpectedSequence) {
            this.lastError = `server expects sequence ${res.nextExpectedSequence} which is no longer buffered`;
            return;
          }
        }
  }

  private scheduleRetry(): void {
    if (this.opts.autoRetry === false || this.retryTimer) return;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      void this.flush();
    }, backoffMs(this.failures, 500, 30_000));
    this.retryTimer.unref?.();
  }

  close(): void {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }

  // ---------- Event builders ----------

  async sessionStarted(client: 'browser-ide' | 'workspace-agent' | 'vscode' = 'workspace-agent', reason?: string) {
    return this.record('session_started', { client, ...(reason ? { reason: reason.slice(0, 200) } : {}) });
  }

  async sessionEnded(reason: 'user_closed' | 'timeout' | 'connection_lost' | 'expired' | 'submitted' | 'teardown') {
    return this.record('session_ended', { reason });
  }

  /**
   * A save from the IDE: aggregated change metadata, the save itself, and — if the editor reported
   * a large paste (or, for writes without editor stats, a large single insertion) — a signal.
   */
  async fileWritten(input: { path: string; before: string | null; after: string; pastedChars?: number; revision?: number }) {
    const p = normalizeWorkspacePath(input.path);
    const created = input.before === null;
    const stats = computeEditStats(input.before ?? '', input.after);
    if (created) await this.record('file_created', { path: p });
    await this.record('file_changed', { path: p, ...stats, bytesAfter: Buffer.byteLength(input.after) });
    const savedSeq = await this.record('file_saved', {
      path: p,
      contentHash: sha256Hex(input.after),
      bytes: Buffer.byteLength(input.after),
      ...(input.revision !== undefined ? { workspaceRevision: input.revision } : {}),
    });
    const inserted = input.pastedChars !== undefined ? input.pastedChars : stats.insertedChars;
    if ((input.pastedChars ?? 0) > 0) {
      await this.record('code_pasted', {
        file: p,
        chars: input.pastedChars!,
        lines: 1,
        snippetHash: sha256Hex(`browser-paste:${p}:${input.pastedChars}`),
        origin: 'unknown',
        interpretation: 'signal_for_additional_review_not_a_verdict',
      });
    }
    const signal = classifyLargeInsertion({ file: p, insertedChars: inserted, threshold: this.opts.largeInsertionThreshold, relatedSequence: savedSeq });
    if (signal) await this.record('large_insertion_signal', { ...signal });
    return { stats, signal };
  }

  async fileDeleted(relPath: string) {
    return this.record('file_deleted', { path: normalizeWorkspacePath(relPath) });
  }

  async terminalCommand(input: { command: string; exitCode: number | null; durationMs: number; timedOut: boolean }) {
    return this.record('terminal_command', {
      command: redactSecrets(input.command).slice(0, TELEMETRY_POLICY.maxCommandLength),
      exitCode: input.exitCode,
      durationMs: Math.round(input.durationMs),
      timedOut: input.timedOut,
    });
  }

  async testStarted(runId: string, command: string) {
    return this.record('test_started', { runId, command: redactSecrets(command).slice(0, TELEMETRY_POLICY.maxCommandLength) });
  }

  async testFinished(input: { runId: string; command: string; status: 'PASSED' | 'FAILED' | 'TIMED_OUT' | 'UNKNOWN'; exitCode: number | null; passed: number; failed: number; durationMs: number; log: string }) {
    return this.record('test_finished', {
      runId: input.runId,
      command: redactSecrets(input.command).slice(0, TELEMETRY_POLICY.maxCommandLength),
      status: input.status,
      exitCode: input.exitCode,
      passed: input.passed,
      failed: input.failed,
      durationMs: Math.round(input.durationMs),
      safeLog: safeLog(input.log, TELEMETRY_POLICY.maxSafeLogBytes).text,
    });
  }

  async gitCommit(input: { sha: string; message: string; author: string; changedFiles: string[]; snapshotId?: string }) {
    return this.record('git_commit', { ...input, message: redactSecrets(input.message).slice(0, 2000), changedFiles: input.changedFiles.map((f) => normalizeWorkspacePath(f)) });
  }

  async snapshotCreated(input: { snapshotId: string; baseSnapshotId: string | null; manifestHash: string; kind: 'checkpoint' | 'patch'; reason: string }) {
    return this.record('snapshot_created', input as any);
  }
}
