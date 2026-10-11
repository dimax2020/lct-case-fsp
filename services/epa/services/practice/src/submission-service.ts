import { actorOf, authorize, type Principal } from '@epa/authz';
import { DomainError, notFound } from '@epa/domain';
import { newId, type Ctx, type Queryable } from '@epa/platform';
import type { PlatformEvents } from '@epa/timeline';
import type { PracticeService } from './practice-service.js';
import { scopeOf } from './practice-service.js';

export interface SubmissionRow {
  id: string;
  practice_id: string;
  snapshot_id: string;
  version: number;
  idempotency_key: string;
  commit_sha: string | null;
  baseline_submission_id: string | null;
  requirement_change_id: string | null;
  submitted_at: Date;
}

/** Ports implemented by other services; kept as interfaces to avoid hard coupling. */
export interface SubmissionPorts {
  snapshotWorkspace(practiceId: string, workspaceId: string): Promise<{ id: string }>;
  headSha(workspaceId: string): Promise<string | null>;
  enqueueSandbox(q: Queryable, input: { practiceId: string; snapshotId: string; submissionId: string; command: string[] }): Promise<string>;
  enqueueAnalysis(q: Queryable, input: { practiceId: string; submissionId: string }): Promise<string | null>;
}

export class SubmissionService {
  constructor(
    private readonly ctx: Ctx,
    private readonly practices: PracticeService,
    private readonly events: PlatformEvents,
    private readonly ports: SubmissionPorts,
  ) {}

  async get(id: string): Promise<SubmissionRow> {
    if (typeof id !== 'string' || id.length > 100) throw notFound('submission');
    const row = await this.ctx.db.one<SubmissionRow>('SELECT * FROM submissions WHERE id = $1', [id]);
    if (!row) throw notFound('submission');
    return row;
  }

  async list(practiceId: string): Promise<SubmissionRow[]> {
    return this.ctx.db.query<SubmissionRow>('SELECT * FROM submissions WHERE practice_id = $1 ORDER BY version', [practiceId]);
  }

  async latest(practiceId: string, q: Queryable = this.ctx.db): Promise<SubmissionRow | null> {
    return q.one<SubmissionRow>('SELECT * FROM submissions WHERE practice_id = $1 ORDER BY version DESC LIMIT 1', [practiceId]);
  }

  /**
   * Creates an immutable submission version. Idempotent per (practice, Idempotency-Key): a retry
   * returns the original submission. Later edits never touch an earlier snapshot.
   */
  async submit(principal: Principal | null, practiceId: string, idempotencyKey: string): Promise<{ submission: SubmissionRow; testRunId: string | null; created: boolean }> {
    this.requireIdempotencyKey(idempotencyKey);
    const practice = await this.practices.authorized(principal, 'practice:work', practiceId);
    const replay = await this.replay(practiceId, idempotencyKey);
    if (replay) return replay;
    await this.practices.assertWorkable(practiceId);
    const snapshot = await this.ports.snapshotWorkspace(practiceId, practice.workspace_id!);
    const commitSha = await this.ports.headSha(practice.workspace_id!);
    return this.finishSubmit(principal!, practiceId, idempotencyKey, snapshot.id, commitSha);
  }

  /** Submits an immutable snapshot uploaded by the VS Code extension, not the browser workspace. */
  async submitVscodeSnapshot(
    principal: Principal | null,
    practiceId: string,
    snapshotId: string,
    idempotencyKey: string,
  ): Promise<{ submission: SubmissionRow; testRunId: string | null; created: boolean }> {
    this.requireIdempotencyKey(idempotencyKey);
    if (!principal || principal.kind !== 'agent' || principal.practiceId !== practiceId) {
      throw new DomainError('FORBIDDEN', 'vscode agent credential required');
    }
    const session = await this.ctx.db.one<{ client: string; ended_at: Date | null }>('SELECT client, ended_at FROM dev_sessions WHERE id = $1', [principal.sessionId]);
    if (!session || session.client !== 'vscode' || session.ended_at) throw new DomainError('FORBIDDEN', 'vscode agent credential required');
    const snap = await this.ctx.db.one<{ practice_id: string }>('SELECT practice_id FROM snapshots WHERE id = $1 AND purged_at IS NULL', [snapshotId]);
    if (!snap || snap.practice_id !== practiceId) throw notFound('snapshot');
    const replay = await this.replay(practiceId, idempotencyKey);
    if (replay) return replay;
    await this.practices.assertWorkable(practiceId);
    return this.finishSubmit(principal, practiceId, idempotencyKey, snapshotId, null);
  }

  private requireIdempotencyKey(idempotencyKey: string) {
    if (!/^[A-Za-z0-9_-]{8,100}$/.test(idempotencyKey ?? '')) throw new DomainError('VALIDATION', 'Idempotency-Key header (8-100 chars) is required');
  }

  private async replay(practiceId: string, idempotencyKey: string): Promise<{ submission: SubmissionRow; testRunId: string | null; created: boolean } | null> {
    const existing = await this.ctx.db.one<SubmissionRow>('SELECT * FROM submissions WHERE practice_id = $1 AND idempotency_key = $2', [practiceId, idempotencyKey]);
    if (!existing) return null;
    const tr = await this.ctx.db.one<{ id: string }>(`SELECT id FROM test_runs WHERE submission_id = $1 AND origin = 'sandbox' ORDER BY created_at LIMIT 1`, [existing.id]);
    return { submission: existing, testRunId: tr?.id ?? null, created: false };
  }

  private async finishSubmit(
    principal: Principal,
    practiceId: string,
    idempotencyKey: string,
    snapshotId: string,
    commitSha: string | null,
  ): Promise<{ submission: SubmissionRow; testRunId: string | null; created: boolean }> {
    return this.ctx.db.tx(async (tx) => {
      const p = await this.practices.load(practiceId, tx, true);
      const dup = await tx.one<SubmissionRow>('SELECT * FROM submissions WHERE practice_id = $1 AND idempotency_key = $2', [practiceId, idempotencyKey]);
      if (dup) return { submission: dup, testRunId: null, created: false };
      if (p.status !== 'IN_PROGRESS') throw new DomainError('CONFLICT', `practice is ${p.status}`);
      const prev = await this.latest(practiceId, tx);
      const openChange = await tx.one<{ id: string }>(
        'SELECT id FROM requirement_changes WHERE practice_id = $1 AND revised_submission_id IS NULL ORDER BY created_at DESC LIMIT 1',
        [practiceId],
      );
      const id = newId('sub');
      const submission = (await tx.one<SubmissionRow>(
        `INSERT INTO submissions (id, practice_id, snapshot_id, version, idempotency_key, commit_sha, baseline_submission_id, requirement_change_id, submitted_at)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *`,
        [id, practiceId, snapshotId, (prev?.version ?? 0) + 1, idempotencyKey, commitSha, prev?.id ?? null, openChange?.id ?? null, this.ctx.clock.now()],
      ))!;
      if (openChange) await tx.query('UPDATE requirement_changes SET revised_submission_id = $2 WHERE id = $1', [openChange.id, id]);
      await this.practices.transition(tx, practiceId, 'SUBMITTED', actorOf(principal), { submissionId: id, version: submission.version });
      await this.events.append(tx, practiceId, 'submit_created', { submissionId: id, version: submission.version, snapshotId });
      await this.ctx.audit.append(tx, {
        ...{ actorKind: principal.kind, actorId: principal.id },
        action: 'submission.created',
        entityType: 'submission',
        entityId: id,
        organisationId: p.organisation_id,
        practiceId,
        detail: { version: submission.version, snapshotId, commitSha },
      });
      const testRunId = await this.ports.enqueueSandbox(tx, { practiceId, snapshotId, submissionId: id, command: p.test_command });
      await this.ports.enqueueAnalysis(tx, { practiceId, submissionId: id });
      return { submission, testRunId, created: true };
    });
  }

  async authorizedSubmission(principal: Principal | null, action: Parameters<typeof authorize>[1], submissionId: string) {
    const submission = await this.get(submissionId);
    const practice = await this.practices.load(submission.practice_id);
    authorize(principal, action, scopeOf(practice));
    return { submission, practice };
  }
}
