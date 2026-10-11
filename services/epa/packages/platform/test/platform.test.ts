import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {
  AuditLog,
  FakeClock,
  FsObjectStore,
  JobQueue,
  Metrics,
  ObjectAccessSigner,
  PermanentJobError,
  RateLimiter,
  Worker,
  createDb,
  createLogger,
  migrate,
  silentLogger,
  type Db,
} from '@epa/platform';

let db: Db;
const clock = new FakeClock('2026-05-01T10:00:00Z');

beforeAll(async () => {
  db = await createDb('memory://');
  await migrate(db);
});
afterAll(async () => db.close());

describe('job queue', () => {
  it('retries with exponential backoff and dead-letters after max attempts with a diagnostic', async () => {
    const q = new JobQueue(db, clock, silentLogger, new Metrics());
    const id = await q.enqueue('sandbox.run', { x: 1 }, { maxAttempts: 3 });
    let calls = 0;
    const w = new Worker(q, { 'sandbox.run': async () => { calls++; throw new Error('boom'); } }, silentLogger, new Metrics());
    expect(await w.runOnce()).toBe(true);
    let job = await q.get(id);
    expect(job!.status).toBe('RETRY');
    expect(await w.runOnce()).toBe(false);
    clock.advance(1000);
    await w.runOnce();
    job = await q.get(id);
    expect(job!.status).toBe('RETRY');
    expect(new Date(job!.run_after).getTime() - clock.now().getTime()).toBe(2000);
    clock.advance(2000);
    await w.runOnce();
    job = await q.get(id);
    expect(job!.status).toBe('DEAD');
    expect(job!.last_error).toBe('boom');
    expect(calls).toBe(3);
    expect((await q.deadLetters()).map((j) => j.id)).toContain(id);
  });

  it('permanent errors are not retried; dedupe keys are idempotent', async () => {
    const q = new JobQueue(db, clock, silentLogger, new Metrics());
    const a = await q.enqueue('ai.analyze', {}, { dedupeKey: 'k1' });
    const b = await q.enqueue('ai.analyze', {}, { dedupeKey: 'k1' });
    expect(a).toBe(b);
    const w = new Worker(q, { 'ai.analyze': async () => { throw new PermanentJobError('bad input'); } }, silentLogger, new Metrics());
    await w.drain();
    expect((await q.get(a))!.status).toBe('DEAD');
  });
});

describe('audit log', () => {
  it('is hash-chained and append-only at the database level', async () => {
    const audit = new AuditLog(clock);
    await db.tx((tx) => audit.append(tx, { actorKind: 'platform', actorId: 'platform', action: 'x.created', entityType: 'x', entityId: '1' }));
    await db.tx((tx) => audit.append(tx, { actorKind: 'employer', actorId: 'emp', action: 'x.updated', entityType: 'x', entityId: '1', detail: { a: 1 } }));
    expect(await audit.verifyChain(db)).toEqual({ ok: true });
    await expect(db.query(`UPDATE audit_log SET action = 'tampered'`)).rejects.toThrow(/append-only/);
    await expect(db.query('DELETE FROM audit_log')).rejects.toThrow(/append-only/);
  });
});

describe('object store and signed links', () => {
  let dir: string;
  beforeAll(async () => {
    dir = await mkdtemp(path.join(os.tmpdir(), 'epa-obj-'));
  });
  afterAll(async () => rm(dir, { recursive: true, force: true }));

  it('objects are write-once and hash-verified', async () => {
    const store = new FsObjectStore(dir);
    const o = await store.put('snapshots/prc_1/a.json.gz', Buffer.from('hello'));
    await expect(store.put('snapshots/prc_1/a.json.gz', Buffer.from('evil'))).rejects.toThrow(/immutable/);
    expect((await store.get(o.key, o.sha256)).toString()).toBe('hello');
    await expect(store.get(o.key, 'f'.repeat(64))).rejects.toThrow(/hash mismatch/);
    await expect(store.put('../escape', Buffer.from('x'))).rejects.toThrow(/invalid object key/);
    await expect(store.get('snapshots/../../etc/passwd')).rejects.toThrow(/invalid object key/);
  });

  it('signed links expire and cannot be forged', () => {
    const c = new FakeClock('2026-01-01T00:00:00Z');
    const signer = new ObjectAccessSigner('secret', c, 60);
    const { token } = signer.sign({ key: 'logs/prc_1/tr_1.log', principal: 'employer:emp' });
    expect(signer.verify(token).key).toBe('logs/prc_1/tr_1.log');
    const [body] = token.split('.');
    const forgedBody = Buffer.from(JSON.stringify({ key: 'logs/prc_2/tr_9.log', principal: 'x', expiresAt: 9e15, contentType: 'text/plain' })).toString('base64url');
    expect(() => signer.verify(`${forgedBody}.${token.split('.')[1]}`)).toThrow(/signature/);
    expect(() => new ObjectAccessSigner('other', c).verify(token)).toThrow(/signature/);
    void body;
    c.advance(61_000);
    expect(() => signer.verify(token)).toThrow(/expired/);
  });
});

describe('rate limiter and logger', () => {
  it('limits bursts and refills over time', () => {
    const c = new FakeClock();
    const rl = new RateLimiter(3, 1, c);
    rl.consume('ip');
    rl.consume('ip');
    rl.consume('ip');
    expect(() => rl.consume('ip')).toThrow(/too many/);
    c.advance(1000);
    expect(() => rl.consume('ip')).not.toThrow();
  });

  it('structured logs never contain secrets', () => {
    const lines: string[] = [];
    const log = createLogger({ sink: (l) => lines.push(l) });
    log.info('connecting with password=hunter2', { token: 'abc', authorization: 'Bearer xyz', url: 'postgres://u:pw@h/db', nested: { secret: 's' } });
    const out = lines.join('\n');
    expect(out).not.toContain('hunter2');
    expect(out).not.toContain('xyz');
    expect(out).not.toContain(':pw@');
    expect(JSON.parse(lines[0]).token).toBe('[omitted]');
  });
});
