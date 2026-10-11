import { canonicalJson, sha256Hex } from '@epa/telemetry';
import type { Queryable } from './db.js';
import { newId, type Clock } from './core.js';

export interface AuditEntry {
  actorKind: string;
  actorId: string;
  action: string;
  entityType: string;
  entityId: string;
  organisationId?: string | null;
  practiceId?: string | null;
  detail?: Record<string, unknown>;
}

export interface AuditRow {
  seq: number;
  id: string;
  at: Date;
  actor_kind: string;
  actor_id: string;
  organisation_id: string | null;
  practice_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  detail: Record<string, unknown>;
  prev_hash: string | null;
  hash: string;
}

/** Hash-chained, append-only audit trail (UPDATE/DELETE are blocked by a DB trigger). */
export class AuditLog {
  constructor(private readonly clock: Clock) {}

  async append(q: Queryable, e: AuditEntry): Promise<void> {
    await q.query('SELECT pg_advisory_xact_lock(424242)');
    const last = await q.one<{ seq: number; hash: string }>('SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1');
    const seq = (last?.seq ?? 0) + 1;
    const at = this.clock.now();
    const detail = e.detail ?? {};
    const entry = {
      actorKind: e.actorKind,
      actorId: e.actorId,
      action: e.action,
      entityType: e.entityType,
      entityId: e.entityId,
      organisationId: e.organisationId ?? null,
      practiceId: e.practiceId ?? null,
    };
    const hash = sha256Hex(`${last?.hash ?? 'genesis'}:${canonicalJson({ seq, at: at.toISOString(), ...entry, detail })}`);
    await q.query(
      `INSERT INTO audit_log (seq, id, at, actor_kind, actor_id, organisation_id, practice_id, action, entity_type, entity_id, detail, prev_hash, hash)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)`,
      [seq, newId('aud'), at, e.actorKind, e.actorId, e.organisationId ?? null, e.practiceId ?? null, e.action, e.entityType, e.entityId, JSON.stringify(detail), last?.hash ?? null, hash],
    );
  }

  async verifyChain(q: Queryable): Promise<{ ok: boolean; brokenAt?: number }> {
    const rows = await q.query<AuditRow>('SELECT * FROM audit_log ORDER BY seq');
    let prev: string | null = null;
    for (const r of rows) {
      const entry = {
        actorKind: r.actor_kind,
        actorId: r.actor_id,
        action: r.action,
        entityType: r.entity_type,
        entityId: r.entity_id,
        organisationId: r.organisation_id,
        practiceId: r.practice_id,
      };
      const expected = sha256Hex(`${prev ?? 'genesis'}:${canonicalJson({ seq: r.seq, at: new Date(r.at).toISOString(), ...entry, detail: r.detail })}`);
      if (r.prev_hash !== prev || r.hash !== expected) return { ok: false, brokenAt: r.seq };
      prev = r.hash;
    }
    return { ok: true };
  }
}
