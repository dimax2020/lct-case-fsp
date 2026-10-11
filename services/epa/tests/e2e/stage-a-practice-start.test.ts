import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { call, createTestPlatform, startPractice, type TestPlatform } from '@epa/test-fixtures';

describe('E2E stage A: employer creates practice → candidate accepts invite/consent → starts → IN_PROGRESS', () => {
  let t: TestPlatform;
  beforeAll(async () => {
    t = await createTestPlatform();
  });
  afterAll(async () => t.close());

  it('walks INVITED → STARTED → IN_PROGRESS with consent and a provisioned workspace', async () => {
    const { practiceId, candidateToken, workspaceId } = await startPractice(t);
    const view = await call(t.app, 'GET', `/v1/practices/${practiceId}`, candidateToken);
    expect(view.status).toBe(200);
    expect(view.body.status).toBe('IN_PROGRESS');
    expect(view.body.workspace.lifecycle).toBe('READY');

    const ws = await call(t.app, 'GET', `/v1/practices/${practiceId}/workspace`, candidateToken);
    expect(ws.body.sshAccess).toBe(false);
    const files = await call(t.app, 'GET', `/v1/workspaces/${workspaceId}/files`, candidateToken);
    expect(files.body.items.map((f: any) => f.path).sort()).toEqual(['README.md', 'package.json', 'src/auth/password.js', 'src/auth/session.js', 'test/auth.test.js']);

    const audit = await call(t.app, 'GET', `/v1/practices/${practiceId}/audit`, t.auditorToken);
    const transitions = audit.body.items.filter((a: any) => a.action === 'practice.status_changed').map((a: any) => `${a.detail.from}->${a.detail.to}`);
    expect(transitions).toEqual(['INVITED->STARTED', 'STARTED->IN_PROGRESS']);
    expect(audit.body.items.map((a: any) => a.action)).toEqual(expect.arrayContaining(['invitation.created', 'invitation.redeemed', 'consent.accepted', 'workspace.provisioned']));
    expect(audit.body.chain.ok).toBe(true);
  });
});
