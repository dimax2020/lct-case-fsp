import type { Principal } from '@epa/authz';
import { parseTelemetryPayload, telemetryBatch, AGENT_EVENT_TYPES, type TelemetryBatch, type TelemetryPayloadType } from '@epa/contracts';
import { DomainError, TELEMETRY_POLICY } from '@epa/domain';
import { newId, type Ctx, type Queryable } from '@epa/platform';
import { chainHash, eventContentHash, redactSecrets, safeLog, PAYLOAD_VERSION } from '@epa/telemetry';
import { ZodError } from 'zod';

export interface IngestResult {
  accepted: number;
  duplicates: number;
  nextExpectedSequence: number;
  gap: { expected: number; received: number } | null;
}

interface SessionRow {
  id: string;
  practice_id: string;
  workspace_id: string | null;
  kind: 'workspace' | 'platform';
  ended_at: Date | null;
  last_sequence: number;
  last_hash: string | null;
}

const INGEST_STATUSES = new Set(['STARTED', 'IN_PROGRESS', 'SUBMITTED', 'REVIEW']);

/** Server-side defence in depth: never trust the agent to have redacted or truncated. */
function sanitizePayload(type: TelemetryPayloadType, payload: any): any {
  if (type === 'terminal_command' || type === 'test_started' || type === 'test_finished') {
    payload = { ...payload, command: redactSecrets(payload.command) };
  }
  if (type === 'test_finished') payload = { ...payload, safeLog: safeLog(payload.safeLog, TELEMETRY_POLICY.maxSafeLogBytes).text };
  if (type === 'git_commit') payload = { ...payload, message: redactSecrets(payload.message) };
  return payload;
}

export class TelemetryIngestion {
  constructor(private readonly ctx: Ctx) {}

  /**
   * Appends an agent batch. Ordering is by (session_id, sequence):
   *  - sequence <= last: idempotent duplicate if the content hash matches, otherwise 409 conflict;
   *  - sequence == last + 1: appended;
   *  - sequence  > last + 1: gap. Processing stops, a diagnostic is recorded and the caller is told
   *    which sequence to resend from. Earlier events in the batch stay committed.
   */
  async ingest(principal: Principal | null, raw: unknown): Promise<IngestResult> {
    if (!principal || principal.kind !== 'agent') throw new DomainError('FORBIDDEN', 'only workspace agents may ingest telemetry');
    const bytes = Buffer.byteLength(JSON.stringify(raw ?? null));
    if (bytes > TELEMETRY_POLICY.maxBatchBytes) throw new DomainError('PAYLOAD_TOO_LARGE', 'telemetry batch too large');
    let batch: TelemetryBatch;
    const payloads: unknown[] = [];
    try {
      batch = telemetryBatch.parse(raw);
      for (const e of batch.events) {
        if (!AGENT_EVENT_TYPES.includes(e.type)) throw new DomainError('VALIDATION', `event type ${e.type} is platform-only`);
        payloads.push(sanitizePayload(e.type, parseTelemetryPayload(e.type, e.payload)));
      }
    } catch (e) {
      if (e instanceof ZodError) {
        this.ctx.metrics.inc('telemetry_rejected_total', { reason: 'schema' });
        throw new DomainError('VALIDATION', 'malformed telemetry batch', { issues: e.issues.slice(0, 5).map((i) => `${i.path.join('.')}: ${i.message}`) });
      }
      throw e;
    }
    if (batch.sessionId !== principal.sessionId) throw new DomainError('FORBIDDEN', 'session does not belong to this credential');
    const events = batch.events.map((e, i) => ({ ...e, payload: payloads[i] })).sort((a, b) => a.sequence - b.sequence);

    return this.ctx.db.tx(async (tx) => {
      const session = await tx.one<SessionRow>('SELECT * FROM dev_sessions WHERE id = $1 FOR UPDATE', [batch.sessionId]);
      if (!session || session.kind !== 'workspace' || session.practice_id !== principal.practiceId || session.workspace_id !== principal.workspaceId) {
        throw new DomainError('FORBIDDEN', 'unknown session');
      }
      const practice = await tx.one<{ status: string }>('SELECT status FROM practices WHERE id = $1', [session.practice_id]);
      const onlySessionEnd = events.every((e) => e.type === 'session_ended');
      if (!practice || (!INGEST_STATUSES.has(practice.status) && !onlySessionEnd)) throw new DomainError('GONE', 'practice no longer accepts telemetry');

      let last = session.last_sequence;
      let lastHash = session.last_hash;
      let accepted = 0;
      let duplicates = 0;
      let gap: IngestResult['gap'] = null;
      const now = this.ctx.clock.now();
      for (const e of events) {
        const contentHash = eventContentHash({ sessionId: session.id, ...e });
        if (e.sequence <= last) {
          const existing = await tx.one<{ content_hash: string }>('SELECT content_hash FROM telemetry_events WHERE session_id = $1 AND sequence = $2', [session.id, e.sequence]);
          if (existing?.content_hash === contentHash) {
            duplicates++;
            continue;
          }
          await this.diagnostic(tx, session, 'sequence_conflict', { sequence: e.sequence });
          throw new DomainError('CONFLICT', 'sequence already used with different content', { sequence: e.sequence });
        }
        if (e.sequence > last + 1) {
          gap = { expected: last + 1, received: e.sequence };
          await this.diagnostic(tx, session, 'sequence_gap', gap);
          this.ctx.metrics.inc('telemetry_gaps_total');
          break;
        }
        const integrity = chainHash(lastHash, contentHash);
        await tx.query(
          `INSERT INTO telemetry_events (id, session_id, practice_id, sequence, type, occurred_at, received_at, payload_version, payload, content_hash, integrity_hash)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
          [newId('evt'), session.id, session.practice_id, e.sequence, e.type, new Date(e.occurredAt), now, e.payloadVersion, JSON.stringify(e.payload), contentHash, integrity],
        );
        if (e.type === 'session_ended') {
          await tx.query('UPDATE dev_sessions SET ended_at = $2, end_reason = $3 WHERE id = $1 AND ended_at IS NULL', [session.id, new Date(e.occurredAt), (e.payload as any).reason]);
        }
        last = e.sequence;
        lastHash = integrity;
        accepted++;
      }
      await tx.query('UPDATE dev_sessions SET last_sequence = $2, last_hash = $3, last_seen_at = $4 WHERE id = $1', [session.id, last, lastHash, now]);
      this.ctx.metrics.inc('telemetry_events_accepted_total', {}, accepted);
      this.ctx.metrics.inc('telemetry_events_duplicate_total', {}, duplicates);
      return { accepted, duplicates, nextExpectedSequence: last + 1, gap };
    });
  }

  private async diagnostic(q: Queryable, s: SessionRow, kind: string, detail: Record<string, unknown>) {
    await q.query('INSERT INTO telemetry_diagnostics (id, session_id, practice_id, kind, detail, created_at) VALUES ($1,$2,$3,$4,$5,$6)', [
      newId('diag'),
      s.id,
      s.practice_id,
      kind,
      JSON.stringify(detail),
      this.ctx.clock.now(),
    ]);
    this.ctx.log.warn('telemetry diagnostic', { sessionId: s.id, practiceId: s.practice_id, kind, ...detail });
  }
}

/** Writes platform-originated events (submit, review, requirement change, sandbox runs) into a per-practice platform session. */
export class PlatformEvents {
  constructor(private readonly ctx: Ctx) {}

  async append(q: Queryable, practiceId: string, type: TelemetryPayloadType, payload: unknown): Promise<void> {
    const parsed = parseTelemetryPayload(type, payload);
    await q.query('SELECT pg_advisory_xact_lock(hashtext($1))', [`platform-session:${practiceId}`]);
    let session = await q.one<SessionRow>(`SELECT * FROM dev_sessions WHERE practice_id = $1 AND kind = 'platform' FOR UPDATE`, [practiceId]);
    const now = this.ctx.clock.now();
    if (!session) {
      session = await q.one<SessionRow>(
        `INSERT INTO dev_sessions (id, practice_id, kind, client, started_at) VALUES ($1,$2,'platform','platform',$3) RETURNING *`,
        [newId('ses'), practiceId, now],
      );
    }
    const sequence = session!.last_sequence + 1;
    const occurredAt = now.toISOString();
    const contentHash = eventContentHash({ sessionId: session!.id, sequence, type, occurredAt, payloadVersion: PAYLOAD_VERSION, payload: parsed });
    const integrity = chainHash(session!.last_hash, contentHash);
    await q.query(
      `INSERT INTO telemetry_events (id, session_id, practice_id, sequence, type, occurred_at, received_at, payload_version, payload, content_hash, integrity_hash)
       VALUES ($1,$2,$3,$4,$5,$6,$6,$7,$8,$9,$10)`,
      [newId('evt'), session!.id, practiceId, sequence, type, now, PAYLOAD_VERSION, JSON.stringify(parsed), contentHash, integrity],
    );
    await q.query('UPDATE dev_sessions SET last_sequence = $2, last_hash = $3 WHERE id = $1', [session!.id, sequence, integrity]);
  }
}
