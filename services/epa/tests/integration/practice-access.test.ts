import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { call, createTestPlatform, futureIso, startPractice, type TestPlatform } from '@epa/test-fixtures';

describe('integration: practice, invitations, access control', () => {
  let t: TestPlatform;
  beforeAll(async () => {
    t = await createTestPlatform();
  });
  afterAll(async () => t?.close());

  const createPractice = async () => {
    const r = await call(t.app, 'POST', '/v1/practices', t.employerToken, { title: 'Practice', description: 'D', template: 'auth-service', deadline: futureIso(t.clock, 2) });
    expect(r.status).toBe(201);
    return r.body.id as string;
  };

  it('invitation redemption is atomic: concurrent redeems yield exactly one candidate', async () => {
    const id = await createPractice();
    const inv = await call(t.app, 'POST', `/v1/practices/${id}/invitations`, t.employerToken, { candidateEmail: 'c@x.test' });
    const results = await Promise.all(Array.from({ length: 5 }, () => call(t.app, 'POST', '/v1/invitations/redeem', null, { token: inv.body.token })));
    expect(results.filter((r) => r.status === 200)).toHaveLength(1);
    for (const r of results.filter((x) => x.status !== 200)) expect([409, 410]).toContain(r.status);
  });

  it('an employer of another organisation cannot read or act on the practice (403/404)', async () => {
    const id = await createPractice();
    for (const [m, url] of [
      ['GET', `/v1/practices/${id}`],
      ['POST', `/v1/practices/${id}/invitations`],
      ['GET', `/v1/practices/${id}/timeline`],
      ['GET', `/v1/practices/${id}/report`],
      ['POST', `/v1/practices/${id}/complete`],
    ] as const) {
      const r = await call(t.app, m, url, t.other.employerToken, m === 'POST' ? { candidateEmail: 'z@z.test' } : undefined);
      expect([403, 404], `${m} ${url}`).toContain(r.status);
    }
    const list = await call(t.app, 'GET', '/v1/practices', t.other.employerToken);
    expect(list.body.items.map((p: any) => p.id)).not.toContain(id);
  });

  it('start is idempotent and requires consent first', async () => {
    const id = await createPractice();
    const inv = await call(t.app, 'POST', `/v1/practices/${id}/invitations`, t.employerToken, { candidateEmail: 'c@x.test' });
    const red = await call(t.app, 'POST', '/v1/invitations/redeem', null, { token: inv.body.token });
    const tok = red.body.candidateToken;
    expect((await call(t.app, 'POST', `/v1/practices/${id}/start`, tok)).status).toBe(409);
    const n = red.body.consentNotice;
    await call(t.app, 'POST', `/v1/practices/${id}/consent`, tok, { consentVersion: n.version, textHash: n.textHash, accepted: true });
    const a = await call(t.app, 'POST', `/v1/practices/${id}/start`, tok);
    const b = await call(t.app, 'POST', `/v1/practices/${id}/start`, tok);
    expect(a.status).toBe(202);
    expect(b.status).toBe(202);
    expect(b.body.workspaceId).toBe(a.body.workspaceId);
    const jobs = await t.platform.ctx.db.query(`SELECT id FROM jobs WHERE kind = 'workspace.provision' AND payload->>'practiceId' = $1`, [id]);
    expect(jobs).toHaveLength(1);
    await t.drain();
  });

  it('two practices get separate workspaces with different identities and directories', async () => {
    const a = await startPractice(t);
    const b = await startPractice(t);
    expect(a.workspaceId).not.toBe(b.workspaceId);
    const rows = await t.platform.ctx.db.query<any>('SELECT id, identity, runtime_ref FROM workspaces WHERE id = ANY($1)', [[a.workspaceId, b.workspaceId]]);
    expect(new Set(rows.map((r) => r.identity)).size).toBe(2);
    expect(new Set(rows.map((r) => r.runtime_ref)).size).toBe(2);
    await call(t.app, 'PUT', `/v1/workspaces/${a.workspaceId}/file`, a.candidateToken, { path: 'notes.txt', content: 'only in A' });
    expect((await call(t.app, 'GET', `/v1/workspaces/${b.workspaceId}/file?path=notes.txt`, b.candidateToken)).status).toBe(404);
    expect((await call(t.app, 'GET', `/v1/workspaces/${a.workspaceId}/file?path=notes.txt`, b.candidateToken)).status).toBe(403);
  });

  it('shows the invited person and lets the employer delete the practice', async () => {
    const id = await createPractice();
    await call(t.app, 'POST', `/v1/practices/${id}/invitations`, t.employerToken, { candidateEmail: 'worker@example.test' });
    const got = await call(t.app, 'GET', `/v1/practices/${id}`, t.employerToken);
    expect(got.body.invitedEmail).toBe('worker@example.test');
    expect(got.body.candidateEmail).toBeNull();
    const templates = await call(t.app, 'GET', '/v1/templates', t.employerToken);
    expect(templates.body.items).not.toContain('auth-service');
    expect(templates.body.items).toContain('blank');
    const removed = await call(t.app, 'DELETE', `/v1/practices/${id}`, t.employerToken);
    expect(removed.status).toBe(204);
    expect((await call(t.app, 'GET', `/v1/practices/${id}`, t.employerToken)).status).toBe(404);
    const other = await createPractice();
    expect([403, 404]).toContain((await call(t.app, 'DELETE', `/v1/practices/${other}`, t.other.employerToken)).status);
  });

  it('deletes a practice that is already in progress and names the candidate', async () => {
    const s = await startPractice(t);
    const view = await call(t.app, 'GET', `/v1/practices/${s.practiceId}`, t.employerToken);
    expect(view.body.candidateEmail).toBe('cand@example.test');
    expect((await call(t.app, 'DELETE', `/v1/practices/${s.practiceId}`, t.employerToken)).status).toBe(204);
    expect((await call(t.app, 'GET', `/v1/practices/${s.practiceId}`, t.employerToken)).status).toBe(404);
  });
});
