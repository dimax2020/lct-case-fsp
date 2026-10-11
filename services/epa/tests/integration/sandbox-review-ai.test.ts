import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { FakeClock } from '@epa/platform';
import { MockCodeAnalysisProvider, SOLUTION, call, createTestPlatform, futureIso, runSandboxFixture, startPractice, type TestPlatform } from '@epa/test-fixtures';
import type { SandboxDriver } from '@epa/sandbox';

/** Drains the queue repeatedly, advancing the fake clock past retry backoff. */
async function settle(t: TestPlatform, clock: FakeClock, rounds = 6) {
  for (let i = 0; i < rounds; i++) {
    await t.drain();
    clock.advance(120_000);
  }
  await t.drain();
}

async function submit(t: TestPlatform, s: { practiceId: string; candidateToken: string }, key: string) {
  const r = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/submissions`, s.candidateToken, undefined, { 'idempotency-key': key });
  expect([200, 201]).toContain(r.status);
  return r.body;
}

describe('integration: sandbox fixtures', () => {
  let t: TestPlatform;
  let s: Awaited<ReturnType<typeof startPractice>>;
  beforeAll(async () => {
    t = await createTestPlatform();
    s = await startPractice(t);
  });
  afterAll(async () => t?.close());

  it('known-good fixture passes with parsed results', async () => {
    const run = await runSandboxFixture(t, s.practiceId, 'known-good');
    expect(run.status).toBe('PASSED');
    expect(run.summary).toMatchObject({ failed: 0, exitCode: 0 });
    expect(run.summary!.passed).toBeGreaterThan(0);
  });

  it('known-bad fixture fails and names the failing tests', async () => {
    const run = await runSandboxFixture(t, s.practiceId, 'known-bad');
    expect(run.status).toBe('FAILED');
    expect(run.summary!.failed).toBeGreaterThan(0);
    expect(run.summary!.failedTests.length).toBeGreaterThan(0);
  });
});

describe('integration: sandbox infrastructure failure reaches a terminal state', () => {
  let t: TestPlatform;
  let clock: FakeClock;
  let attempts = 0;
  beforeAll(async () => {
    clock = new FakeClock(new Date());
    const broken: SandboxDriver = {
      name: 'local',
      isolated: false,
      async run() {
        attempts++;
        return { exitCode: null, stdout: '', stderr: '', durationMs: 0, timedOut: false, infraError: 'container runtime unavailable' };
      },
    };
    t = await createTestPlatform({ clock, overrides: { sandboxDriver: broken } });
  });
  afterAll(async () => t?.close());

  it('retries, then records UNKNOWN (never PASSED) and dead-letters the job', async () => {
    const s = await startPractice(t);
    const body = await submit(t, s, 'infra-0001');
    await settle(t, clock);
    const run = await call(t.app, 'GET', `/v1/test-runs/${body.testRunId}`, t.employerToken);
    expect(run.body.status).toBe('UNKNOWN');
    expect(run.body.summary.reason).toMatch(/sandbox failure/);
    expect(attempts).toBe(3);
    const dead = await call(t.app, 'GET', '/v1/ops/dead-letters', t.platformToken);
    expect(dead.body.items.some((j: any) => j.kind === 'sandbox.run')).toBe(true);
  });
});

describe('integration: review, versions, requirement change, AI', () => {
  let t: TestPlatform;
  let clock: FakeClock;
  let ai: MockCodeAnalysisProvider;
  let s: Awaited<ReturnType<typeof startPractice>>;
  const ctx: Record<string, any> = {};

  beforeAll(async () => {
    clock = new FakeClock(new Date());
    ai = new MockCodeAnalysisProvider('down');
    t = await createTestPlatform({ clock, ai });
    s = await startPractice(t);
    for (const [p, c] of Object.entries(SOLUTION)) await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, { path: p, content: c });
    await call(t.app, 'POST', `/v1/workspaces/${s.workspaceId}/commits`, s.candidateToken, { message: 'fix' });
  });
  afterAll(async () => t?.close());

  it('AI outage does not block submit: tests still run, analysis ends FAILED with a visible error', async () => {
    const body = await submit(t, s, 'ai-down-1');
    ctx.sub1 = body.submission;
    await settle(t, clock);
    const run = await call(t.app, 'GET', `/v1/test-runs/${body.testRunId}`, t.employerToken);
    expect(run.body.status).toBe('PASSED');
    const list = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/ai`, t.employerToken);
    const a = list.body.analyses.find((x: any) => x.submissionId === ctx.sub1.id);
    expect(a.status).toBe('FAILED');
    expect(a.error).toMatch(/unavailable/);
    const report = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/report`, t.employerToken);
    expect(report.status).toBe(200);
  });

  it('after recovery, hallucinated items (Redis, missing files) are rejected and never shown as questions', async () => {
    ai.mode = 'hallucinate';
    const r = await call(t.app, 'POST', `/v1/submissions/${ctx.sub1.id}/analysis`, t.employerToken);
    expect(r.status).toBe(202);
    await settle(t, clock);
    const list = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/ai`, t.employerToken);
    const a = list.body.analyses.find((x: any) => x.id === r.body.analysisId);
    expect(a.status).toBe('SUCCEEDED');
    expect(JSON.stringify(a.output)).not.toMatch(/redis/i);
    expect(a.output.findings.every((f: any) => f.evidence.file !== 'src/config/keys.js')).toBe(true);
    expect(a.rejected.map((x: any) => x.reason)).toEqual(expect.arrayContaining(['ungrounded_technology', 'unknown_file']));
    expect(a.provider).toMatchObject({ providerId: 'mock', templateVersion: 'prompt-v1', policyVersion: 'ai-policy-v1' });
    const qs = (await call(t.app, 'GET', `/v1/practices/${s.practiceId}/ai`, s.candidateToken)).body;
    expect(qs.questions.length).toBeGreaterThan(0);
    expect(JSON.stringify(qs.questions)).not.toMatch(/redis/i);
    expect(qs.analyses[0].output).toBeUndefined();
    ai.mode = 'grounded';
  });

  it('comment → request changes → new version → resolve; old version stays unchanged', async () => {
    await call(t.app, 'POST', `/v1/practices/${s.practiceId}/review`, t.employerToken);
    const c = await call(t.app, 'POST', `/v1/submissions/${ctx.sub1.id}/comments`, t.employerToken, { filePath: 'src/auth/session.js', lineStart: 1, lineEnd: 2, body: 'Validate ttl' });
    expect(c.status).toBe(201);
    const bad = await call(t.app, 'POST', `/v1/submissions/${ctx.sub1.id}/comments`, t.employerToken, { filePath: 'src/auth/session.js', lineStart: 1, lineEnd: 999, body: 'x' });
    expect(bad.status).toBe(400);
    await call(t.app, 'POST', `/v1/practices/${s.practiceId}/request-changes`, t.employerToken);
    const updated = SOLUTION['src/auth/session.js'].replace('return { userId', "if (!(ttlMs > 0)) throw new RangeError('ttl');\n  return { userId");
    await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, { path: 'src/auth/session.js', content: updated });
    const v2 = await submit(t, s, 'version-0002');
    expect(v2.submission.version).toBe(2);
    expect(v2.submission.baselineSubmissionId).toBe(ctx.sub1.id);
    await settle(t, clock);
    const oldFile = await call(t.app, 'GET', `/v1/snapshots/${ctx.sub1.snapshotId}/file?path=src/auth/session.js`, t.employerToken);
    expect(oldFile.body.content).not.toContain('RangeError');
    await call(t.app, 'POST', `/v1/practices/${s.practiceId}/review`, t.employerToken);
    expect((await call(t.app, 'POST', `/v1/comments/${c.body.id}/resolve`, t.employerToken)).body.status).toBe('RESOLVED');
    ctx.sub2 = v2.submission;
  });

  it('baseline → requirement change → revised submission are linked', async () => {
    const rc = await call(t.app, 'POST', `/v1/practices/${s.practiceId}/requirement-changes`, t.employerToken, {
      text: 'Add a logout function',
      reason: 'Feature',
      acceptanceCriteria: ['logout clears the session'],
      dueAt: futureIso(clock, 1),
    });
    expect(rc.status).toBe(201);
    expect(rc.body.baseline_submission_id ?? rc.body.baselineSubmissionId).toBe(ctx.sub2.id);
    await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, { path: 'src/auth/logout.js', content: 'export function logout(s) {\n  return { ...s, expiresAt: 0 };\n}\n' });
    const v3 = await submit(t, s, 'version-0003');
    expect(v3.submission.requirementChangeId).toBe(rc.body.id);
    const list = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/requirement-changes`, t.employerToken);
    expect(list.body.items[0].revised_submission_id ?? list.body.items[0].revisedSubmissionId).toBe(v3.submission.id);
    await settle(t, clock);
    const ai2 = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/ai`, t.employerToken);
    expect(ai2.body.analyses.find((a: any) => a.submissionId === v3.submission.id).status).toBe('SUCCEEDED');
  });
});
