import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { symlink } from 'node:fs/promises';
import path from 'node:path';
import { call, createTestPlatform, startPractice, type TestPlatform } from '@epa/test-fixtures';

const ev = (sequence: number, type: string, payload: Record<string, unknown>) => ({ sequence, type, occurredAt: new Date().toISOString(), payloadVersion: 1, payload });

describe('security: workspace input validation', () => {
  let t: TestPlatform;
  let s: Awaited<ReturnType<typeof startPractice>>;
  let repo: string;
  beforeAll(async () => {
    t = await createTestPlatform();
    s = await startPractice(t);
    repo = path.join(t.dataDir, 'workspaces', s.workspaceId, 'repository');
  });
  afterAll(async () => t?.close());

  it.each(['../../../etc/passwd', '/etc/passwd', '~/.ssh/id_rsa', 'src/../../x', '.git/config', '.epa/outbox.json', 'C:\\Windows\\win.ini', 'a\u0000b'])('rejects unsafe path %j', async (p) => {
    const read = await call(t.app, 'GET', `/v1/workspaces/${s.workspaceId}/file?path=${encodeURIComponent(p)}`, s.candidateToken);
    const write = await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, { path: p, content: 'x' });
    expect(read.status).toBe(400);
    expect(write.status).toBe(400);
  });

  it('never follows symlinks out of the workspace', async () => {
    await symlink('/etc', path.join(repo, 'etc-link'));
    await symlink('/etc/hosts', path.join(repo, 'hosts-link'));
    for (const p of ['etc-link/hosts', 'hosts-link']) {
      const r = await call(t.app, 'GET', `/v1/workspaces/${s.workspaceId}/file?path=${p}`, s.candidateToken);
      expect([400, 403, 404]).toContain(r.status);
      expect(JSON.stringify(r.body)).not.toMatch(/localhost/);
      const w = await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, { path: p, content: 'pwned' });
      expect([400, 403, 404]).toContain(w.status);
    }
    const snap = await t.platform.workspaces.snapshot(await t.platform.practices.load(s.practiceId), s.workspaceId, 'manual');
    expect(snap.skipped.map((x: any) => x.reason)).toContain('symlink');
  });

  it('rejects oversized files, malformed bodies and shell injection', async () => {
    expect((await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, { path: 'big.txt', content: 'x'.repeat(2 * 1024 * 1024) })).status).toBe(413);
    expect((await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, { path: 'a.js', content: 1, extra: true })).status).toBe(400);
    const raw = await t.app.inject({ method: 'PUT', url: `/v1/workspaces/${s.workspaceId}/file`, headers: { authorization: `Bearer ${s.candidateToken}`, 'content-type': 'application/json' }, payload: '{"path":' });
    expect(raw.statusCode).toBe(400);
    for (const c of ['ls; cat /etc/passwd', 'curl http://169.254.169.254', 'cat $(id)', 'ssh localhost', 'git push origin main']) {
      expect((await call(t.app, 'POST', `/v1/workspaces/${s.workspaceId}/commands`, s.candidateToken, { command: c })).status).toBe(400);
    }
  });

  it('redacts secrets from recorded terminal commands', async () => {
    await call(t.app, 'POST', `/v1/workspaces/${s.workspaceId}/commands`, s.candidateToken, { command: 'echo AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY ghp_abcdefghijklmnopqrstuvwxyz0123456789' });
    await t.platform.workspaces.flushAll();
    const rows = await t.platform.ctx.db.query<any>(`SELECT payload FROM telemetry_events WHERE practice_id = $1 AND type = 'terminal_command'`, [s.practiceId]);
    const dump = JSON.stringify(rows);
    expect(dump).not.toContain('wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY');
    expect(dump).not.toContain('ghp_abcdefghijklmnopqrstuvwxyz0123456789');
    expect(dump).toContain('[REDACTED');
  });
});

describe('security: telemetry ingestion', () => {
  let t: TestPlatform;
  let cred: { token: string; sessionId: string };
  beforeAll(async () => {
    t = await createTestPlatform();
    const s = await startPractice(t);
    cred = await t.platform.workspaces.issueAgentCredential(s.workspaceId);
  });
  afterAll(async () => t?.close());

  const send = (events: unknown[]) => call(t.app, 'POST', '/v1/agent/events:batch', cred.token, { sessionId: cred.sessionId, events });

  it.each(['keypress', 'keystroke', 'clipboard', 'clipboard_read', 'screen_capture', 'process_list', 'window_focus'])('there is no %s event type', async (type) => {
    expect((await send([ev(1, type, { key: 'a' })])).status).toBe(400);
  });

  it('rejects unknown payload fields, raw content and client system paths', async () => {
    expect((await send([ev(1, 'file_saved', { path: 'a.js', contentHash: 'a'.repeat(64), bytes: 1, content: 'secret source' })])).status).toBe(400);
    expect((await send([ev(1, 'file_saved', { path: '/Users/alice/projects/a.js', contentHash: 'a'.repeat(64), bytes: 1 })])).status).toBe(400);
    expect((await send([ev(1, 'large_insertion_signal', { file: 'a.js', insertedChars: 5000, threshold: 800, interpretation: 'cheating_detected' })])).status).toBe(400);
  });

  it('platform-only event types cannot be forged by agents', async () => {
    expect((await send([ev(1, 'submission_created', { submissionId: 'sub_x', version: 1 })])).status).toBe(400);
  });

  it('rejects oversized batches', async () => {
    const many = Array.from({ length: 501 }, (_, i) => ev(i + 1, 'file_deleted', { path: `f${i}.js` }));
    expect([400, 413]).toContain((await send(many)).status);
    const fat = [ev(1, 'terminal_command', { command: 'x'.repeat(300_000), exitCode: 0, durationMs: 1, timedOut: false })];
    expect([400, 413]).toContain((await send(fat)).status);
  });
});
