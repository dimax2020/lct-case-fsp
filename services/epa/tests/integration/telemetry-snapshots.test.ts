import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { mkdtemp, readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { FakeClock } from '@epa/platform';
import { FlakyTransport, HttpTransport, WorkspaceAgent } from '@epa/workspace-agent';
import { manifestHash, readWorkspaceTree } from '@epa/snapshots';
import { buildSnapshotPolicy } from '@epa/domain';
import { SOLUTION, call, createTestPlatform, injectFetch, startPractice, type TestPlatform } from '@epa/test-fixtures';

const ev = (sequence: number, type: string, payload: Record<string, unknown>, at = new Date()) => ({ sequence, type, occurredAt: at.toISOString(), payloadVersion: 1, payload });

describe('integration: workspace agent → ingestion → timeline', () => {
  let t: TestPlatform;
  let clock: FakeClock;
  let s: Awaited<ReturnType<typeof startPractice>>;
  let agentCred: { token: string; sessionId: string };

  beforeAll(async () => {
    clock = new FakeClock(new Date());
    t = await createTestPlatform({ clock });
    s = await startPractice(t);
    agentCred = await t.platform.workspaces.issueAgentCredential(s.workspaceId);
  });
  afterAll(async () => t?.close());

  const send = (events: unknown[], sessionId = agentCred.sessionId, token = agentCred.token) => call(t.app, 'POST', '/v1/agent/events:batch', token, { sessionId, events });

  it('accepts a batch, deduplicates replays and rejects reuse of a sequence with different content', async () => {
    const batch = [ev(1, 'session_started', { client: 'workspace-agent' }, clock.now()), ev(2, 'file_saved', { path: 'src/a.js', contentHash: 'a'.repeat(64), bytes: 10 }, clock.now())];
    const r1 = await send(batch);
    expect(r1.status).toBe(200);
    expect(r1.body).toMatchObject({ accepted: 2, duplicates: 0, nextExpectedSequence: 3 });
    const r2 = await send(batch);
    expect(r2.body).toMatchObject({ accepted: 0, duplicates: 2 });
    const conflict = await send([ev(2, 'file_saved', { path: 'src/b.js', contentHash: 'b'.repeat(64), bytes: 1 }, clock.now())]);
    expect(conflict.status).toBe(409);
  });

  it('reports a sequence gap with the next expected sequence and records an interruption', async () => {
    const r = await send([ev(5, 'file_deleted', { path: 'x.js' }, clock.now())]);
    expect(r.status).toBe(409);
    expect(r.body.gap).toEqual({ expected: 3, received: 5 });
    expect(r.body.nextExpectedSequence).toBe(3);
    const tl = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/timeline?limit=200`, t.employerToken);
    expect(tl.body.interruptions.some((i: any) => i.kind === 'sequence_gap' && i.sessionId === agentCred.sessionId)).toBe(true);
  });

  it('agent buffers events during a network outage and delivers them once, in order', async () => {
    const flaky = new FlakyTransport(new HttpTransport('http://platform.local', agentCred.token, injectFetch(t.app)));
    const dir = await mkdtemp(path.join(os.tmpdir(), 'epa-int-agent-'));
    const agent = await WorkspaceAgent.open({ sessionId: agentCred.sessionId, outboxDir: dir, transport: flaky, autoRetry: false, now: () => clock.now() });
    // Resume from where the server is (the agent persisted 1-2 previously in a real deployment).
    (agent as any).state.nextSequence = 3;
    flaky.offline = true;
    await agent.terminalCommand({ command: 'npm test', exitCode: 1, durationMs: 300, timedOut: false });
    clock.advance(1000);
    await agent.fileWritten({ path: 'src/a.js', before: 'a', after: 'ab' });
    await agent.flush();
    expect(agent.pendingCount).toBe(3);
    flaky.offline = false;
    clock.advance(45_000);
    await agent.flush();
    await agent.flush();
    expect(agent.pendingCount).toBe(0);
    const rows = await t.platform.ctx.db.query<any>('SELECT sequence, type FROM telemetry_events WHERE session_id = $1 ORDER BY sequence', [agentCred.sessionId]);
    expect(rows.map((r) => r.sequence)).toEqual([1, 2, 3, 4, 5]);
    expect(rows.map((r) => r.type).slice(2)).toEqual(['terminal_command', 'file_changed', 'file_saved']);
    const tl = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/timeline?limit=200`, t.employerToken);
    expect(tl.body.interruptions.some((i: any) => i.kind === 'delayed_delivery')).toBe(true);
    const integrity = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/timeline/integrity`, t.employerToken);
    expect(integrity.body.ok).toBe(true);
  });

  it('timeline pagination is stable and complete', async () => {
    const all: string[] = [];
    let cursor: string | null = null;
    do {
      const page: any = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/timeline?limit=3${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`, t.employerToken);
      all.push(...page.body.items.map((i: any) => `${i.sessionId}:${i.sequence}`));
      cursor = page.body.nextCursor;
    } while (cursor);
    const full = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/timeline?limit=200`, t.employerToken);
    expect(all).toEqual(full.body.items.map((i: any) => `${i.sessionId}:${i.sequence}`));
    expect(new Set(all).size).toBe(all.length);
  });
});

describe('integration: snapshots and immutable submissions', () => {
  let t: TestPlatform;
  let s: Awaited<ReturnType<typeof startPractice>>;
  beforeAll(async () => {
    t = await createTestPlatform();
    s = await startPractice(t, { snapshotPolicy: { significantSaveBytes: 1, checkpointEvery: 3 } });
  });
  afterAll(async () => t?.close());

  it('edits create patch snapshots whose reconstruction is byte-identical to the workspace', async () => {
    for (let i = 0; i < 5; i++) {
      await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, { path: `src/gen${i}.js`, content: `export const v = ${i};\n` });
    }
    for (const [p, c] of Object.entries(SOLUTION)) await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, { path: p, content: c });
    const list = (await call(t.app, 'GET', `/v1/practices/${s.practiceId}/snapshots`, t.employerToken)).body.items;
    expect(list.length).toBeGreaterThanOrEqual(5);
    expect(list.filter((x: any) => x.kind === 'checkpoint').length).toBeGreaterThanOrEqual(2);
    const latest = list.at(-1);
    const tree = await t.platform.snapshots.reconstruct(latest.id);
    const repoDir = path.join(t.dataDir, 'workspaces', s.workspaceId, 'repository');
    const { tree: live } = await readWorkspaceTree(repoDir, buildSnapshotPolicy({}));
    expect(manifestHash(tree)).toBe(manifestHash(live));
    expect(tree.get('src/auth/session.js')!.equals(await readFile(path.join(repoDir, 'src/auth/session.js')))).toBe(true);
  });

  it('submission snapshots and records cannot be modified', async () => {
    const r = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/submissions`, s.candidateToken, undefined, { 'idempotency-key': 'int-sub-1' });
    expect(r.status).toBe(201);
    const db = t.platform.ctx.db;
    await expect(db.query(`UPDATE submissions SET commit_sha = 'deadbeef' WHERE id = $1`, [r.body.submission.id])).rejects.toThrow();
    await expect(db.query(`UPDATE snapshots SET manifest_hash = 'x' WHERE id = $1`, [r.body.submission.snapshotId])).rejects.toThrow();
    await expect(db.query(`DELETE FROM snapshots WHERE id = $1`, [r.body.submission.snapshotId])).rejects.toThrow();
    await expect(db.query(`DELETE FROM telemetry_events WHERE practice_id = $1`, [s.practiceId])).rejects.toThrow();
  });
});
