import { requireKind, type Principal } from '@epa/authz';
import { retentionEligibility } from '@epa/domain';
import type { Ctx } from '@epa/platform';
import type { GitService } from '@epa/git';

export interface PurgeReport {
  practiceId: string;
  objectsDeleted: number;
  eventsDeleted: number;
}

/**
 * Applies the organisation retention policy after COMPLETED/EXPIRED: deletes snapshots, logs,
 * telemetry and the git repository, anonymises the candidate, and keeps only the audit record.
 */
export class RetentionService {
  constructor(private readonly ctx: Ctx, private readonly git: GitService) {}

  async sweep(): Promise<PurgeReport[]> {
    const now = this.ctx.clock.now();
    const rows = await this.ctx.db.query<any>(
      `SELECT p.id, p.status, p.terminal_at, p.purged_at, o.retention_days FROM practices p JOIN organisations o ON o.id = p.organisation_id
       WHERE p.status IN ('COMPLETED','EXPIRED') AND p.purged_at IS NULL`,
    );
    const reports: PurgeReport[] = [];
    for (const r of rows) {
      const d = retentionEligibility({
        status: r.status,
        terminalAt: r.terminal_at ? new Date(r.terminal_at) : null,
        purgedAt: null,
        policy: { artifactRetentionDays: r.retention_days },
        now,
      });
      if (d.eligible) reports.push(await this.purge(r.id));
    }
    return reports;
  }

  async sweepAs(principal: Principal | null) {
    requireKind(principal, 'platform');
    return this.sweep();
  }

  async purge(practiceId: string): Promise<PurgeReport> {
    const snaps = await this.ctx.db.query<{ object_key: string }>('SELECT object_key FROM snapshots WHERE practice_id = $1 AND purged_at IS NULL', [practiceId]);
    const logs = await this.ctx.db.query<{ log_object_key: string }>('SELECT log_object_key FROM test_runs WHERE practice_id = $1 AND log_object_key IS NOT NULL', [practiceId]);
    const keys = [...snaps.map((s) => s.object_key), ...logs.map((l) => l.log_object_key)];
    const now = this.ctx.clock.now();
    const eventsDeleted = await this.ctx.db.tx(async (tx) => {
      await tx.query(`SELECT set_config('epa.retention_purge', 'on', true)`);
      const ev = await tx.one<{ n: number }>('SELECT count(*)::int AS n FROM telemetry_events WHERE practice_id = $1', [practiceId]);
      await tx.query('DELETE FROM telemetry_events WHERE practice_id = $1', [practiceId]);
      await tx.query('DELETE FROM telemetry_diagnostics WHERE practice_id = $1', [practiceId]);
      await tx.query('UPDATE snapshots SET purged_at = $2 WHERE practice_id = $1', [practiceId, now]);
      await tx.query(`UPDATE test_runs SET log_object_key = NULL, summary = summary - 'failedTests' WHERE practice_id = $1`, [practiceId]);
      await tx.query(`UPDATE interview_answers SET text = '[purged]' WHERE question_id IN (SELECT id FROM interview_questions WHERE practice_id = $1)`, [practiceId]);
      await tx.query(`UPDATE review_comments SET body = '[purged]' WHERE practice_id = $1`, [practiceId]);
      await tx.query(`UPDATE git_commits SET message = '[purged]', changed_files = '[]'::jsonb WHERE practice_id = $1`, [practiceId]);
      await tx.query(`UPDATE ai_analyses SET output = NULL, rejected = '[]'::jsonb, input_hashes = NULL WHERE practice_id = $1`, [practiceId]);
      await tx.query(
        `UPDATE candidates SET identity = 'anonymised:' || id, anonymised_at = $2 WHERE id = (SELECT candidate_id FROM practices WHERE id = $1)`,
        [practiceId, now],
      );
      await tx.query('UPDATE invitations SET candidate_email = $2 WHERE practice_id = $1', [practiceId, 'anonymised']);
      await tx.query(`UPDATE auth_tokens SET revoked_at = $2 WHERE revoked_at IS NULL AND (scope->>'practiceId') = $1`, [practiceId, now]);
      await tx.query('UPDATE practices SET purged_at = $2 WHERE id = $1', [practiceId, now]);
      const org = await tx.one<{ organisation_id: string }>('SELECT organisation_id FROM practices WHERE id = $1', [practiceId]);
      await this.ctx.audit.append(tx, {
        actorKind: 'platform',
        actorId: 'platform',
        action: 'retention.purged',
        entityType: 'practice',
        entityId: practiceId,
        organisationId: org?.organisation_id,
        practiceId,
        detail: { objects: keys.length, events: ev!.n },
      });
      return ev!.n;
    });
    for (const k of keys) await this.ctx.objects.delete(k);
    await this.git.deletePracticeRepo(practiceId);
    this.ctx.metrics.inc('retention_purged_total');
    return { practiceId, objectsDeleted: keys.length, eventsDeleted };
  }
}
