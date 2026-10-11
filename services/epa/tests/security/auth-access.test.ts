import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { SOLUTION, call, createTestPlatform, startPractice, type TestPlatform } from '@epa/test-fixtures';

describe('security: authentication, tokens and horizontal access', () => {
  let t: TestPlatform;
  let a: Awaited<ReturnType<typeof startPractice>>;
  let b: Awaited<ReturnType<typeof startPractice>>;
  let subA: any;

  beforeAll(async () => {
    t = await createTestPlatform();
    a = await startPractice(t);
    b = await startPractice(t);
    for (const [p, c] of Object.entries(SOLUTION)) await call(t.app, 'PUT', `/v1/workspaces/${a.workspaceId}/file`, a.candidateToken, { path: p, content: c });
    subA = (await call(t.app, 'POST', `/v1/practices/${a.practiceId}/submissions`, a.candidateToken, undefined, { 'idempotency-key': 'sec-sub-a1' })).body.submission;
    await t.drain();
  });
  afterAll(async () => t?.close());

  it('stores only token hashes (invite, candidate, staff), never raw tokens', async () => {
    const dump = JSON.stringify(await t.platform.ctx.db.query('SELECT * FROM auth_tokens')) + JSON.stringify(await t.platform.ctx.db.query('SELECT * FROM invitations'));
    for (const raw of [a.inviteToken, a.candidateToken, t.employerToken, t.auditorToken, t.platformToken]) expect(dump).not.toContain(raw);
  });

  it('rejects forged, malformed and missing tokens', async () => {
    for (const tok of [null, 'x', 'Bearer', a.candidateToken.slice(0, -2) + 'zz', 'a'.repeat(500)]) {
      expect((await call(t.app, 'GET', `/v1/practices/${a.practiceId}`, tok)).status).toBe(401);
    }
  });

  it('rate-limits invitation brute force', async () => {
    const statuses: number[] = [];
    for (let i = 0; i < 15; i++) statuses.push((await call(t.app, 'POST', '/v1/invitations/redeem', null, { token: `inv_${'0'.repeat(30)}${i}` })).status);
    expect(statuses).toContain(429);
    expect(statuses.filter((s) => s === 200)).toHaveLength(0);
  });

  it('a candidate cannot access another candidate’s practice, workspace, timeline or snapshots', async () => {
    for (const [m, url] of [
      ['GET', `/v1/practices/${a.practiceId}`],
      ['GET', `/v1/practices/${a.practiceId}/timeline`],
      ['GET', `/v1/workspaces/${a.workspaceId}/files`],
      ['GET', `/v1/workspaces/${a.workspaceId}/file?path=README.md`],
      ['POST', `/v1/workspaces/${a.workspaceId}/commands`],
      ['GET', `/v1/snapshots/${subA.snapshotId}/file?path=src/auth/session.js`],
      ['POST', `/v1/practices/${a.practiceId}/submissions`],
    ] as const) {
      const r = await call(t.app, m, url, b.candidateToken, m === 'POST' ? { command: 'ls' } : undefined, { 'idempotency-key': 'cross-0001' });
      expect([403, 404], `${m} ${url}`).toContain(r.status);
    }
  });

  it('a candidate cannot act as employer: no review, comments, resolve, report, assessments or AI findings', async () => {
    await call(t.app, 'POST', `/v1/practices/${a.practiceId}/review`, t.employerToken);
    const c = await call(t.app, 'POST', `/v1/submissions/${subA.id}/comments`, t.employerToken, { filePath: 'src/auth/session.js', lineStart: 1, lineEnd: 1, body: 'note' });
    expect(c.status).toBe(201);
    const attempts = [
      call(t.app, 'POST', `/v1/submissions/${subA.id}/comments`, a.candidateToken, { filePath: 'src/auth/session.js', lineStart: 1, lineEnd: 1, body: 'self-review' }),
      call(t.app, 'POST', `/v1/practices/${a.practiceId}/request-changes`, a.candidateToken),
      call(t.app, 'POST', `/v1/practices/${a.practiceId}/complete`, a.candidateToken),
      call(t.app, 'GET', `/v1/practices/${a.practiceId}/report`, a.candidateToken),
      call(t.app, 'POST', `/v1/practices/${a.practiceId}/assessments`, a.candidateToken),
      call(t.app, 'POST', `/v1/submissions/${subA.id}/analysis`, a.candidateToken),
      call(t.app, 'GET', `/v1/practices/${a.practiceId}/audit`, a.candidateToken),
    ];
    for (const r of await Promise.all(attempts)) expect(r.status).toBe(403);
    const ai = await call(t.app, 'GET', `/v1/practices/${a.practiceId}/ai`, a.candidateToken);
    for (const an of ai.body.analyses) expect(an.output).toBeUndefined();
    // Candidates may resolve comments (spec §RBAC), but the resolution is attributed to them, never to the employer.
    const forged = await call(t.app, 'POST', `/v1/comments/${c.body.id}/resolve`, a.candidateToken, { resolvedBy: { kind: 'employer', id: t.employerId } });
    expect(forged.status).toBe(200);
    expect(forged.body.resolvedBy).toEqual({ kind: 'candidate', id: a.candidateId });
    expect((await call(t.app, 'POST', `/v1/comments/${c.body.id}/resolve`, b.candidateToken)).status).toBe(403);
  });

  it('cross-organisation employers cannot comment, resolve, read reports, snapshots or logs', async () => {
    const other = t.other.employerToken;
    const run = (await call(t.app, 'GET', `/v1/practices/${a.practiceId}/test-runs`, t.employerToken)).body.items[0];
    const res = await Promise.all([
      call(t.app, 'POST', `/v1/submissions/${subA.id}/comments`, other, { filePath: 'src/auth/session.js', lineStart: 1, lineEnd: 1, body: 'x' }),
      call(t.app, 'GET', `/v1/practices/${a.practiceId}/comments`, other),
      call(t.app, 'GET', `/v1/practices/${a.practiceId}/report`, other),
      call(t.app, 'GET', `/v1/snapshots/${subA.snapshotId}`, other),
      call(t.app, 'POST', `/v1/test-runs/${run.id}/log-link`, other),
      call(t.app, 'GET', `/v1/practices/${a.practiceId}/audit`, other),
    ]);
    for (const r of res) expect([403, 404]).toContain(r.status);
  });

  it('report views are audited; auditors read audit but cannot change the practice', async () => {
    await call(t.app, 'GET', `/v1/practices/${a.practiceId}/report`, t.employerToken);
    const audit = await call(t.app, 'GET', `/v1/practices/${a.practiceId}/audit`, t.auditorToken);
    expect(audit.status).toBe(200);
    expect(audit.body.items.map((i: any) => i.action)).toContain('report.viewed');
    expect((await call(t.app, 'POST', `/v1/practices/${a.practiceId}/complete`, t.auditorToken)).status).toBe(403);
  });

  it('ops endpoints and retention purge require the platform role', async () => {
    for (const tok of [t.employerToken, t.auditorToken, a.candidateToken]) {
      expect((await call(t.app, 'POST', '/v1/ops/retention/sweep', tok)).status).toBe(403);
      expect((await call(t.app, 'GET', '/v1/ops/dead-letters', tok)).status).toBe(403);
      expect((await call(t.app, 'GET', '/metrics', tok)).status).toBe(403);
    }
    expect((await call(t.app, 'GET', '/metrics', t.platformToken)).status).toBe(200);
  });

  it('agent credentials are bound to their own session', async () => {
    const credA = await t.platform.workspaces.issueAgentCredential(a.workspaceId);
    const credB = await t.platform.workspaces.issueAgentCredential(b.workspaceId);
    const r = await call(t.app, 'POST', '/v1/agent/events:batch', credA.token, {
      sessionId: credB.sessionId,
      events: [{ sequence: 1, type: 'session_started', occurredAt: new Date().toISOString(), payloadVersion: 1, payload: { client: 'workspace-agent' } }],
    });
    expect(r.status).toBe(403);
    expect((await call(t.app, 'GET', `/v1/practices/${a.practiceId}`, credA.token)).status).toBe(403);
  });
});
