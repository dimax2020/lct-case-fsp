import { mkdir, rm, chmod } from 'node:fs/promises';
import path from 'node:path';
import { DEFAULT_SANDBOX_POLICY, assertTestRunTransition, mapSandboxOutcome, notFound, type SandboxPolicy, type TestRunStatus } from '@epa/domain';
import { newId, PermanentJobError, type Ctx, type JobRow, type Queryable } from '@epa/platform';
import { parseNodeTestOutput, safeLog, type ParsedTestResults } from '@epa/telemetry';
import type { SnapshotService } from '@epa/snapshots';
import type { PlatformEvents } from '@epa/timeline';
import type { SandboxDriver } from './drivers.js';

export interface TestRunRow {
  id: string;
  practice_id: string;
  snapshot_id: string | null;
  submission_id: string | null;
  origin: 'sandbox' | 'workspace';
  command: string[];
  job_id: string | null;
  status: TestRunStatus;
  summary: TestRunSummary | null;
  log_object_key: string | null;
  created_at: Date;
  started_at: Date | null;
  finished_at: Date | null;
}

export interface TestRunSummary {
  status: TestRunStatus;
  exitCode: number | null;
  durationMs: number;
  tests: number;
  passed: number;
  failed: number;
  skipped: number;
  failedTests: string[];
  coverage: ParsedTestResults['coverage'];
  logTruncated: boolean;
  reason: string | null;
  driver: string;
}

export class SandboxOrchestrator {
  constructor(
    private readonly ctx: Ctx,
    private readonly driver: SandboxDriver,
    private readonly snapshots: SnapshotService,
    private readonly events: PlatformEvents,
    private readonly policy: SandboxPolicy = DEFAULT_SANDBOX_POLICY,
  ) {}

  /** Queues a sandbox run for an immutable submission snapshot. */
  async enqueue(q: Queryable, input: { practiceId: string; snapshotId: string; submissionId: string | null; command: string[] }): Promise<string> {
    const id = newId('tr');
    await q.query(
      `INSERT INTO test_runs (id, practice_id, snapshot_id, submission_id, origin, command, status, created_at) VALUES ($1,$2,$3,$4,'sandbox',$5,'QUEUED',$6)`,
      [id, input.practiceId, input.snapshotId, input.submissionId, JSON.stringify(input.command), this.ctx.clock.now()],
    );
    const jobId = await this.ctx.jobs.enqueue('sandbox.run', { testRunId: id }, { dedupeKey: `sandbox:${id}`, maxAttempts: 3 }, q);
    await q.query('UPDATE test_runs SET job_id = $2 WHERE id = $1', [id, jobId]);
    return id;
  }

  async get(id: string): Promise<TestRunRow> {
    const r = await this.ctx.db.one<TestRunRow>('SELECT * FROM test_runs WHERE id = $1', [id]);
    if (!r) throw notFound('test run');
    return r;
  }

  private async setStatus(run: TestRunRow, to: TestRunStatus, extra: Partial<Pick<TestRunRow, 'summary' | 'log_object_key'>> = {}) {
    assertTestRunTransition(run.status, to);
    const now = this.ctx.clock.now();
    await this.ctx.db.query(
      `UPDATE test_runs SET status = $2, summary = COALESCE($3, summary), log_object_key = COALESCE($4, log_object_key),
         started_at = CASE WHEN $2::text = 'RUNNING' THEN $5::timestamptz ELSE started_at END,
         finished_at = CASE WHEN $2::text IN ('PASSED','FAILED','TIMED_OUT','UNKNOWN') THEN $5::timestamptz ELSE finished_at END
       WHERE id = $1`,
      [run.id, to, extra.summary ? JSON.stringify(extra.summary) : null, extra.log_object_key ?? null, now],
    );
    run.status = to;
  }

  /** Job handler. Infrastructure failures retry; the final failure is recorded as UNKNOWN, never PASSED. */
  async handle(job: JobRow): Promise<void> {
    const run = await this.get(job.payload.testRunId);
    if (run.status !== 'QUEUED') return;
    const practice = await this.ctx.db.one<{ coverage: boolean }>('SELECT coverage FROM practices WHERE id = $1', [run.practice_id]);
    await this.setStatus(run, 'RUNNING');
    await this.events.append(this.ctx.db, run.practice_id, 'test_started', { runId: run.id, command: run.command.join(' ') });
    const workDir = path.join(this.ctx.config.dataDir, 'sandbox-work', run.id);
    let summary: TestRunSummary;
    let rawLog = '';
    let infraFailure: string | null = null;
    try {
      await rm(workDir, { recursive: true, force: true });
      await this.snapshots.materialize(run.snapshot_id!, workDir);
      await chmod(workDir, 0o755);
      const out = await this.driver.run({ runId: run.id, sourceDir: workDir, argv: run.command, policy: this.policy });
      rawLog = `${out.stdout}\n${out.stderr}`;
      if (out.infraError) throw new Error(out.infraError);
      const parsed = parseNodeTestOutput(out.stdout + '\n' + out.stderr, { coverageEnabled: !!practice?.coverage });
      const status = mapSandboxOutcome({ timedOut: out.timedOut, infraError: false, exitCode: out.exitCode, parsed });
      summary = {
        status,
        exitCode: out.exitCode,
        durationMs: parsed?.durationMs ?? out.durationMs,
        tests: parsed?.tests ?? 0,
        passed: parsed?.passed ?? 0,
        failed: parsed?.failed ?? 0,
        skipped: parsed?.skipped ?? 0,
        failedTests: parsed?.failedTests ?? [],
        coverage: parsed?.coverage ?? null,
        logTruncated: false,
        reason: out.timedOut ? `time limit of ${this.policy.timeoutSec}s exceeded` : parsed ? null : 'test output could not be parsed',
        driver: this.driver.name,
      };
    } catch (e) {
      const reason = (e instanceof Error ? e.message : String(e)).slice(0, 300);
      if (job.attempts < job.max_attempts && !(e instanceof PermanentJobError)) {
        await this.ctx.db.query(`UPDATE test_runs SET status = 'QUEUED' WHERE id = $1`, [run.id]);
        throw e;
      }
      infraFailure = reason;
      summary = { status: 'UNKNOWN', exitCode: null, durationMs: 0, tests: 0, passed: 0, failed: 0, skipped: 0, failedTests: [], coverage: null, logTruncated: false, reason: `sandbox failure: ${reason}`, driver: this.driver.name };
    } finally {
      await rm(workDir, { recursive: true, force: true });
    }
    const log = safeLog(rawLog || summary.reason || '', this.policy.maxLogBytes);
    summary.logTruncated = log.truncated;
    const logKey = `logs/${run.practice_id}/${run.id}.log`;
    await this.ctx.objects.put(logKey, Buffer.from(log.text, 'utf8'));
    await this.setStatus(run, summary.status, { summary, log_object_key: logKey });
    await this.events.append(this.ctx.db, run.practice_id, 'test_finished', {
      runId: run.id,
      command: run.command.join(' '),
      status: summary.status === 'QUEUED' || summary.status === 'RUNNING' ? 'UNKNOWN' : summary.status,
      exitCode: summary.exitCode,
      passed: summary.passed,
      failed: summary.failed,
      durationMs: summary.durationMs,
      safeLog: log.text.slice(0, 4000),
    });
    this.ctx.metrics.inc('sandbox_runs_total', { status: summary.status });
    // The run is recorded as UNKNOWN; the job is still dead-lettered so operators see the outage.
    if (infraFailure) throw new PermanentJobError(`sandbox infrastructure failure: ${infraFailure}`);
  }

  async listForPractice(practiceId: string): Promise<TestRunRow[]> {
    return this.ctx.db.query<TestRunRow>('SELECT * FROM test_runs WHERE practice_id = $1 ORDER BY created_at', [practiceId]);
  }
}
