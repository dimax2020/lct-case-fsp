import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { DIMENSIONS } from '@epa/domain';
import { FakeClock } from '@epa/platform';
import { SOLUTION, call, createTestPlatform, dockerAvailable, futureIso, startPractice, type TestPlatform } from '@epa/test-fixtures';

const drivers = process.env.EPA_E2E_DRIVERS === 'local' || !dockerAvailable() ? 'local' : 'docker';

/** Section 14 general acceptance scenario, executed against the real HTTP API. */
describe(`E2E acceptance scenario (drivers: ${drivers})`, () => {
  let t: TestPlatform;
  let clock: FakeClock;
  let s: Awaited<ReturnType<typeof startPractice>>;
  const ctx: Record<string, any> = {};

  beforeAll(async () => {
    clock = new FakeClock(new Date());
    t = await createTestPlatform({ drivers, clock });
  });
  afterAll(async () => t?.close());

  it('1-3: practice, invite, consent, INVITED → STARTED → IN_PROGRESS, isolated RDE without SSH', async () => {
    s = await startPractice(t);
    const p = await call(t.app, 'GET', `/v1/practices/${s.practiceId}`, t.employerToken);
    expect(p.body.status).toBe('IN_PROGRESS');
    expect(p.body.workspace.driver).toBe(drivers);
    const ws = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/workspace`, s.candidateToken);
    expect(ws.body.sshAccess).toBe(false);
    if (drivers === 'docker') {
      const host = await (t.platform.rdeDriver as any).inspectHostConfig(`epa-${s.workspaceId.replace('_', '-')}`);
      expect(host.NetworkMode).toBe('none');
      expect(host.ReadonlyRootfs).toBe(true);
      expect(host.CapDrop).toContain('ALL');
      expect(host.Privileged).toBe(false);
    }
  });

  it('4: candidate edits src/auth, saves, runs tests, runs a terminal command, commits', async () => {
    const before = await call(t.app, 'POST', `/v1/workspaces/${s.workspaceId}/tests`, s.candidateToken);
    expect(before.status).toBe(200);
    expect(before.body.status).toBe('FAILED');
    expect(before.body.failed).toBe(2);
    clock.advance(5_000);
    for (const [path, content] of Object.entries(SOLUTION)) {
      const w = await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, { path, content, editorStats: { pastedChars: 0 } });
      expect(w.status).toBe(200);
      clock.advance(5_000);
    }
    const after = await call(t.app, 'POST', `/v1/workspaces/${s.workspaceId}/tests`, s.candidateToken);
    expect(after.body.status).toBe('PASSED');
    expect(after.body.passed).toBe(4);
    const cmd = await call(t.app, 'POST', `/v1/workspaces/${s.workspaceId}/commands`, s.candidateToken, { command: 'ls src/auth' });
    expect(cmd.body.exitCode).toBe(0);
    expect(cmd.body.output).toContain('password.js');
    const commit = await call(t.app, 'POST', `/v1/workspaces/${s.workspaceId}/commits`, s.candidateToken, { message: 'Fix password verification and session expiry' });
    expect(commit.status).toBe(201);
    expect(commit.body.changedFiles.sort()).toEqual(['src/auth/password.js', 'src/auth/session.js']);
    ctx.commitSha = commit.body.sha;
  });

  it('5: snapshots/diffs let the employer replay the state before and after the fix', async () => {
    await t.platform.workspaces.flushAll();
    const tl = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/timeline?limit=200`, t.employerToken);
    const types = tl.body.items.map((i: any) => i.type);
    expect(types).toEqual(expect.arrayContaining(['session_started', 'file_changed', 'file_saved', 'test_started', 'test_finished', 'terminal_command', 'git_commit', 'snapshot_created']));
    const snaps = tl.body.items.filter((i: any) => i.type === 'snapshot_created');
    const initial = snaps[0].refs.snapshotId;
    const atCommit = tl.body.items.find((i: any) => i.type === 'git_commit').refs.snapshotId;
    const beforeFix = await call(t.app, 'GET', `/v1/snapshots/${initial}/file?path=src/auth/session.js`, t.employerToken);
    const afterFix = await call(t.app, 'GET', `/v1/snapshots/${atCommit}/file?path=src/auth/session.js`, t.employerToken);
    expect(beforeFix.body.content).toContain('now > session.expiresAt');
    expect(afterFix.body.content).toContain('now >= session.expiresAt');
    const meta = await call(t.app, 'GET', `/v1/snapshots/${atCommit}`, t.employerToken);
    expect(meta.body.kind).toBe('patch');
    expect(meta.body.baseSnapshotId).toBeTruthy();
  });

  it('6: submit creates an immutable submission (idempotent) and tests run in a separate sandbox', async () => {
    const r1 = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/submissions`, s.candidateToken, undefined, { 'idempotency-key': 'submit-0001' });
    expect(r1.status).toBe(201);
    const r2 = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/submissions`, s.candidateToken, undefined, { 'idempotency-key': 'submit-0001' });
    expect(r2.status).toBe(200);
    expect(r2.body.submission.id).toBe(r1.body.submission.id);
    ctx.sub1 = r1.body.submission;
    expect(ctx.sub1.commitSha).toBe(ctx.commitSha);
    const edit = await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, { path: 'src/auth/session.js', content: 'broken' });
    expect(edit.status).toBe(409);
    await t.drain();
    const run = await call(t.app, 'GET', `/v1/test-runs/${r1.body.testRunId}`, t.employerToken);
    expect(run.body.status).toBe('PASSED');
    expect(run.body.summary.passed).toBe(4);
    expect(run.body.summary.failed).toBe(0);
    expect(run.body.summary.driver).toBe(drivers);
    expect(run.body.summary.coverage).toBeNull();
    const link = await call(t.app, 'POST', `/v1/test-runs/${r1.body.testRunId}/log-link`, t.employerToken);
    const log = await call(t.app, 'GET', link.body.url);
    expect(log.status).toBe(200);
    expect(String(log.body)).toMatch(/pass 4/);
  });

  it('7: review → comment → request changes → candidate fixes → resubmits → comment resolved', async () => {
    expect((await call(t.app, 'POST', `/v1/practices/${s.practiceId}/review`, t.employerToken)).body.status).toBe('REVIEW');
    const c = await call(t.app, 'POST', `/v1/submissions/${ctx.sub1.id}/comments`, t.employerToken, { filePath: 'src/auth/password.js', lineStart: 10, lineEnd: 11, body: 'Please also reject **malformed** stored hashes.' });
    expect(c.status).toBe(201);
    ctx.commentId = c.body.id;
    expect((await call(t.app, 'POST', `/v1/practices/${s.practiceId}/request-changes`, t.employerToken)).body.status).toBe('IN_PROGRESS');
    const seen = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/comments`, s.candidateToken);
    expect(seen.body.items[0].status).toBe('OPEN');
    clock.advance(60_000);
    const improved = SOLUTION['src/auth/password.js'].replace("if (!salt || !hash) return false;", "if (typeof stored !== 'string' || !salt || !hash || !/^[0-9a-f]+$/.test(hash)) return false;");
    await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, { path: 'src/auth/password.js', content: improved });
    await call(t.app, 'POST', `/v1/workspaces/${s.workspaceId}/commits`, s.candidateToken, { message: 'Reject malformed stored hashes' });
    const r = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/submissions`, s.candidateToken, undefined, { 'idempotency-key': 'submit-0002' });
    expect(r.body.submission.version).toBe(2);
    expect(r.body.submission.baselineSubmissionId).toBe(ctx.sub1.id);
    ctx.sub2 = r.body.submission;
    await t.drain();
    const old = await call(t.app, 'GET', `/v1/snapshots/${ctx.sub1.snapshotId}/file?path=src/auth/password.js`, t.employerToken);
    expect(old.body.content).not.toContain('/^[0-9a-f]+$/');
    expect((await call(t.app, 'POST', `/v1/practices/${s.practiceId}/review`, t.employerToken)).body.status).toBe('REVIEW');
    const resolved = await call(t.app, 'POST', `/v1/comments/${ctx.commentId}/resolve`, t.employerToken);
    expect(resolved.body.status).toBe('RESOLVED');
    expect(resolved.body.resolvedBy.kind).toBe('employer');
  });

  it('8: AI analysis yields evidence-backed findings and code-specific questions; candidate defends', async () => {
    const ai = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/ai`, t.employerToken);
    const latest = ai.body.analyses.find((a: any) => a.submissionId === ctx.sub2.id);
    expect(latest.status).toBe('SUCCEEDED');
    expect(latest.output.findings.length).toBeGreaterThan(0);
    for (const f of latest.output.findings) expect(f.evidence.file).toMatch(/^src\//);
    const qs = (await call(t.app, 'GET', `/v1/practices/${s.practiceId}/ai`, s.candidateToken)).body.questions.filter((q: any) => q.submissionId === ctx.sub2.id && q.depth === 0);
    expect(qs.length).toBeGreaterThan(0);
    const a = await call(t.app, 'POST', `/v1/interview/questions/${qs[0].id}/answers`, s.candidateToken, { text: 'It splits the stored value, rejects malformed input, and compares with timingSafeEqual to avoid timing leaks.' });
    expect(a.status).toBe(202);
    await t.drain();
    const after = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/ai`, t.employerToken);
    const followUp = after.body.questions.find((q: any) => q.parentQuestionId === qs[0].id);
    expect(followUp).toBeTruthy();
    expect(after.body.questions.find((q: any) => q.id === qs[0].id).answer.evaluation.score).toBeGreaterThan(0);
  });

  it('9: requirement change → candidate adapts → tests and timeline bound to the new version', async () => {
    const rc = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/requirement-changes`, t.employerToken, {
      text: 'Sessions must support sliding expiration via a touchSession function.',
      reason: 'Product wants idle timeout semantics.',
      acceptanceCriteria: ['touchSession extends expiresAt by ttl', 'expired sessions cannot be touched'],
      dueAt: futureIso(clock, 1),
    });
    expect(rc.status).toBe(201);
    const session = SOLUTION['src/auth/session.js'] + `
export function touchSession(session, ttlMs, now = Date.now()) {
  if (isSessionExpired(session, now)) throw new Error('session expired');
  return { ...session, expiresAt: now + ttlMs };
}
`;
    clock.advance(60_000);
    await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, { path: 'src/auth/session.js', content: session });
    await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, {
      path: 'test/touch.test.js',
      content: `import { test } from 'node:test';\nimport assert from 'node:assert/strict';\nimport { createSession, touchSession } from '../src/auth/session.js';\n\ntest('touch extends', () => {\n  const s = touchSession(createSession('u', 100, 0), 100, 50);\n  assert.equal(s.expiresAt, 150);\n});\n\ntest('touch rejects expired', () => {\n  assert.throws(() => touchSession(createSession('u', 100, 0), 100, 100));\n});\n`,
    });
    await call(t.app, 'POST', `/v1/workspaces/${s.workspaceId}/commits`, s.candidateToken, { message: 'Add sliding session expiration' });
    const r = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/submissions`, s.candidateToken, undefined, { 'idempotency-key': 'submit-0003' });
    expect(r.body.submission.requirementChangeId).toBe(rc.body.id);
    ctx.sub3 = r.body.submission;
    await t.drain();
    const run = await call(t.app, 'GET', `/v1/test-runs/${r.body.testRunId}`, t.employerToken);
    expect(run.body.status).toBe('PASSED');
    expect(run.body.summary.passed).toBe(6);
    const ai = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/ai`, s.candidateToken);
    const q = ai.body.questions.find((x: any) => x.submissionId === ctx.sub3.id && x.depth === 0);
    await call(t.app, 'POST', `/v1/interview/questions/${q.id}/answers`, s.candidateToken, { text: 'touchSession refuses expired sessions so idle users must log in again; otherwise it slides the expiry window forward by ttl.' });
    await t.drain();
    expect((await call(t.app, 'POST', `/v1/practices/${s.practiceId}/review`, t.employerToken)).body.status).toBe('REVIEW');
  });

  it('10: evidence-backed profile over eight dimensions; COMPLETED; workspace torn down; retention purges artifacts', async () => {
    const draft = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/assessments`, t.employerToken);
    expect(draft.status).toBe(201);
    expect(draft.body.rubric_version).toBe('rubric-v1');
    const dims = draft.body.dimensions as any[];
    expect(dims.map((d) => d.dimension)).toEqual([...DIMENSIONS]);
    for (const d of dims) {
      expect(d.score).not.toBeNull();
      expect(d.score).toBeGreaterThanOrEqual(0);
      expect(d.score).toBeLessThanOrEqual(100);
      expect(d.evidence.length).toBeGreaterThan(0);
    }
    const report = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/report`, t.employerToken);
    expect(report.body.assessment.label).toMatch(/Recommendation/);
    expect(report.body.submissions).toHaveLength(3);
    expect(report.body.commits.length).toBe(3);
    expect(report.body.testResults.every((r: any) => r.status === 'PASSED')).toBe(true);
    expect(report.body.requirementChanges[0].revisedSubmissionId).toBe(ctx.sub3.id);

    await call(t.app, 'POST', `/v1/assessments/${draft.body.id}/approve`, t.employerToken);
    const done = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/complete`, t.employerToken);
    expect(done.body.status).toBe('COMPLETED');
    await t.drain();
    const p = await call(t.app, 'GET', `/v1/practices/${s.practiceId}`, t.employerToken);
    expect(p.body.workspace.lifecycle).toBe('DESTROYED');
    expect((await call(t.app, 'GET', `/v1/workspaces/${s.workspaceId}/files`, s.candidateToken)).status).toBeGreaterThanOrEqual(400);
    expect((await call(t.app, 'GET', `/v1/snapshots/${ctx.sub1.snapshotId}/file?path=src/auth/session.js`, t.employerToken)).status).toBe(200);

    clock.advance(31 * 86_400_000);
    // Staff and platform credentials are short-lived too; issue fresh ones after the time jump.
    const employer = await t.platform.auth.createStaff(t.orgId, 'lead+later@acme.test', 'employer');
    const auditor = await t.platform.auth.createStaff(t.orgId, 'audit+later@acme.test', 'auditor');
    const purge = await call(t.app, 'POST', '/v1/ops/retention/sweep', await t.platform.auth.platformToken());
    expect(purge.body.purged.map((x: any) => x.practiceId)).toContain(s.practiceId);
    expect((await call(t.app, 'GET', `/v1/snapshots/${ctx.sub1.snapshotId}/file?path=src/auth/session.js`, employer.token)).status).toBe(410);
    expect((await call(t.app, 'GET', `/v1/practices/${s.practiceId}/report`, employer.token)).status).toBe(410);
    const audit = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/audit`, auditor.token);
    expect(audit.body.items.map((a: any) => a.action)).toContain('retention.purged');
    expect(audit.body.chain.ok).toBe(true);
  });
});
