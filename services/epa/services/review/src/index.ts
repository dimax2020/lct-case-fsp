import { actorOf, authorize, requireKind, type Principal } from '@epa/authz';
import {
  DomainError,
  assertCommentRange,
  assertCommentTransition,
  assertValidRequirementChange,
  notFound,
  renderSafeMarkdown,
  stripControlChars,
  type CommentStatus,
} from '@epa/domain';
import { newId, type Ctx } from '@epa/platform';
import { scopeOf, type PracticeService, type SubmissionService } from '@epa/practice';
import type { SnapshotService } from '@epa/snapshots';
import type { PlatformEvents } from '@epa/timeline';

export interface CommentRow {
  id: string;
  practice_id: string;
  submission_id: string;
  author_kind: string;
  author_id: string;
  file_path: string;
  line_start: number;
  line_end: number;
  body: string;
  status: CommentStatus;
  resolved_by_kind: string | null;
  resolved_by_id: string | null;
  resolved_at: Date | null;
  created_at: Date;
}

export interface RequirementChangeRow {
  id: string;
  practice_id: string;
  baseline_submission_id: string;
  text: string;
  reason: string;
  acceptance_criteria: string[];
  due_at: Date;
  created_by_kind: string;
  created_by_id: string;
  revised_submission_id: string | null;
  created_at: Date;
}

export const presentComment = (c: CommentRow) => ({
  id: c.id,
  submissionId: c.submission_id,
  filePath: c.file_path,
  lineStart: c.line_start,
  lineEnd: c.line_end,
  body: c.body,
  bodyHtml: renderSafeMarkdown(c.body),
  status: c.status,
  author: { kind: c.author_kind, id: c.author_id },
  resolvedBy: c.resolved_by_id ? { kind: c.resolved_by_kind, id: c.resolved_by_id } : null,
  resolvedAt: c.resolved_at,
  createdAt: c.created_at,
});

export class ReviewService {
  constructor(
    private readonly ctx: Ctx,
    private readonly practices: PracticeService,
    private readonly submissions: SubmissionService,
    private readonly snapshots: SnapshotService,
    private readonly events: PlatformEvents,
  ) {}

  async startReview(principal: Principal | null, practiceId: string) {
    const practice = await this.practices.authorized(principal, 'practice:review', practiceId);
    const latest = await this.submissions.latest(practiceId);
    if (!latest) throw new DomainError('CONFLICT', 'no submission to review');
    return this.ctx.db.tx(async (tx) => {
      const p = await this.practices.transition(tx, practice.id, 'REVIEW', actorOf(principal!), { submissionId: latest.id });
      await tx.query(`INSERT INTO review_decisions (id, practice_id, submission_id, employer_id, decision, created_at) VALUES ($1,$2,$3,$4,'START_REVIEW',$5)`, [
        newId('rvd'),
        practiceId,
        latest.id,
        principal!.id,
        this.ctx.clock.now(),
      ]);
      return p;
    });
  }

  /** Line comment on a specific submission version; the range is validated against that immutable snapshot. */
  async addComment(principal: Principal | null, submissionId: string, input: { filePath: string; lineStart: number; lineEnd: number; body: string }) {
    const { submission, practice } = await this.submissions.authorizedSubmission(principal, 'practice:review', submissionId);
    if (practice.status !== 'SUBMITTED' && practice.status !== 'REVIEW') throw new DomainError('CONFLICT', `cannot comment while practice is ${practice.status}`);
    const content = await this.snapshots.readFile(submission.snapshot_id, input.filePath);
    const lineCount = content.toString('utf8').split('\n').length;
    assertCommentRange({ lineStart: input.lineStart, lineEnd: input.lineEnd, fileLineCount: lineCount });
    const body = stripControlChars(input.body).trim();
    if (!body) throw new DomainError('VALIDATION', 'comment body is empty');
    const id = newId('cmt');
    return this.ctx.db.tx(async (tx) => {
      const row = await tx.one<CommentRow>(
        `INSERT INTO review_comments (id, practice_id, submission_id, author_kind, author_id, file_path, line_start, line_end, body, status, created_at)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'OPEN',$10) RETURNING *`,
        [id, practice.id, submission.id, principal!.kind, principal!.id, input.filePath, input.lineStart, input.lineEnd, body, this.ctx.clock.now()],
      );
      await this.ctx.audit.append(tx, {
        actorKind: principal!.kind,
        actorId: principal!.id,
        action: 'review.comment_created',
        entityType: 'review_comment',
        entityId: id,
        organisationId: practice.organisation_id,
        practiceId: practice.id,
        detail: { submissionId, filePath: input.filePath, lineStart: input.lineStart, lineEnd: input.lineEnd },
      });
      return presentComment(row!);
    });
  }

  async listComments(principal: Principal | null, practiceId: string) {
    await this.practices.authorized(principal, 'practice:timeline', practiceId);
    const rows = await this.ctx.db.query<CommentRow>('SELECT * FROM review_comments WHERE practice_id = $1 ORDER BY created_at', [practiceId]);
    return rows.map(presentComment);
  }

  /** Resolution is attributed to the authenticated principal, never to a client-supplied actor. */
  async resolve(principal: Principal | null, commentId: string) {
    if (typeof commentId !== 'string' || commentId.length > 100) throw notFound('comment');
    const c = await this.ctx.db.one<CommentRow>('SELECT * FROM review_comments WHERE id = $1', [commentId]);
    if (!c) throw notFound('comment');
    const practice = await this.practices.load(c.practice_id);
    authorize(principal, 'comment:resolve', scopeOf(practice));
    assertCommentTransition(c.status, 'RESOLVED');
    return this.ctx.db.tx(async (tx) => {
      const row = await tx.one<CommentRow>(
        `UPDATE review_comments SET status = 'RESOLVED', resolved_by_kind = $2, resolved_by_id = $3, resolved_at = $4 WHERE id = $1 AND status = 'OPEN' RETURNING *`,
        [commentId, principal!.kind, principal!.id, this.ctx.clock.now()],
      );
      if (!row) throw new DomainError('CONFLICT', 'comment already resolved');
      await this.ctx.audit.append(tx, {
        actorKind: principal!.kind,
        actorId: principal!.id,
        action: 'review.comment_resolved',
        entityType: 'review_comment',
        entityId: commentId,
        organisationId: practice.organisation_id,
        practiceId: practice.id,
      });
      return presentComment(row);
    });
  }

  async requestChanges(principal: Principal | null, practiceId: string) {
    const practice = await this.practices.authorized(principal, 'practice:review', practiceId);
    const latest = await this.submissions.latest(practiceId);
    if (!latest) throw new DomainError('CONFLICT', 'no submission');
    return this.ctx.db.tx(async (tx) => {
      const p = await this.practices.transition(tx, practice.id, 'IN_PROGRESS', actorOf(principal!), { reason: 'changes_requested', submissionId: latest.id });
      const open = await tx.one<{ n: number }>(`SELECT count(*)::int AS n FROM review_comments WHERE submission_id = $1 AND status = 'OPEN'`, [latest.id]);
      await tx.query(`INSERT INTO review_decisions (id, practice_id, submission_id, employer_id, decision, created_at) VALUES ($1,$2,$3,$4,'REQUEST_CHANGES',$5)`, [
        newId('rvd'),
        practiceId,
        latest.id,
        principal!.id,
        this.ctx.clock.now(),
      ]);
      await this.events.append(tx, practiceId, 'review_requested', { submissionId: latest.id, openComments: open!.n });
      return p;
    });
  }

  /** Requirement change after initial review; the practice returns to IN_PROGRESS for adaptation. */
  async createRequirementChange(principal: Principal | null, practiceId: string, input: { text: string; reason: string; acceptanceCriteria: string[]; dueAt: string }) {
    const emp = requireKind(principal, 'employer');
    const practice = await this.practices.authorized(emp, 'practice:review', practiceId);
    if (practice.status !== 'REVIEW') throw new DomainError('CONFLICT', 'requirement changes are created during review');
    const dueAt = new Date(input.dueAt);
    assertValidRequirementChange({ ...input, dueAt }, this.ctx.clock.now());
    if (dueAt.getTime() > new Date(practice.deadline).getTime()) throw new DomainError('VALIDATION', 'due date must not exceed the practice deadline');
    const baseline = await this.submissions.latest(practiceId);
    if (!baseline) throw new DomainError('CONFLICT', 'no baseline submission');
    const pending = await this.ctx.db.one('SELECT id FROM requirement_changes WHERE practice_id = $1 AND revised_submission_id IS NULL', [practiceId]);
    if (pending) throw new DomainError('CONFLICT', 'a requirement change is already pending');
    return this.ctx.db.tx(async (tx) => {
      const id = newId('rc');
      const row = await tx.one<RequirementChangeRow>(
        `INSERT INTO requirement_changes (id, practice_id, baseline_submission_id, text, reason, acceptance_criteria, due_at, created_by_kind, created_by_id, created_at)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *`,
        [id, practiceId, baseline.id, stripControlChars(input.text), stripControlChars(input.reason), JSON.stringify(input.acceptanceCriteria.map((c) => stripControlChars(c.trim()))), dueAt, emp.kind, emp.id, this.ctx.clock.now()],
      );
      await this.practices.transition(tx, practiceId, 'IN_PROGRESS', actorOf(emp), { reason: 'requirement_changed', requirementChangeId: id });
      await this.events.append(tx, practiceId, 'requirement_changed', { requirementChangeId: id, baselineSubmissionId: baseline.id });
      await this.ctx.audit.append(tx, {
        actorKind: emp.kind,
        actorId: emp.id,
        action: 'requirement_change.created',
        entityType: 'requirement_change',
        entityId: id,
        organisationId: practice.organisation_id,
        practiceId,
      });
      return row!;
    });
  }

  async listRequirementChanges(principal: Principal | null, practiceId: string) {
    await this.practices.authorized(principal, 'practice:timeline', practiceId);
    return this.ctx.db.query<RequirementChangeRow>('SELECT * FROM requirement_changes WHERE practice_id = $1 ORDER BY created_at', [practiceId]);
  }

  async complete(principal: Principal | null, practiceId: string) {
    const practice = await this.practices.authorized(principal, 'practice:review', practiceId);
    const latest = await this.submissions.latest(practiceId);
    return this.ctx.db.tx(async (tx) => {
      const p = await this.practices.transition(tx, practice.id, 'COMPLETED', actorOf(principal!), {});
      if (latest) {
        await tx.query(`INSERT INTO review_decisions (id, practice_id, submission_id, employer_id, decision, created_at) VALUES ($1,$2,$3,$4,'APPROVE',$5)`, [
          newId('rvd'),
          practiceId,
          latest.id,
          principal!.id,
          this.ctx.clock.now(),
        ]);
      }
      return p;
    });
  }
}
