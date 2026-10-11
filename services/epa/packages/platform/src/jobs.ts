import { backoffMs, type JobStatus } from '@epa/domain';
import type { Db, Queryable } from './db.js';
import { newId, type Clock } from './core.js';
import type { Logger } from './observability.js';
import type { Metrics } from './observability.js';

export type JobKind =
  | 'workspace.provision'
  | 'workspace.teardown'
  | 'sandbox.run'
  | 'ai.analyze'
  | 'ai.suggest_tests'
  | 'ai.assess_process'
  | 'ai.review_materials'
  | 'ai.suggest_improvements'
  | 'ai.evaluate_answer'
  | 'practice.expire_sweep'
  | 'snapshot.interval_sweep'
  | 'retention.sweep';

export interface JobRow {
  id: string;
  kind: JobKind;
  payload: any;
  status: JobStatus;
  attempts: number;
  max_attempts: number;
  run_after: Date;
  last_error: string | null;
  dedupe_key: string | null;
  trace_id: string | null;
}

export interface EnqueueOptions {
  dedupeKey?: string;
  maxAttempts?: number;
  delayMs?: number;
  traceId?: string;
}

/** Thrown by handlers for errors that must not be retried. */
export class PermanentJobError extends Error {}

export type JobHandler = (job: JobRow) => Promise<void>;

export class JobQueue {
  constructor(
    private readonly db: Db,
    private readonly clock: Clock,
    private readonly log: Logger,
    private readonly metrics: Metrics,
  ) {}

  async enqueue(kind: JobKind, payload: unknown, opts: EnqueueOptions = {}, q: Queryable = this.db): Promise<string> {
    const now = this.clock.now();
    const id = newId('job');
    const row = await q.one<{ id: string }>(
      `INSERT INTO jobs (id, kind, payload, status, attempts, max_attempts, run_after, dedupe_key, trace_id, created_at, updated_at)
       VALUES ($1,$2,$3,'QUEUED',0,$4,$5,$6,$7,$8,$8)
       ON CONFLICT (dedupe_key) DO NOTHING RETURNING id`,
      [id, kind, JSON.stringify(payload), opts.maxAttempts ?? 5, new Date(now.getTime() + (opts.delayMs ?? 0)), opts.dedupeKey ?? null, opts.traceId ?? null, now],
    );
    if (row) {
      this.metrics.inc('jobs_enqueued_total', { kind });
      return row.id;
    }
    const existing = await q.one<{ id: string }>('SELECT id FROM jobs WHERE dedupe_key = $1', [opts.dedupeKey]);
    return existing!.id;
  }

  async claim(kinds: JobKind[]): Promise<JobRow | null> {
    const now = this.clock.now();
    return this.db.one<JobRow>(
      `UPDATE jobs SET status = 'RUNNING', attempts = attempts + 1, updated_at = $1
       WHERE id = (
         SELECT id FROM jobs WHERE status IN ('QUEUED','RETRY') AND run_after <= $1 AND kind = ANY($2::text[])
         ORDER BY run_after, created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
       RETURNING *`,
      [now, kinds],
    );
  }

  async complete(id: string): Promise<void> {
    await this.db.query(`UPDATE jobs SET status = 'SUCCEEDED', updated_at = $2, last_error = NULL WHERE id = $1`, [id, this.clock.now()]);
  }

  async fail(job: JobRow, err: unknown): Promise<JobStatus> {
    const message = (err instanceof Error ? err.message : String(err)).slice(0, 1000);
    const permanent = err instanceof PermanentJobError;
    const dead = permanent || job.attempts >= job.max_attempts;
    const now = this.clock.now();
    const status: JobStatus = dead ? 'DEAD' : 'RETRY';
    await this.db.query(`UPDATE jobs SET status = $2, last_error = $3, run_after = $4, updated_at = $5 WHERE id = $1`, [
      job.id,
      status,
      message,
      new Date(now.getTime() + (dead ? 0 : backoffMs(job.attempts))),
      now,
    ]);
    this.metrics.inc(dead ? 'jobs_dead_total' : 'jobs_retried_total', { kind: job.kind });
    this.log[dead ? 'error' : 'warn']('job failed', { jobId: job.id, kind: job.kind, attempts: job.attempts, status, error: message, traceId: job.trace_id });
    return status;
  }

  async get(id: string): Promise<JobRow | null> {
    return this.db.one<JobRow>('SELECT * FROM jobs WHERE id = $1', [id]);
  }

  async depth(): Promise<Record<string, number>> {
    const rows = await this.db.query<{ status: string; n: number }>(`SELECT status, count(*)::int AS n FROM jobs GROUP BY status`);
    return Object.fromEntries(rows.map((r) => [r.status, r.n]));
  }

  async deadLetters(limit = 50): Promise<JobRow[]> {
    return this.db.query<JobRow>(`SELECT * FROM jobs WHERE status = 'DEAD' ORDER BY updated_at DESC LIMIT $1`, [limit]);
  }
}

/** Polls the queue and dispatches jobs to handlers. */
export class Worker {
  private stopped = false;
  private loop: Promise<void> | null = null;

  constructor(
    private readonly queue: JobQueue,
    private readonly handlers: Partial<Record<JobKind, JobHandler>>,
    private readonly log: Logger,
    private readonly metrics: Metrics,
  ) {}

  private get kinds(): JobKind[] {
    return Object.keys(this.handlers) as JobKind[];
  }

  /** Processes one job. Returns false when no job was ready. */
  async runOnce(): Promise<boolean> {
    const job = await this.queue.claim(this.kinds);
    if (!job) return false;
    const started = Date.now();
    try {
      await this.handlers[job.kind]!(job);
      await this.queue.complete(job.id);
      this.metrics.observe('job_duration_ms', Date.now() - started, { kind: job.kind, outcome: 'ok' });
    } catch (e) {
      await this.queue.fail(job, e);
      this.metrics.observe('job_duration_ms', Date.now() - started, { kind: job.kind, outcome: 'error' });
    }
    return true;
  }

  /** Drains all ready jobs (used by tests and the embedded worker). */
  async drain(maxJobs = 1000): Promise<number> {
    let n = 0;
    while (n < maxJobs && (await this.runOnce())) n++;
    return n;
  }

  start(intervalMs = 500): void {
    if (this.loop) return;
    this.stopped = false;
    this.loop = (async () => {
      while (!this.stopped) {
        try {
          const worked = await this.runOnce();
          if (!worked) await new Promise((r) => setTimeout(r, intervalMs));
        } catch (e) {
          this.log.error('worker loop error', { error: String(e) });
          await new Promise((r) => setTimeout(r, intervalMs));
        }
      }
    })();
  }

  async stop(): Promise<void> {
    this.stopped = true;
    await this.loop;
    this.loop = null;
  }
}
