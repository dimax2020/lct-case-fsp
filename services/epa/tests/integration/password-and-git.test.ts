import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import type { AddressInfo } from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { call, createTestPlatform, startPractice, type TestPlatform } from '@epa/test-fixtures';
import { zipStore } from '../../services/git/src/zip.js';

describe('integration: name entry and git upload', () => {
  let t: TestPlatform;
  beforeAll(async () => {
    t = await createTestPlatform();
  });
  afterAll(async () => t?.close());

  it('lets an employer and a candidate enter by name on the first visit', async () => {
    const ok = await call(t.app, 'POST', '/v1/auth/login', null, { name: 'Босс', role: 'employer' });
    expect(ok.status).toBe(200);
    expect(ok.body.role).toBe('employer');
    expect(ok.body.email).toBe('Босс');
    expect(ok.body.token.length).toBeGreaterThan(20);
    const again = await call(t.app, 'POST', '/v1/auth/login', null, { name: 'босс', role: 'employer' });
    expect(again.status).toBe(200);
    const me = await call(t.app, 'GET', '/v1/me', again.body.token);
    expect(me.body.email).toBe('Босс');
    const cand = await call(t.app, 'POST', '/v1/auth/login', null, { name: 'Никто', role: 'candidate' });
    expect(cand.status).toBe(200);
    expect(cand.body.role).toBe('candidate');
    expect(cand.body.email).toBe('Никто');
    const candAgain = await call(t.app, 'POST', '/v1/auth/login', null, { name: 'никто', role: 'candidate' });
    expect(candAgain.status).toBe(200);
    const candMe = await call(t.app, 'GET', '/v1/me', candAgain.body.token);
    expect(candMe.body.email).toBe('Никто');
  });

  it('registers a candidate from an invite and lets them fetch the project repository', async () => {
    const created = await call(t.app, 'POST', '/v1/practices', t.employerToken, {
      title: 'Auth service',
      description: 'Fix src/auth so that tests pass.',
      template: 'auth-service',
      deadline: new Date(t.clock.now().getTime() + 3 * 86_400_000).toISOString(),
    });
    const invite = await call(t.app, 'POST', `/v1/practices/${created.body.id}/invitations`, t.employerToken, { candidateEmail: 'ada@example.test' });
    const preview = await call(t.app, 'GET', `/v1/invitations/preview?token=${invite.body.token}`);
    expect(preview.body.email).toBe('ada@example.test');
    const registered = await call(t.app, 'POST', '/v1/auth/register', null, { token: invite.body.token, name: 'Ада', username: 'ada', password: 'ada-secret' });
    expect(registered.status).toBe(200);
    expect(registered.body.email).toBe('Ада');
    expect(registered.body.username).toBe('ada');
    const again = await call(t.app, 'POST', '/v1/auth/login', null, { name: 'Ада', role: 'candidate' });
    expect(again.status).toBe(200);
    expect(again.body.role).toBe('candidate');
  });

  it('advertises the practice git remote without a password', async () => {
    const s = await startPractice(t);
    const anon = await t.app.inject({ method: 'GET', url: `/git/${s.practiceId}.git/info/refs?service=git-upload-pack` });
    expect(anon.statusCode).toBe(200);
    const refs = anon;
    expect(refs.statusCode).toBe(200);
    expect(refs.body).toContain('# service=git-upload-pack');
    expect(refs.body).toContain('refs/heads/main');
    const project = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/project`, s.candidateToken);
    expect(project.body.remote).toContain(`/git/${s.practiceId}.git`);
    expect(project.body.candidateEmail).toBe('cand@example.test');
  });

  it('takes a git push without a password and shows the new commit', async () => {
    const created = await call(t.app, 'POST', '/v1/practices', t.employerToken, {
      title: 'Auth service',
      description: 'Fix src/auth so that tests pass.',
      template: 'auth-service',
      deadline: new Date(t.clock.now().getTime() + 3 * 86_400_000).toISOString(),
    });
    const invite = await call(t.app, 'POST', `/v1/practices/${created.body.id}/invitations`, t.employerToken, { candidateEmail: 'pusher@example.test' });
    const redeemed = await call(t.app, 'POST', '/v1/invitations/redeem', null, { token: invite.body.token });
    const candidateToken = redeemed.body.candidateToken as string;
    const notice = redeemed.body.consentNotice;
    await call(t.app, 'POST', `/v1/practices/${created.body.id}/consent`, candidateToken, { consentVersion: notice.version, textHash: notice.textHash, accepted: true });
    await call(t.app, 'POST', `/v1/practices/${created.body.id}/start`, candidateToken);
    await t.drain();
    const ws = await call(t.app, 'GET', `/v1/practices/${created.body.id}/workspace`, candidateToken);
    const s = { practiceId: created.body.id as string, workspaceId: ws.body.workspaceId as string };
    await t.app.listen({ port: 0, host: '127.0.0.1' });
    const port = (t.app.server.address() as AddressInfo).port;
    const remote = `http://127.0.0.1:${port}/git/${s.practiceId}.git`;
    const dir = await mkdtemp(path.join(os.tmpdir(), 'epa-push-client-'));
    const git = (args: string[], cwd: string) =>
      new Promise<{ status: number | null; stderr: string }>((resolve, reject) => {
        const child = spawn('git', args, {
          cwd,
          env: {
            ...process.env,
            GIT_TERMINAL_PROMPT: '0',
            GIT_AUTHOR_NAME: 'Ada',
            GIT_AUTHOR_EMAIL: 'pusher@example.test',
            GIT_COMMITTER_NAME: 'Ada',
            GIT_COMMITTER_EMAIL: 'pusher@example.test',
          },
        });
        let stderr = '';
        const timer = setTimeout(() => {
          child.kill();
          reject(new Error(`git timed out: ${stderr}`));
        }, 20_000);
        child.stderr.on('data', (d) => (stderr += d));
        child.on('close', (status) => {
          clearTimeout(timer);
          resolve({ status, stderr });
        });
      });
    try {
      const cloned = await git(['clone', remote, dir], os.tmpdir());
      expect(cloned.status, cloned.stderr).toBe(0);
      await writeFile(path.join(dir, 'FROM_CANDIDATE.txt'), 'uploaded\n');
      expect((await git(['add', 'FROM_CANDIDATE.txt'], dir)).status).toBe(0);
      expect((await git(['commit', '-m', 'upload the project'], dir)).status).toBe(0);
      const pushed = await git(['push', 'origin', 'HEAD:main'], dir);
      expect(pushed.status, pushed.stderr).toBe(0);
      const project = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/project`, t.employerToken);
      expect(project.body.commits[0].message).toBe('upload the project');
      const tree = await call(t.app, 'GET', `/v1/workspaces/${s.workspaceId}/files`, candidateToken);
      expect(tree.body.items.some((f: { path: string }) => f.path === 'FROM_CANDIDATE.txt')).toBe(true);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });

  it('stores an employer zip as the project both sides can read, plus a brief', async () => {
    const created = await call(t.app, 'POST', '/v1/practices', t.employerToken, {
      title: 'Auth service',
      description: 'Fix src/auth so that tests pass.',
      template: 'auth-service',
      deadline: new Date(t.clock.now().getTime() + 3 * 86_400_000).toISOString(),
    });
    const zip = zipStore([
      { name: 'task/src/hello.js', data: 'export const hi = 1;\n' },
      { name: 'task/README.md', data: '# Task\n' },
    ]);
    const uploaded = await t.app.inject({
      method: 'POST',
      url: `/v1/practices/${created.body.id}/project`,
      headers: { authorization: `Bearer ${t.employerToken}`, 'content-type': 'application/zip' },
      payload: zip,
    });
    expect(uploaded.statusCode).toBe(200);
    const files = await call(t.app, 'GET', `/v1/practices/${created.body.id}/files`, t.employerToken);
    expect(files.body.items.map((f: { path: string }) => f.path).sort()).toEqual(['README.md', 'src/hello.js']);
    const file = await call(t.app, 'GET', `/v1/practices/${created.body.id}/file?path=${encodeURIComponent('src/hello.js')}`, t.employerToken);
    expect(file.body.content).toContain('hi');
    const brief = await call(t.app, 'POST', `/v1/practices/${created.body.id}/brief`, t.employerToken, { text: 'Сделайте hello.', name: 'task.md' });
    expect(brief.status).toBe(200);
    const project = await call(t.app, 'GET', `/v1/practices/${created.body.id}/project`, t.employerToken);
    expect(project.body.source).toBe('upload');
    expect(project.body.brief).toBe('Сделайте hello.');
    expect(project.body.briefFilename).toBe('task.md');
    expect(project.body.commits[0].message).toBe('Проект работодателя');
    const timeline = await call(t.app, 'GET', `/v1/practices/${created.body.id}/timeline?limit=5`, t.employerToken);
    expect(timeline.status).toBe(200);
  });

  it('reviews the project and specification, then stores the description and employer notes', async () => {
    const created = await call(t.app, 'POST', '/v1/practices', t.employerToken, {
      title: 'Сборщик логов',
      description: '',
      deadline: new Date(t.clock.now().getTime() + 3 * 86_400_000).toISOString(),
    });
    expect(created.status).toBe(201);
    expect(created.body.description).toBe('');
    const brief = await call(t.app, 'POST', `/v1/practices/${created.body.id}/brief`, t.employerToken, { text: 'Соберите строки лога и посчитайте уровни.' });
    expect(brief.status).toBe(200);
    await t.drain();
    const ai = await call(t.app, 'GET', `/v1/practices/${created.body.id}/ai`, t.employerToken);
    const review = ai.body.materialsReviews.at(-1);
    expect(review.status).toBe('SUCCEEDED');
    expect(review.provider.modelId).toBe('qwen2.5-coder:0.5b');
    expect(review.output.description).toContain('ТЗ.md');
    const applied = await call(t.app, 'POST', `/v1/practices/${created.body.id}/materials`, t.employerToken, {
      description: review.output.description,
      notes: 'Добавьте пример строки лога.',
    });
    expect(applied.status).toBe(200);
    expect(applied.body.description).toBe(review.output.description);
    expect(applied.body.employerNotes).toBe('Добавьте пример строки лога.');
    const improvements = await call(t.app, 'POST', `/v1/practices/${created.body.id}/improvements`, t.employerToken, {});
    expect(improvements.status).toBe(200);
    await t.drain();
    const again = await call(t.app, 'GET', `/v1/practices/${created.body.id}/ai`, t.employerToken);
    const advice = again.body.improvements.at(-1);
    expect(advice.status).toBe('SUCCEEDED');
    expect(advice.output.items[0].title).toBe('Уточнить критерий');
    const project = await call(t.app, 'GET', `/v1/practices/${created.body.id}/project`, t.employerToken);
    expect(project.body.notes).toBe('Добавьте пример строки лога.');
  });
});
