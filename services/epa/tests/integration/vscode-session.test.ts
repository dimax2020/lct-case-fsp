import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { call, createTestPlatform, startPractice, type TestPlatform } from '@epa/test-fixtures';

describe('integration: VS Code extension session', () => {
  let t: TestPlatform;
  beforeAll(async () => {
    t = await createTestPlatform();
  });
  afterAll(async () => t?.close());

  it('shows extension telemetry on the employer timeline and drops a rotated code', async () => {
    const s = await startPractice(t);
    const denied = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/vscode-link`, t.employerToken);
    expect(denied.status).toBe(403);

    const link = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/vscode-link`, s.candidateToken);
    expect(link.status).toBe(200);
    expect(link.body.token.length).toBeGreaterThan(20);

    const waiting = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/vscode`, t.employerToken);
    expect(waiting.body.linked).toBe(true);
    expect(waiting.body.connected).toBe(false);

    const beat = await call(t.app, 'POST', '/v1/agent/heartbeat', link.body.token, {});
    expect(beat.status).toBe(200);
    const online = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/vscode`, t.employerToken);
    expect(online.body.connected).toBe(true);

    const occurredAt = new Date(t.clock.now().getTime()).toISOString();
    const batch = await call(t.app, 'POST', '/v1/agent/events:batch', link.body.token, {
      sessionId: link.body.sessionId,
      events: [
        { sequence: 1, type: 'session_started', occurredAt, payloadVersion: 1, payload: { client: 'vscode', reason: 'extension_connected' } },
        {
          sequence: 2,
          type: 'file_saved',
          occurredAt,
          payloadVersion: 1,
          payload: { path: 'src/auth/password.js', contentHash: 'ab'.repeat(32), bytes: 20 },
        },
      ],
    });
    expect(batch.status).toBe(200);

    const tl = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/timeline?limit=100`, t.employerToken);
    const vscodeEvents = tl.body.items.filter((e: { client: string }) => e.client === 'vscode');
    expect(vscodeEvents.map((e: { type: string }) => e.type)).toEqual(['session_started', 'file_saved']);
    expect(vscodeEvents[0].summary).toContain('VS Code');

    const outsider = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/vscode`, t.other.employerToken);
    expect([403, 404]).toContain(outsider.status);

    const rotated = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/vscode-link`, s.candidateToken);
    expect(rotated.status).toBe(200);
    expect(rotated.body.sessionId).not.toBe(link.body.sessionId);
    const stale = await call(t.app, 'POST', '/v1/agent/heartbeat', link.body.token, {});
    expect(stale.status).toBe(401);
  });

  it('keeps an uploaded snapshot but refuses to close the task from the extension', async () => {
    const s = await startPractice(t);
    const link = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/vscode-link`, s.candidateToken);
    const content = Buffer.from('export const n = 1;\n').toString('base64');
    const up = await call(t.app, 'POST', '/v1/agent/snapshots', link.body.token, {
      files: [{ path: 'src/auth/extra.js', contentBase64: content }],
      reason: 'pre_submit',
    });
    expect(up.status).toBe(201);
    expect(up.body.snapshotId).toMatch(/^snap_/);
    expect(['checkpoint', 'patch']).toContain(up.body.kind);

    const sidecar = await t.platform.workspaces.issueAgentCredential(s.workspaceId);
    const blocked = await call(t.app, 'POST', '/v1/agent/submit', sidecar.token, { snapshotId: up.body.snapshotId }, { 'idempotency-key': 'sidecar-nope' });
    expect(blocked.status).toBe(403);
    const fromExtension = await call(t.app, 'POST', '/v1/agent/submit', link.body.token, { snapshotId: up.body.snapshotId }, { 'idempotency-key': 'vscode-submit-1' });
    expect(fromExtension.status).toBe(403);

    const closed = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/submissions`, s.candidateToken, undefined, { 'idempotency-key': 'platform-close-1' });
    expect(closed.status).toBe(201);
    expect(closed.body.submission.version).toBe(1);
    const practice = await call(t.app, 'GET', `/v1/practices/${s.practiceId}`, s.candidateToken);
    expect(practice.body.status).toBe('SUBMITTED');
  });

  it('connects the extension with the candidate username and password', async () => {
    const s = await startPractice(t);
    const saved = await call(t.app, 'POST', '/v1/auth/extension-credentials', s.candidateToken, { username: 'worker', password: 'worker-secret' });
    expect(saved.status).toBe(200);
    expect(saved.body.username).toBe('worker');
    const bad = await call(t.app, 'POST', '/v1/agent/login', null, { username: 'worker', password: 'wrong-password' });
    expect(bad.status).toBe(401);
    const login = await call(t.app, 'POST', '/v1/agent/login', null, { username: 'worker', password: 'worker-secret' });
    expect(login.status).toBe(200);
    expect(login.body.token.length).toBeGreaterThan(20);
    const beat = await call(t.app, 'POST', '/v1/agent/heartbeat', login.body.token, {});
    expect(beat.status).toBe(200);
  });
});
