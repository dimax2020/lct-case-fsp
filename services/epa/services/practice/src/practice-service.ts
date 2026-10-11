import { authorize, requireKind, actorOf, type Principal, type PracticeScope } from '@epa/authz';
import type { CreatePracticeReq } from '@epa/contracts';
import {
  CONSENT_VERSION,
  DomainError,
  assertCanStart,
  assertTransition,
  buildSnapshotPolicy,
  buildWorkspacePolicy,
  consentNotice,
  isTerminal,
  notFound,
  retentionDeadline,
  shouldExpire,
  type PracticeStatus,
  type WorkspacePolicy,
} from '@epa/domain';
import { hashToken, newId, newSecretToken, type Ctx, type Queryable } from '@epa/platform';
import { normalizeName, type AuthService } from './auth.js';
import type { TemplateCatalog } from './templates.js';

export interface PracticeRow {
  id: string;
  organisation_id: string;
  employer_id: string;
  candidate_id: string | null;
  title: string;
  description: string;
  rules: string;
  template: string;
  task_version: string;
  test_command: string[];
  coverage: boolean;
  snapshot_policy: Record<string, number>;
  workspace_policy: Record<string, unknown>;
  status: PracticeStatus;
  deadline: Date;
  workspace_id: string | null;
  consent_id: string | null;
  terminal_at: Date | null;
  purged_at: Date | null;
  brief: string | null;
  brief_filename: string | null;
  employer_notes: string | null;
  project_source: 'template' | 'upload';
  vacancy_id: string | null;
  source_practice_id: string | null;
  created_at: Date;
  updated_at: Date;
}

export const scopeOf = (p: PracticeRow): PracticeScope => ({
  practiceId: p.id,
  organisationId: p.organisation_id,
  candidateId: p.candidate_id,
});

const CANDIDATE_TOKEN_TTL_MS = 30 * 86_400_000;

function cleanVacancyId(raw: string): string | null {
  const id = raw.trim();
  if (!id) return null;
  if (!/^[0-9a-fA-F-]{8,80}$/.test(id)) throw new DomainError('VALIDATION', 'некорректная вакансия');
  return id;
}

function jsonValue(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value ?? null);
}

function cleanBriefName(name: string): string {
  const base = name.replace(/\\/g, '/').split('/').pop()?.replace(/[\u0000-\u001f]/g, '').trim() ?? '';
  if (!base || base === '.' || base === '..' || base.length > 200) throw new DomainError('VALIDATION', 'некорректное имя файла ТЗ');
  return base;
}

export class PracticeService {
  constructor(
    private readonly ctx: Ctx,
    private readonly auth: AuthService,
    private readonly templates: TemplateCatalog,
  ) {}

  async load(practiceId: string, q: Queryable = this.ctx.db, forUpdate = false): Promise<PracticeRow> {
    if (typeof practiceId !== 'string' || practiceId.length > 100) throw notFound('practice');
    const row = await q.one<PracticeRow>(`SELECT * FROM practices WHERE id = $1${forUpdate ? ' FOR UPDATE' : ''}`, [practiceId]);
    if (!row) throw notFound('practice');
    return row;
  }

  /** Loads a practice and authorises the principal for the given action against its stored scope. */
  async authorized(principal: Principal | null, action: Parameters<typeof authorize>[1], practiceId: string): Promise<PracticeRow> {
    const row = await this.load(practiceId);
    authorize(principal, action, scopeOf(row));
    return row;
  }

  /** Server-side status transition with row lock, validation and audit. */
  async transition(q: Queryable, practiceId: string, to: PracticeStatus, actor: { actorType: string; actorId: string }, detail: Record<string, unknown> = {}): Promise<PracticeRow> {
    const p = await this.load(practiceId, q, true);
    assertTransition(p.status, to);
    const now = this.ctx.clock.now();
    const terminalAt = isTerminal(to) ? now : null;
    const updated = await q.one<PracticeRow>(
      `UPDATE practices SET status = $2, updated_at = $3, terminal_at = COALESCE($4, terminal_at) WHERE id = $1 RETURNING *`,
      [practiceId, to, now, terminalAt],
    );
    await this.ctx.audit.append(q, {
      actorKind: actor.actorType,
      actorId: actor.actorId,
      action: 'practice.status_changed',
      entityType: 'practice',
      entityId: practiceId,
      organisationId: p.organisation_id,
      practiceId,
      detail: { from: p.status, to, ...detail },
    });
    this.ctx.metrics.inc('practice_transitions_total', { from: p.status, to });
    if (isTerminal(to)) {
      await this.ctx.jobs.enqueue('workspace.teardown', { practiceId, reason: to }, { dedupeKey: `teardown:${practiceId}` }, q);
    }
    return updated!;
  }

  // ---------- Employer ----------

  async create(principal: Principal | null, req: CreatePracticeReq): Promise<PracticeRow> {
    const emp = requireKind(principal, 'employer');
    const template = await this.templates.get(req.template || 'blank');
    const deadline = new Date(req.deadline);
    const now = this.ctx.clock.now();
    if (deadline.getTime() <= now.getTime()) throw new DomainError('VALIDATION', 'deadline must be in the future');
    const snapshotPolicy = buildSnapshotPolicy(req.snapshotPolicy ?? {});
    const workspacePolicy = buildWorkspacePolicy(req.workspacePolicy ?? {});
    return this.ctx.db.tx(async (tx) => {
      const id = newId('prc');
      const row = await tx.one<PracticeRow>(
        `INSERT INTO practices (id, organisation_id, employer_id, title, description, rules, template, task_version, test_command, coverage,
           snapshot_policy, workspace_policy, status, deadline, created_at, updated_at)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'INVITED',$13,$14,$14) RETURNING *`,
        [
          id,
          emp.organisationId,
          emp.id,
          req.title,
          req.description,
          req.rules ?? '',
          template.name,
          template.version,
          JSON.stringify(req.testCommand ?? template.testCommand),
          req.coverage || template.coverage,
          JSON.stringify(snapshotPolicy),
          JSON.stringify(workspacePolicy),
          deadline,
          now,
        ],
      );
      await this.ctx.audit.append(tx, {
        ...auditActor(emp),
        action: 'practice.created',
        entityType: 'practice',
        entityId: id,
        organisationId: emp.organisationId,
        practiceId: id,
        detail: { template: template.version },
      });
      return row!;
    });
  }

  async list(principal: Principal | null, cursor: string | undefined, limit: number): Promise<{ items: PracticeRow[]; nextCursor: string | null }> {
    if (!principal) throw new DomainError('UNAUTHENTICATED', 'authentication required');
    const c = cursor ? decodeCursor(cursor) : null;
    let rows: PracticeRow[];
    const params: unknown[] = [];
    let where: string;
    if (principal.kind === 'employer' || principal.kind === 'auditor') {
      params.push(principal.organisationId);
      where = 'organisation_id = $1 AND source_practice_id IS NULL';
    } else if (principal.kind === 'candidate') {
      params.push(principal.id);
      where = 'candidate_id = $1';
    } else {
      throw new DomainError('FORBIDDEN', 'not allowed');
    }
    if (c) {
      params.push(new Date(c.t), c.id);
      where += ` AND (created_at, id) < ($${params.length - 1}, $${params.length})`;
    }
    params.push(limit + 1);
    rows = await this.ctx.db.query<PracticeRow>(`SELECT * FROM practices WHERE ${where} ORDER BY created_at DESC, id DESC LIMIT $${params.length}`, params);
    const more = rows.length > limit;
    rows = rows.slice(0, limit);
    const last = rows[rows.length - 1];
    return { items: rows, nextCursor: more && last ? encodeCursor({ t: new Date(last.created_at).toISOString(), id: last.id }) : null };
  }

  /** Replaces the vacancies pinned to this task. One task can cover several vacancies. */
  async attachVacancy(principal: Principal | null, practiceId: string, vacancyIds: string[]): Promise<PracticeRow> {
    const p = await this.authorized(principal, 'practice:invite', practiceId);
    if (p.source_practice_id) throw new DomainError('CONFLICT', 'вакансия задаётся у задания, а не у выполнения кандидата');
    const ids = [...new Set(vacancyIds.map((id) => cleanVacancyId(id)).filter((id): id is string => !!id))].slice(0, 30);
    const now = this.ctx.clock.now();
    await this.ctx.db.tx(async (tx) => {
      await tx.query(`DELETE FROM practice_vacancies WHERE practice_id = $1`, [p.id]);
      for (const id of ids) {
        await tx.query(`DELETE FROM practice_vacancies WHERE vacancy_id = $1`, [id]);
        await tx.query(`INSERT INTO practice_vacancies (practice_id, vacancy_id) VALUES ($1, $2)`, [p.id, id]);
        await tx.query(
          `UPDATE practices SET vacancy_id = NULL, updated_at = $2
           WHERE organisation_id = $3 AND vacancy_id = $1 AND source_practice_id IS NULL AND id <> $4`,
          [id, now, p.organisation_id, p.id],
        );
      }
      await tx.query(`UPDATE practices SET vacancy_id = $2, updated_at = $3 WHERE id = $1`, [p.id, ids[0] ?? null, now]);
    });
    return this.load(practiceId);
  }

  async vacancyMap(practiceIds: string[]): Promise<Map<string, string[]>> {
    const ids = [...new Set(practiceIds.filter(Boolean))];
    const map = new Map<string, string[]>();
    if (!ids.length) return map;
    const rows = await this.ctx.db.query<{ practice_id: string; vacancy_id: string }>(
      `SELECT practice_id, vacancy_id FROM practice_vacancies WHERE practice_id IN (${ids.map((_, i) => `$${i + 1}`).join(',')}) ORDER BY vacancy_id`,
      ids,
    );
    for (const row of rows) {
      const list = map.get(row.practice_id) ?? [];
      list.push(row.vacancy_id);
      map.set(row.practice_id, list);
    }
    return map;
  }

  /** Vacancy ids from the given list that already have a test task pinned. */
  async vacanciesWithTasks(vacancyIds: string[]): Promise<string[]> {
    const ids = [...new Set(vacancyIds.map((id) => id.trim()).filter((id) => /^[0-9a-fA-F-]{8,80}$/.test(id)))].slice(0, 50);
    if (!ids.length) return [];
    const rows = await this.ctx.db.query<{ vacancy_id: string }>(
      `SELECT DISTINCT vacancy_id FROM practice_vacancies WHERE vacancy_id IN (${ids.map((_, i) => `$${i + 1}`).join(',')})`,
      ids,
    );
    return rows.map((row) => row.vacancy_id).filter((id): id is string => !!id);
  }

  /** Candidate copies created when someone applies to the vacancy of this task. */
  async attempts(principal: Principal | null, practiceId: string): Promise<PracticeRow[]> {
    await this.authorized(principal, 'practice:read', practiceId);
    return this.ctx.db.query<PracticeRow>(
      `SELECT * FROM practices WHERE source_practice_id = $1 ORDER BY created_at DESC, id DESC`,
      [practiceId],
    );
  }

  /**
   * Opens the task attached to a vacancy for the candidate who applied.
   * The same candidate gets the same copy on the next visit.
   */
  async joinVacancy(principal: Principal | null, vacancyId: string): Promise<{ practice: PracticeRow; copyRepoFrom: string | null }> {
    const cand = requireKind(principal, 'candidate');
    const id = cleanVacancyId(vacancyId);
    if (!id) throw new DomainError('VALIDATION', 'укажите вакансию');
    const template = await this.ctx.db.one<PracticeRow>(
      `SELECT p.* FROM practices p
       JOIN practice_vacancies v ON v.practice_id = p.id
       WHERE v.vacancy_id = $1 AND p.source_practice_id IS NULL
       ORDER BY p.updated_at DESC LIMIT 1`,
      [id],
    );
    if (!template) throw new DomainError('NOT_FOUND', 'к этой вакансии ещё не прикрепили тестовое задание');
    const existing = await this.ctx.db.one<PracticeRow>(
      `SELECT * FROM practices WHERE source_practice_id = $1 AND candidate_id = $2`,
      [template.id, cand.id],
    );
    if (existing) return { practice: existing, copyRepoFrom: null };
    const now = this.ctx.clock.now();
    const practiceId = newId('prc');
    const row = await this.ctx.db.one<PracticeRow>(
      `INSERT INTO practices (
         id, organisation_id, employer_id, candidate_id, title, description, rules, template, task_version,
         test_command, coverage, snapshot_policy, workspace_policy, status, deadline, brief, brief_filename,
         project_source, vacancy_id, source_practice_id, created_at, updated_at
       ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,'INVITED',$14,$15,$16,$17,$18,$19,$20,$20)
       RETURNING *`,
      [
        practiceId,
        template.organisation_id,
        template.employer_id,
        cand.id,
        template.title,
        template.description,
        template.rules ?? '',
        template.template,
        template.task_version,
        jsonValue(template.test_command),
        template.coverage,
        jsonValue(template.snapshot_policy),
        jsonValue(template.workspace_policy),
        new Date(template.deadline),
        template.brief,
        template.brief_filename,
        template.project_source ?? 'template',
        id,
        template.id,
        now,
      ],
    );
    return { practice: row!, copyRepoFrom: template.id };
  }

  async createInvitation(principal: Principal | null, practiceId: string, input: { candidateEmail?: string; expiresInHours: number }) {
    const practice = await this.authorized(principal, 'practice:invite', practiceId);
    if (practice.status !== 'INVITED' || practice.candidate_id) {
      throw new DomainError('CONFLICT', 'practice already has a candidate or is not in INVITED state');
    }
    const token = newSecretToken();
    const now = this.ctx.clock.now();
    const expiresAt = new Date(Math.min(now.getTime() + input.expiresInHours * 3_600_000, new Date(practice.deadline).getTime()));
    const id = newId('inv');
    const email = input.candidateEmail?.trim().toLowerCase() || '';
    await this.ctx.db.tx(async (tx) => {
      await tx.query(
        `INSERT INTO invitations (id, practice_id, candidate_email, token_hash, expires_at, created_at) VALUES ($1,$2,$3,$4,$5,$6)`,
        [id, practiceId, email, hashToken(token), expiresAt, now],
      );
      await this.ctx.audit.append(tx, {
        ...auditActor(principal!),
        action: 'invitation.created',
        entityType: 'invitation',
        entityId: id,
        organisationId: practice.organisation_id,
        practiceId,
        detail: { expiresAt: expiresAt.toISOString() },
      });
    });
    return { invitationId: id, token, expiresAt, invitePath: `/candidate.html#invite=${token}` };
  }

  async setMaterials(
    principal: Principal | null,
    practiceId: string,
    input: { title?: string; description?: string; notes?: string },
  ): Promise<PracticeRow> {
    const p = await this.authorized(principal, 'practice:invite', practiceId);
    this.assertEditable(p);
    const notes = input.notes === undefined ? p.employer_notes : input.notes.trim() || null;
    await this.ctx.db.query(
      'UPDATE practices SET title = $2, description = $3, employer_notes = $4, updated_at = $5 WHERE id = $1',
      [practiceId, input.title ?? p.title, input.description ?? p.description, notes, this.ctx.clock.now()],
    );
    return this.load(practiceId);
  }

  async setBrief(principal: Principal | null, practiceId: string, text: string, name?: string): Promise<void> {
    const p = await this.authorized(principal, 'practice:invite', practiceId);
    this.assertEditable(p);
    const now = this.ctx.clock.now();
    if (name === undefined) {
      await this.ctx.db.query('UPDATE practices SET brief = $2, updated_at = $3 WHERE id = $1', [practiceId, text, now]);
      return;
    }
    await this.ctx.db.query('UPDATE practices SET brief = $2, brief_filename = $3, updated_at = $4 WHERE id = $1', [practiceId, text, cleanBriefName(name), now]);
  }

  async markProjectUploaded(principal: Principal | null, practiceId: string): Promise<PracticeRow> {
    const p = await this.authorized(principal, 'practice:invite', practiceId);
    this.assertEditable(p);
    await this.ctx.db.query(`UPDATE practices SET project_source = 'upload', updated_at = $2 WHERE id = $1`, [practiceId, this.ctx.clock.now()]);
    return this.load(practiceId);
  }

  /** Candidate who is doing the practice, or the email from the latest invitation. */
  async people(rows: PracticeRow[]): Promise<Map<string, { candidateEmail: string | null; invitedEmail: string | null; invited: boolean }>> {
    const out = new Map<string, { candidateEmail: string | null; invitedEmail: string | null; invited: boolean }>();
    if (rows.length === 0) return out;
    const candidateIds = [...new Set(rows.map((r) => r.candidate_id).filter((id): id is string => !!id))];
    const emails = new Map<string, string>();
    if (candidateIds.length) {
      const people = await this.ctx.db.query<{ id: string; identity: string }>(
        `SELECT id, identity FROM candidates WHERE id IN (${candidateIds.map((_, i) => `$${i + 1}`).join(',')})`,
        candidateIds,
      );
      for (const person of people) emails.set(person.id, person.identity);
    }
    const practiceIds = rows.map((r) => r.id);
    const invites = await this.ctx.db.query<{ practice_id: string; candidate_email: string }>(
      `SELECT DISTINCT ON (practice_id) practice_id, candidate_email FROM invitations
       WHERE practice_id IN (${practiceIds.map((_, i) => `$${i + 1}`).join(',')})
       ORDER BY practice_id, created_at DESC`,
      practiceIds,
    );
    const invited = new Map(invites.map((i) => [i.practice_id, i.candidate_email]));
    for (const row of rows) {
      const invitedEmail = invited.get(row.id) ?? null;
      out.set(row.id, {
        candidateEmail: row.candidate_id ? emails.get(row.candidate_id) ?? null : null,
        invitedEmail: invitedEmail || null,
        invited: invited.has(row.id),
      });
    }
    return out;
  }

  /** Removes a practice and everything stored for it. The caller tears down the workspace and git repo. */
  async purge(principal: Principal | null, practiceId: string): Promise<void> {
    await this.authorized(principal, 'practice:invite', practiceId);
    await this.ctx.db.tx(async (tx) => {
      await tx.query(`SELECT set_config('epa.retention_purge', 'on', true)`);
      await tx.query(
        `DELETE FROM interview_answers WHERE question_id IN (SELECT id FROM interview_questions WHERE practice_id = $1)`,
        [practiceId],
      );
      await tx.query(`UPDATE interview_questions SET parent_question_id = NULL WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM interview_questions WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM review_comments WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM review_decisions WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM requirement_changes WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM test_runs WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM git_commits WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM assessments WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM ai_analyses WHERE practice_id = $1`, [practiceId]);
      await tx.query(`UPDATE submissions SET baseline_submission_id = NULL, requirement_change_id = NULL WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM submissions WHERE practice_id = $1`, [practiceId]);
      await tx.query(`UPDATE snapshots SET base_snapshot_id = NULL WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM snapshots WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM telemetry_events WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM telemetry_diagnostics WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM dev_sessions WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM invitations WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM consents WHERE practice_id = $1`, [practiceId]);
      await tx.query(`UPDATE practices SET workspace_id = NULL, consent_id = NULL WHERE id = $1`, [practiceId]);
      await tx.query(`DELETE FROM workspaces WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM jobs WHERE payload->>'practiceId' = $1`, [practiceId]);
      await tx.query(`DELETE FROM practice_vacancies WHERE practice_id = $1`, [practiceId]);
      await tx.query(`DELETE FROM practices WHERE id = $1`, [practiceId]);
    });
  }

  private assertEditable(p: PracticeRow): void {
    if (p.status === 'COMPLETED' || p.status === 'EXPIRED' || p.purged_at) {
      throw new DomainError('CONFLICT', 'задание уже закрыто, проект заменить нельзя');
    }
  }

  /** Shows the invited email without consuming the link. */
  async previewInvitation(token: string) {
    if (!token || token.length < 20) throw notFound('invitation');
    const row = await this.ctx.db.one<{ candidate_email: string; expires_at: Date; consumed_at: Date | null; title: string; practice_id: string }>(
      `SELECT i.candidate_email, i.expires_at, i.consumed_at, p.title, p.id AS practice_id
       FROM invitations i JOIN practices p ON p.id = i.practice_id WHERE i.token_hash = $1`,
      [hashToken(token)],
    );
    if (!row) throw notFound('invitation');
    if (row.consumed_at || new Date(row.expires_at).getTime() <= this.ctx.clock.now().getTime()) {
      throw new DomainError('GONE', 'invitation already used or expired');
    }
    return { email: row.candidate_email || null, title: row.title, practiceId: row.practice_id };
  }

  /** Consumes the invite, stores the display name, and the login used by the VS Code extension. */
  async registerFromInvite(token: string, name: string, username: string, password: string) {
    const taken = await this.ctx.db.one('SELECT id FROM candidates WHERE lower(username) = lower($1)', [username.trim()]);
    if (taken) throw new DomainError('CONFLICT', 'этот логин уже занят');
    const session = await this.redeemInvitation(token, normalizeName(name));
    await this.auth.setExtensionCredentials(session.candidateId, username, password);
    return session;
  }

  // ---------- Candidate ----------

  /** Atomically consumes a one-time invitation and returns a candidate credential. */
  async redeemInvitation(token: string, identity?: string) {
    const now = this.ctx.clock.now();
    const tokenHash = hashToken(token);
    return this.ctx.db.tx(async (tx) => {
      const candidateId = newId('cand');
      const inv = await tx.one<{ id: string; practice_id: string; candidate_email: string }>(
        `UPDATE invitations SET consumed_at = $2, consumed_by = $3
         WHERE token_hash = $1 AND consumed_at IS NULL AND expires_at > $2 RETURNING id, practice_id, candidate_email`,
        [tokenHash, now, candidateId],
      );
      if (!inv) {
        const exists = await tx.one('SELECT 1 AS x FROM invitations WHERE token_hash = $1', [tokenHash]);
        throw exists ? new DomainError('GONE', 'invitation already used or expired') : notFound('invitation');
      }
      const practice = await this.load(inv.practice_id, tx, true);
      if (practice.candidate_id || practice.status !== 'INVITED') throw new DomainError('GONE', 'invitation no longer valid');
      if (shouldExpire(practice.status, new Date(practice.deadline), now)) throw new DomainError('EXPIRED', 'practice deadline has passed');
      const display = (identity ?? inv.candidate_email).trim();
      if (!display) throw new DomainError('VALIDATION', 'укажите имя');
      await tx.query('INSERT INTO candidates (id, identity, created_at) VALUES ($1,$2,$3)', [candidateId, display, now]);
      await tx.query('UPDATE practices SET candidate_id = $2, updated_at = $3 WHERE id = $1', [practice.id, candidateId, now]);
      const cred = await this.auth.issue(tx, { kind: 'candidate', principalId: candidateId, ttlMs: CANDIDATE_TOKEN_TTL_MS, scope: { practiceId: practice.id } });
      await this.ctx.audit.append(tx, {
        actorKind: 'candidate',
        actorId: candidateId,
        action: 'invitation.redeemed',
        entityType: 'invitation',
        entityId: inv.id,
        organisationId: practice.organisation_id,
        practiceId: practice.id,
      });
      const org = await tx.one<{ retention_days: number }>('SELECT retention_days FROM organisations WHERE id = $1', [practice.organisation_id]);
      return {
        candidateId,
        candidateToken: cred.token,
        practiceId: practice.id,
        consentNotice: consentNotice(org!.retention_days),
      };
    });
  }

  async getConsentNotice(principal: Principal | null, practiceId: string) {
    const p = await this.authorized(principal, 'practice:read', practiceId);
    const org = await this.ctx.db.one<{ retention_days: number }>('SELECT retention_days FROM organisations WHERE id = $1', [p.organisation_id]);
    return consentNotice(org!.retention_days);
  }

  async acceptConsent(principal: Principal | null, practiceId: string, input: { consentVersion: string; textHash: string }) {
    const practice = await this.authorized(principal, 'practice:consent', practiceId);
    const notice = await this.getConsentNotice(principal, practiceId);
    if (input.consentVersion !== CONSENT_VERSION || input.textHash !== notice.textHash) {
      throw new DomainError('VALIDATION', 'consent must reference the currently displayed notice', { consentVersion: CONSENT_VERSION });
    }
    if (practice.status !== 'INVITED') throw new DomainError('CONFLICT', 'consent can only be given before start');
    const now = this.ctx.clock.now();
    return this.ctx.db.tx(async (tx) => {
      const existing = await tx.one<{ id: string }>(
        'SELECT id FROM consents WHERE practice_id = $1 AND candidate_id = $2 AND consent_version = $3',
        [practiceId, principal!.id, CONSENT_VERSION],
      );
      const id = existing?.id ?? newId('cns');
      if (!existing) {
        await tx.query(
          'INSERT INTO consents (id, candidate_id, practice_id, consent_version, text_hash, accepted_at) VALUES ($1,$2,$3,$4,$5,$6)',
          [id, principal!.id, practiceId, CONSENT_VERSION, input.textHash, now],
        );
        await tx.query('UPDATE candidates SET consent_version = $2, consent_at = $3 WHERE id = $1', [principal!.id, CONSENT_VERSION, now]);
        await tx.query('UPDATE practices SET consent_id = $2, updated_at = $3 WHERE id = $1', [practiceId, id, now]);
        await this.ctx.audit.append(tx, {
          ...auditActor(principal!),
          action: 'consent.accepted',
          entityType: 'consent',
          entityId: id,
          organisationId: practice.organisation_id,
          practiceId,
          detail: { consentVersion: CONSENT_VERSION, textHash: input.textHash },
        });
      }
      return { consentId: id, consentVersion: CONSENT_VERSION, acceptedAt: now };
    });
  }

  /** Idempotent: repeated start returns the existing workspace instead of creating a new one. */
  async start(principal: Principal | null, practiceId: string): Promise<PracticeRow> {
    await this.authorized(principal, 'practice:work', practiceId);
    const now = this.ctx.clock.now();
    return this.ctx.db.tx(async (tx) => {
      const p = await this.load(practiceId, tx, true);
      if (p.status === 'STARTED' || p.status === 'IN_PROGRESS') return p;
      const consent = p.consent_id
        ? await tx.one<{ accepted_at: Date; consent_version: string }>('SELECT accepted_at, consent_version FROM consents WHERE id = $1', [p.consent_id])
        : null;
      assertCanStart({
        status: p.status,
        consentAcceptedAt: consent ? new Date(consent.accepted_at) : null,
        consentVersion: consent?.consent_version ?? null,
        requiredConsentVersion: CONSENT_VERSION,
        deadline: new Date(p.deadline),
        now,
      });
      const policy = p.workspace_policy as unknown as WorkspacePolicy;
      const wsId = newId('ws');
      const expiresAt = new Date(p.deadline);
      await tx.query(
        `INSERT INTO workspaces (id, practice_id, driver, identity, lifecycle, policy_version, policy, expires_at, created_at)
         VALUES ($1,$2,$3,$4,'PROVISIONING',$5,$6,$7,$8)`,
        [wsId, practiceId, this.ctx.config.rdeDriver, `ws-identity-${wsId}`, policy.version, JSON.stringify(policy), expiresAt, now],
      );
      await tx.query('UPDATE practices SET workspace_id = $2 WHERE id = $1', [practiceId, wsId]);
      const updated = await this.transition(tx, practiceId, 'STARTED', actorOf(principal!), { workspaceId: wsId });
      await this.ctx.jobs.enqueue('workspace.provision', { practiceId, workspaceId: wsId }, { dedupeKey: `provision:${wsId}`, maxAttempts: 3 }, tx);
      return updated;
    });
  }

  // ---------- Platform ----------

  async expireOverdue(): Promise<string[]> {
    const now = this.ctx.clock.now();
    const due = await this.ctx.db.query<{ id: string }>(
      `SELECT id FROM practices WHERE status IN ('INVITED','STARTED','IN_PROGRESS') AND deadline <= $1`,
      [now],
    );
    const expired: string[] = [];
    for (const { id } of due) {
      await this.ctx.db.tx(async (tx) => {
        const p = await this.load(id, tx, true);
        if (!shouldExpire(p.status, new Date(p.deadline), now)) return;
        await this.transition(tx, id, 'EXPIRED', { actorType: 'platform', actorId: 'platform' }, { reason: 'deadline' });
        await this.auth.revokeWhere(tx, 'agent', 'practiceId', id);
        expired.push(id);
      });
    }
    return expired;
  }

  /** Expires lazily on access so a passed deadline is enforced even before the sweeper runs. */
  async assertWorkable(practiceId: string, q: Queryable = this.ctx.db): Promise<PracticeRow> {
    const p = await this.load(practiceId, q);
    const now = this.ctx.clock.now();
    if (shouldExpire(p.status, new Date(p.deadline), now)) {
      await this.expireOverdue();
      throw new DomainError('EXPIRED', 'practice deadline has passed');
    }
    if (p.status !== 'IN_PROGRESS') throw new DomainError('CONFLICT', `practice is ${p.status}, not IN_PROGRESS`);
    return p;
  }

  async retentionUntil(p: PracticeRow): Promise<Date | null> {
    if (!p.terminal_at) return null;
    const org = await this.ctx.db.one<{ retention_days: number }>('SELECT retention_days FROM organisations WHERE id = $1', [p.organisation_id]);
    return retentionDeadline(new Date(p.terminal_at), { artifactRetentionDays: org!.retention_days });
  }
}

export function auditActor(p: Principal): { actorKind: string; actorId: string } {
  return { actorKind: p.kind, actorId: p.id };
}

export function encodeCursor(v: Record<string, unknown>): string {
  return Buffer.from(JSON.stringify(v)).toString('base64url');
}

export function decodeCursor(c: string): any {
  try {
    return JSON.parse(Buffer.from(c, 'base64url').toString('utf8'));
  } catch {
    throw new DomainError('VALIDATION', 'invalid cursor');
  }
}
