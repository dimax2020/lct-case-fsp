import { mkdir, readFile, readdir, rm } from 'node:fs/promises';
import { buildSnapshotPolicy } from '@epa/domain';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import type { FastifyInstance } from 'fastify';
import { FakeClock, loadConfig, silentLogger, type Clock } from '@epa/platform';
import { buildPlatform, buildServer, type Platform, type PlatformOptions } from '@epa/api';
import type { CodeAnalysisProvider } from '@epa/ai-provider';
import { MockCodeAnalysisProvider } from './mock-ai.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
export const FIXTURES_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const TEMPLATES_DIR = path.join(FIXTURES_DIR, 'templates');
export const SANDBOX_FIXTURES_DIR = path.join(FIXTURES_DIR, 'sandbox');

let dockerChecked: boolean | null = null;
export function dockerAvailable(): boolean {
  if (dockerChecked === null) {
    const r = spawnSync('docker', ['image', 'inspect', 'node:20-alpine'], { stdio: 'ignore', timeout: 15_000 });
    dockerChecked = r.status === 0;
  }
  return dockerChecked;
}

export interface TestPlatform {
  platform: Platform;
  app: FastifyInstance;
  clock: Clock;
  ai: CodeAnalysisProvider;
  dataDir: string;
  orgId: string;
  employerToken: string;
  employerId: string;
  auditorToken: string;
  platformToken: string;
  other: { orgId: string; employerToken: string };
  drain(): Promise<number>;
  close(): Promise<void>;
}

export async function createTestPlatform(
  opts: { drivers?: 'local' | 'docker'; clock?: Clock; ai?: CodeAnalysisProvider; overrides?: Partial<PlatformOptions> } = {},
): Promise<TestPlatform> {
  const drivers = opts.drivers ?? 'local';
  const dataDir = path.join(ROOT, '.tmp', 'test-data', randomUUID());
  await mkdir(dataDir, { recursive: true });
  const config = loadConfig(
    { NODE_ENV: 'test' },
    {
      dataDir,
      databaseUrl: 'memory://',
      templatesDir: TEMPLATES_DIR,
      rdeDriver: drivers,
      sandboxDriver: drivers,
      embeddedWorker: false,
    },
  );
  const clock = opts.clock ?? new FakeClock(new Date());
  const ai = opts.ai ?? new MockCodeAnalysisProvider();
  const platform = await buildPlatform({ config, clock, logger: silentLogger, aiProvider: ai, ...opts.overrides });
  const app = await buildServer(platform);
  const orgId = await platform.auth.createOrganisation('Acme', 30);
  const employer = await platform.auth.createStaff(orgId, 'lead@acme.test', 'employer');
  const auditor = await platform.auth.createStaff(orgId, 'audit@acme.test', 'auditor');
  const otherOrg = await platform.auth.createOrganisation('Globex', 30);
  const otherEmployer = await platform.auth.createStaff(otherOrg, 'lead@globex.test', 'employer');
  const platformToken = await platform.auth.platformToken();
  return {
    platform,
    app,
    clock,
    ai,
    dataDir,
    orgId,
    employerToken: employer.token,
    employerId: employer.id,
    auditorToken: auditor.token,
    platformToken,
    other: { orgId: otherOrg, employerToken: otherEmployer.token },
    drain: () => platform.worker.drain(),
    async close() {
      // Tear down any RDE containers this test created before dropping state.
      const ws = await platform.ctx.db.query<{ runtime_ref: string | null }>(`SELECT runtime_ref FROM workspaces WHERE lifecycle <> 'DESTROYED'`).catch(() => []);
      for (const w of ws) if (w.runtime_ref) await platform.rdeDriver.teardown(w.runtime_ref).catch(() => undefined);
      await app.close();
      await platform.close();
      await rm(dataDir, { recursive: true, force: true });
    },
  };
}

export interface ApiResponse<T = any> {
  status: number;
  body: T;
  headers: Record<string, unknown>;
}

export async function call<T = any>(
  app: FastifyInstance,
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  url: string,
  token?: string | null,
  body?: unknown,
  headers: Record<string, string> = {},
): Promise<ApiResponse<T>> {
  const res = await app.inject({
    method,
    url,
    headers: { ...(token ? { authorization: `Bearer ${token}` } : {}), ...(body !== undefined ? { 'content-type': 'application/json' } : {}), ...headers },
    payload: body === undefined ? undefined : JSON.stringify(body),
  });
  let parsed: any = res.body;
  try {
    parsed = JSON.parse(res.body);
  } catch {}
  return { status: res.statusCode, body: parsed, headers: res.headers as Record<string, unknown> };
}

/** A `fetch` implementation that routes requests into the Fastify app (for HttpTransport in tests). */
export function injectFetch(app: FastifyInstance): typeof fetch {
  return (async (url: string | URL, init: RequestInit = {}) => {
    const u = new URL(String(url));
    const res = await app.inject({ method: (init.method ?? 'GET') as any, url: u.pathname + u.search, headers: init.headers as Record<string, string>, payload: init.body as string | undefined });
    return new Response(res.body, { status: res.statusCode, headers: { 'content-type': String(res.headers['content-type'] ?? 'application/json') } });
  }) as typeof fetch;
}

export const SOLUTION = {
  'src/auth/password.js': `import { randomBytes, scryptSync, timingSafeEqual } from 'node:crypto';

export function hashPassword(password) {
  const salt = randomBytes(16).toString('hex');
  const hash = scryptSync(password, salt, 32).toString('hex');
  return \`\${salt}:\${hash}\`;
}

export function verifyPassword(password, stored) {
  const [salt, hash] = stored.split(':');
  if (!salt || !hash) return false;
  const candidate = scryptSync(password, salt, 32);
  const expected = Buffer.from(hash, 'hex');
  return candidate.length === expected.length && timingSafeEqual(candidate, expected);
}
`,
  'src/auth/session.js': `export function createSession(userId, ttlMs, now = Date.now()) {
  return { userId, createdAt: now, expiresAt: now + ttlMs };
}

export function isSessionExpired(session, now = Date.now()) {
  return now >= session.expiresAt;
}
`,
};

async function readDirFiles(root: string, rel = ''): Promise<{ path: string; contentBase64: string }[]> {
  const out: { path: string; contentBase64: string }[] = [];
  for (const e of await readdir(path.join(root, rel), { withFileTypes: true })) {
    const p = rel ? `${rel}/${e.name}` : e.name;
    if (e.isDirectory()) out.push(...(await readDirFiles(root, p)));
    else out.push({ path: p, contentBase64: (await readFile(path.join(root, p))).toString('base64') });
  }
  return out;
}

/** Snapshots a sandbox fixture directory and runs it through the real orchestrator + job worker. */
export async function runSandboxFixture(t: TestPlatform, practiceId: string, fixture: string, command = ['node', '--test']) {
  const files = await readDirFiles(path.join(SANDBOX_FIXTURES_DIR, fixture));
  const { snapshot } = await t.platform.snapshots.createFromUpload(practiceId, files, 'manual', buildSnapshotPolicy({ maxFileBytes: 1024 * 1024 }));
  const runId = await t.platform.sandbox.enqueue(t.platform.ctx.db, { practiceId, snapshotId: snapshot.id, submissionId: null, command });
  await t.drain();
  return t.platform.sandbox.get(runId);
}

export const futureIso = (clock: Clock, days: number) => new Date(clock.now().getTime() + days * 86_400_000).toISOString();

/** Employer creates a practice, invites; candidate redeems, consents and starts; provisioning job runs. */
export async function startPractice(t: TestPlatform, opts: { deadlineDays?: number; snapshotPolicy?: Record<string, number> } = {}) {
  const created = await call(t.app, 'POST', '/v1/practices', t.employerToken, {
    title: 'Auth service',
    description: 'Fix src/auth so that tests pass.',
    template: 'auth-service',
    deadline: futureIso(t.clock, opts.deadlineDays ?? 3),
    ...(opts.snapshotPolicy ? { snapshotPolicy: opts.snapshotPolicy } : {}),
  });
  if (created.status !== 201) throw new Error(`create practice failed: ${JSON.stringify(created.body)}`);
  const practiceId = created.body.id as string;
  const invite = await call(t.app, 'POST', `/v1/practices/${practiceId}/invitations`, t.employerToken, { candidateEmail: 'cand@example.test' });
  const redeemed = await call(t.app, 'POST', '/v1/invitations/redeem', null, { token: invite.body.token });
  if (redeemed.status !== 200) throw new Error(`redeem failed: ${JSON.stringify(redeemed.body)}`);
  const candidateToken = redeemed.body.candidateToken as string;
  const notice = redeemed.body.consentNotice;
  const consent = await call(t.app, 'POST', `/v1/practices/${practiceId}/consent`, candidateToken, { consentVersion: notice.version, textHash: notice.textHash, accepted: true });
  if (consent.status !== 200) throw new Error(`consent failed: ${JSON.stringify(consent.body)}`);
  const started = await call(t.app, 'POST', `/v1/practices/${practiceId}/start`, candidateToken);
  if (started.status !== 202) throw new Error(`start failed: ${JSON.stringify(started.body)}`);
  await t.drain();
  const ws = await call(t.app, 'GET', `/v1/practices/${practiceId}/workspace`, candidateToken);
  return { practiceId, candidateToken, workspaceId: ws.body.workspaceId as string, inviteToken: invite.body.token as string, candidateId: redeemed.body.candidateId as string };
}
