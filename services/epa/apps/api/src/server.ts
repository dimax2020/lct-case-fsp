import Fastify, { type FastifyInstance, type FastifyReply, type FastifyRequest } from 'fastify';
import { createWriteStream } from 'node:fs';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { PassThrough, Transform } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { ZodError, type ZodType } from 'zod';
import { authorize, requireKind, type Principal } from '@epa/authz';
import {
  acceptConsentReq,
  commitReq,
  createCommentReq,
  createInviteReq,
  briefReq,
  materialsReq,
  createPracticeReq,
  fileQuery,
  interviewAnswerReq,
  loginReq,
  paginationQuery,
  redeemInviteReq,
  extensionCredentialsReq,
  extensionLoginReq,
  registerReq,
  requirementChangeReq,
  runCommandReq,
  writeFileReq,
} from '@epa/contracts';
import { DomainError, buildSnapshotPolicy, isDomainError, notFound } from '@epa/domain';
import { scopeOf, type PracticeRow } from '@epa/practice';
import { canonicalJson, sha256Hex } from '@epa/telemetry';
import type { Platform } from './container.js';

declare module 'fastify' {
  interface FastifyRequest {
    principal: Principal | null;
    startedAt: number;
  }
}

const WEB_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../web/public');
const STATIC_FILES: Record<string, string> = {
  '/': 'index.html',
  '/index.html': 'index.html',
  '/employer.html': 'employer.html',
  '/candidate.html': 'candidate.html',
  '/app.css': 'app.css',
  '/common.js': 'common.js',
  '/employer.js': 'employer.js',
  '/candidate.js': 'candidate.js',
};
const CONTENT_TYPES: Record<string, string> = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8' };

function parse<T>(schema: ZodType<T>, value: unknown): T {
  try {
    return schema.parse(value);
  } catch (e) {
    if (e instanceof ZodError) {
      throw new DomainError('VALIDATION', 'request validation failed', { issues: e.issues.slice(0, 10).map((i) => `${i.path.join('.') || '(root)'}: ${i.message}`) });
    }
    throw e;
  }
}

const bearer = (req: FastifyRequest) => {
  const h = req.headers.authorization;
  return h && h.startsWith('Bearer ') ? h.slice(7).trim() : undefined;
};

export function presentPractice(p: PracticeRow, people?: { candidateEmail: string | null; invitedEmail: string | null; invited?: boolean }, vacancyIds?: string[]) {
  return {
    id: p.id,
    title: p.title,
    description: p.description,
    rules: p.rules,
    brief: p.brief ?? null,
    briefFilename: p.brief_filename ?? null,
    employerNotes: p.employer_notes ?? null,
    projectSource: p.project_source ?? 'template',
    vacancyId: p.vacancy_id ?? null,
    vacancyIds: vacancyIds ?? (p.vacancy_id ? [p.vacancy_id] : []),
    sourcePracticeId: p.source_practice_id ?? null,
    candidateEmail: people?.candidateEmail ?? null,
    invitedEmail: people?.invitedEmail ?? null,
    invited: people?.invited ?? false,
    template: p.template,
    taskVersion: p.task_version,
    status: p.status,
    deadline: p.deadline,
    candidateId: p.candidate_id,
    workspaceId: p.workspace_id,
    testCommand: p.test_command,
    coverage: p.coverage,
    snapshotPolicy: p.snapshot_policy,
    terminalAt: p.terminal_at,
    purgedAt: p.purged_at,
    createdAt: p.created_at,
    updatedAt: p.updated_at,
  };
}

export async function buildServer(platform: Platform): Promise<FastifyInstance> {
  const { ctx } = platform;
  const app = Fastify({ logger: false, bodyLimit: 32 * 1024 * 1024, trustProxy: false, routerOptions: { maxParamLength: 1024 }, genReqId: () => randomUUID() });
  const archiveLimit = 4 * 1024 * 1024 * 1024;
  const pushLimit = 2 * 1024 * 1024 * 1024;
  const spool = async (payload: NodeJS.ReadableStream, limit: number) => {
    const dir = await mkdtemp(path.join(os.tmpdir(), 'epa-upload-'));
    const file = path.join(dir, 'body');
    let bytes = 0;
    try {
      await pipeline(
        payload,
        new Transform({
          transform(chunk, _enc, cb) {
            bytes += chunk.length;
            if (bytes > limit) {
              const err = new Error('файл больше допустимого размера') as Error & { statusCode: number; code: string };
              err.statusCode = 413;
              err.code = 'FST_ERR_CTP_BODY_TOO_LARGE';
              cb(err);
              return;
            }
            cb(null, chunk);
          },
        }),
        createWriteStream(file),
      );
    } catch (e) {
      await rm(dir, { recursive: true, force: true });
      throw e;
    }
    return { dir, file, bytes };
  };
  const gitBody = (_req: FastifyRequest, body: Buffer, done: (err: null, body: Buffer) => void) => done(null, body);
  app.addContentTypeParser('application/x-git-upload-pack-request', { parseAs: 'buffer' }, gitBody);
  app.addContentTypeParser('application/x-git-receive-pack-request', (req, payload, done) => {
    spool(payload, pushLimit).then((saved) => done(null, saved), done);
  });
  app.addContentTypeParser('application/zip', (req, payload, done) => {
    spool(payload, archiveLimit).then((saved) => done(null, saved), done);
  });

  app.decorateRequest('principal', null);
  app.decorateRequest('startedAt', 0);

  app.addHook('onRequest', async (req, reply) => {
    req.startedAt = Date.now();
    reply.header('x-request-id', req.id);
    reply.header('x-content-type-options', 'nosniff');
    reply.header('referrer-policy', 'no-referrer');
    reply.header('x-frame-options', 'DENY');
    reply.header('cache-control', 'no-store');
    reply.header('content-security-policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
    req.principal = await platform.auth.authenticate(bearer(req));
    if (req.url.startsWith('/v1/')) {
      const key = req.principal ? `${req.principal.kind}:${req.principal.id}` : `ip:${req.ip}`;
      (req.url.startsWith('/v1/agent/') ? platform.limits.ingest : platform.limits.api).consume(key);
    }
  });

  app.addHook('onResponse', async (req, reply) => {
    const route = req.routeOptions?.url ?? 'unmatched';
    ctx.metrics.inc('http_requests_total', { route, method: req.method, status: String(reply.statusCode) });
    ctx.metrics.observe('http_request_duration_ms', Date.now() - req.startedAt, { route });
    if (reply.statusCode >= 500) ctx.log.error('request failed', { requestId: req.id, route, status: reply.statusCode });
  });

  app.setErrorHandler((err: any, req, reply) => {
    if (isDomainError(err)) {
      if (err.code === 'RATE_LIMITED' && err.details?.retryAfterSec) reply.header('retry-after', String(err.details.retryAfterSec));
      return reply.status(err.httpStatus).send({ error: { code: err.code, message: err.message, details: err.details } });
    }
    if (err?.statusCode === 413 || err?.code === 'FST_ERR_CTP_BODY_TOO_LARGE') {
      return reply.status(413).send({ error: { code: 'PAYLOAD_TOO_LARGE', message: 'файл больше допустимого размера' } });
    }
    if (err?.statusCode === 400 || err?.validation) return reply.status(400).send({ error: { code: 'VALIDATION', message: 'malformed request' } });
    if (err?.code === '42501') return reply.status(403).send({ error: { code: 'FORBIDDEN', message: 'immutable record' } });
    ctx.log.error('unhandled error', { requestId: req.id, error: String(err?.message ?? err), stack: String(err?.stack ?? '').slice(0, 1500) });
    return reply.status(500).send({ error: { code: 'INTERNAL', message: 'internal error', requestId: req.id } });
  });

  app.get('/extension/epa-vscode.vsix', async (_req, reply) => {
    const file = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../extensions/vscode/epa-vscode.vsix');
    try {
      const body = await readFile(file);
      return reply
        .header('content-type', 'application/octet-stream')
        .header('content-disposition', 'attachment; filename="epa-vscode.vsix"')
        .send(body);
    } catch {
      return reply.status(404).send({ error: { code: 'NOT_FOUND', message: 'extension package is not built yet' } });
    }
  });

  // ---------- Static web UI ----------
  for (const [route, file] of Object.entries(STATIC_FILES)) {
    app.get(route, async (_req, reply) => {
      const body = await readFile(path.join(WEB_DIR, file));
      return reply.header('content-type', CONTENT_TYPES[path.extname(file)]).send(body);
    });
  }

  // ---------- Health & ops ----------
  app.get('/healthz', async () => {
    await ctx.db.query('SELECT 1');
    return { ok: true, rdeDriver: platform.rdeDriver.name, sandboxDriver: platform.sandboxDriver.name, isolated: platform.rdeDriver.isolated && platform.sandboxDriver.isolated };
  });
  app.get('/metrics', async (req, reply) => {
    requireKind(req.principal, 'platform');
    const depth = await ctx.jobs.depth();
    for (const [status, n] of Object.entries(depth)) ctx.metrics.gauge('jobs_queue_depth', n, { status });
    return reply.header('content-type', 'text/plain; version=0.0.4').send(ctx.metrics.render());
  });
  app.get('/v1/ops/dead-letters', async (req) => {
    requireKind(req.principal, 'platform');
    return { items: (await ctx.jobs.deadLetters()).map((j) => ({ id: j.id, kind: j.kind, attempts: j.attempts, lastError: j.last_error, payload: j.payload })) };
  });
  app.post('/v1/ops/retention/sweep', async (req) => ({ purged: await platform.retention.sweepAs(req.principal) }));

  // ---------- Name entry (the browser keeps the session; the person never sees a token) ----------
  app.post('/v1/auth/login', async (req) => {
    platform.limits.redeem.consume(`login:${req.ip}`);
    const body = parse(loginReq, req.body);
    return platform.auth.enterByName(body.name, body.role);
  });
  app.get('/v1/invitations/preview', async (req) => {
    const token = String((req.query as { token?: string }).token ?? '');
    return platform.practices.previewInvitation(token);
  });
  app.post('/v1/auth/register', async (req) => {
    platform.limits.redeem.consume(`register:${req.ip}`);
    const body = parse(registerReq, req.body);
    const session = await platform.practices.registerFromInvite(body.token, body.name, body.username, body.password);
    const me = await platform.auth.me({ kind: 'candidate', id: session.candidateId });
    return { candidateToken: session.candidateToken, practiceId: session.practiceId, consentNotice: session.consentNotice, email: me.email, username: me.username };
  });
  app.post('/v1/auth/extension-credentials', async (req) => {
    const candidate = requireKind(req.principal, 'candidate');
    const body = parse(extensionCredentialsReq, req.body);
    const username = await platform.auth.setExtensionCredentials(candidate.id, body.username, body.password);
    return { username };
  });
  app.get('/v1/me', async (req) => platform.auth.me(req.principal));

  app.get('/v1/ai/settings', async (req) => {
    requireKind(req.principal, 'employer', 'candidate', 'auditor');
    return platform.aiSettings.view();
  });
  app.put('/v1/ai/settings', async (req) => {
    requireKind(req.principal, 'employer', 'candidate', 'auditor');
    return platform.aiSettings.update((req.body ?? {}) as { apiKey?: unknown; provider?: unknown });
  });
  app.post('/v1/ai/local-model', async (req) => {
    requireKind(req.principal, 'employer', 'candidate', 'auditor');
    return platform.aiSettings.startPull();
  });

  app.get('/v1/practices/:id/project', async (req) => {
    const p = await platform.practices.authorized(req.principal, 'practice:read', (req.params as any).id);
    const commits = await platform.git.log(p.id, 20);
    const candidate = p.candidate_id
      ? await ctx.db.one<{ identity: string }>('SELECT identity FROM candidates WHERE id = $1', [p.candidate_id])
      : null;
    return {
      remote: `${platform.config.publicUrl}/git/${p.id}.git`,
      candidateEmail: candidate?.identity ?? null,
      source: p.project_source ?? 'template',
      brief: p.brief ?? null,
      briefFilename: p.brief_filename ?? null,
      notes: p.employer_notes ?? null,
      commits: commits.map((c) => ({ sha: c.sha, author: c.author, message: c.message, committedAt: c.committedAt })),
    };
  });

  app.get('/v1/practices/:id/files', async (req) => {
    const p = await platform.practices.authorized(req.principal, 'practice:read', (req.params as any).id);
    return { items: await platform.git.listTree(p.id) };
  });
  app.get('/v1/practices/:id/file', async (req) => {
    const p = await platform.practices.authorized(req.principal, 'practice:read', (req.params as any).id);
    const filePath = String((req.query as { path?: string }).path ?? '');
    return platform.git.readBlob(p.id, filePath);
  });
  app.post('/v1/practices/:id/brief', async (req) => {
    const body = parse(briefReq, req.body);
    await platform.practices.setBrief(req.principal, (req.params as any).id, body.text, body.name);
    if (body.review !== false) await platform.ai.enqueueMaterialsReview((req.params as any).id);
    return { ok: true };
  });
  app.post('/v1/practices/:id/materials', async (req) => {
    const body = parse(materialsReq, req.body);
    return presentPractice(await platform.practices.setMaterials(req.principal, (req.params as any).id, body));
  });
  const extractProgress = new Map<string, { done: number; total: number }>();
  app.post('/v1/practices/:id/project', async (req) => {
    const id = (req.params as { id: string }).id;
    const zip = req.body as { dir?: string; file?: string; bytes?: number };
    if (!zip?.file || !zip.dir) throw new DomainError('VALIDATION', 'приложите zip-архив проекта');
    try {
    if ((zip.bytes ?? 0) < 22) throw new DomainError('VALIDATION', 'приложите zip-архив проекта');
    await platform.practices.authorized(req.principal, 'practice:invite', id);
    const imported = await platform.git.importArchive(id, zip.file, 'Проект работодателя', (done, total) => {
      extractProgress.set(id, { done, total });
    });
    const practice = await platform.practices.markProjectUploaded(req.principal, id);
    await platform.ai.enqueueMaterialsReview(id);
    if (practice.workspace_id) {
      try {
        const lay = platform.workspaces.layout(practice.workspace_id);
        await platform.git.checkoutWorkspace(id, lay.repository, lay.gitDir);
      } catch (e) {
        ctx.log.warn('workspace sync skipped', { practiceId: id, error: e instanceof Error ? e.message : String(e) });
      }
    }
    return { ok: true, source: 'upload', files: imported.files, skipped: imported.skipped };
    } finally {
      extractProgress.delete(id);
      await rm(zip.dir, { recursive: true, force: true });
    }
  });
  app.get('/v1/practices/:id/setup-progress', async (req) => {
    const id = (req.params as { id: string }).id;
    await platform.practices.authorized(req.principal, 'practice:read', id);
    return { extract: extractProgress.get(id) ?? null };
  });

  // ---------- Git smart HTTP: clone and push without a password ----------
  const practiceRepo = (repo: string) => {
    const id = repo.replace(/\.git$/, '');
    if (!/^prc_[a-f0-9]{32}$/.test(id)) throw notFound('repository');
    return id;
  };
  const pkt = (text: string) => {
    const data = Buffer.from(text);
    return Buffer.concat([Buffer.from((data.length + 4).toString(16).padStart(4, '0')), data]);
  };
  app.get('/git/:repo/info/refs', async (req, reply) => {
    const practiceId = practiceRepo((req.params as { repo: string }).repo);
    const service = String((req.query as { service?: string }).service ?? '');
    if (service !== 'git-upload-pack' && service !== 'git-receive-pack') throw new DomainError('FORBIDDEN', 'unsupported git service');
    await platform.practices.load(practiceId);
    const kind = service === 'git-upload-pack' ? 'upload-pack' : 'receive-pack';
    const advertised = await platform.git.httpRpc(practiceId, kind, null, true);
    const body = Buffer.concat([pkt(`# service=${service}\n`), Buffer.from('0000'), advertised]);
    return reply
      .header('content-type', `application/x-${service}-advertisement`)
      .header('cache-control', 'no-cache')
      .send(body);
  });
  app.post('/git/:repo/git-upload-pack', async (req, reply) => {
    const practiceId = practiceRepo((req.params as { repo: string }).repo);
    await platform.practices.load(practiceId);
    const streamed = await platform.git.streamRpc(practiceId, 'upload-pack', req.body as Buffer);
    void streamed.finished.catch((e) => ctx.log.warn('git upload-pack failed', { practiceId, error: e instanceof Error ? e.message : String(e) }));
    return reply.header('content-type', 'application/x-git-upload-pack-result').header('cache-control', 'no-cache').send(streamed.stdout);
  });
  app.post('/git/:repo/git-receive-pack', async (req, reply) => {
    const practiceId = practiceRepo((req.params as { repo: string }).repo);
    const practice = await platform.practices.load(practiceId);
    const pushed = req.body as { dir?: string; file?: string };
    if (!pushed?.file || !pushed.dir) throw new DomainError('VALIDATION', 'пустой push');
    const streamed = await platform.git.streamRpc(practiceId, 'receive-pack', pushed.file);
    const pass = new PassThrough();
    streamed.stdout.pipe(pass, { end: false });
    streamed.stdout.on('error', (e) => pass.destroy(e));
    void streamed.finished
      .then(async () => {
        if (practice.workspace_id) {
          try {
            const lay = platform.workspaces.layout(practice.workspace_id);
            await platform.git.checkoutWorkspace(practiceId, lay.repository, lay.gitDir);
          } catch (e) {
            ctx.log.warn('workspace sync skipped', { practiceId, error: e instanceof Error ? e.message : String(e) });
          }
        }
        const tmp = await mkdtemp(path.join(os.tmpdir(), 'epa-push-'));
        try {
          await platform.git.materialize(practiceId, tmp);
          await platform.snapshots.captureWorkspace(practiceId, tmp, 'git_commit', buildSnapshotPolicy(practice.snapshot_policy as any));
        } catch (e) {
          ctx.log.warn('push snapshot skipped', { practiceId, error: e instanceof Error ? e.message : String(e) });
        } finally {
          await rm(tmp, { recursive: true, force: true });
        }
      })
      .catch((e) => ctx.log.warn('git receive-pack failed', { practiceId, error: e instanceof Error ? e.message : String(e) }))
      .finally(() => {
        pass.end();
        void rm(pushed.dir!, { recursive: true, force: true });
      });
    return reply.header('content-type', 'application/x-git-receive-pack-result').header('cache-control', 'no-cache').send(pass);
  });

  // ---------- Employer: practices & invitations ----------
  app.get('/v1/templates', async (req) => {
    requireKind(req.principal, 'employer');
    return { items: await platform.templates.list() };
  });

  app.post('/v1/practices', async (req, reply) => {
    const body = parse(createPracticeReq, req.body);
    const key = req.headers['idempotency-key'];
    const principal = requireKind(req.principal, 'employer');
    if (typeof key === 'string' && key) {
      const scope = `create_practice:${principal.id}`;
      const reqHash = sha256Hex(canonicalJson(body));
      const prev = await ctx.db.one<any>('SELECT * FROM idempotency_keys WHERE scope = $1 AND key = $2', [scope, key]);
      if (prev) {
        if (prev.request_hash !== reqHash) throw new DomainError('CONFLICT', 'idempotency key reused with a different request');
        return reply.status(200).send(prev.response);
      }
      const created = presentPractice(await platform.practices.create(principal, body));
      await ctx.db.query('INSERT INTO idempotency_keys (scope, key, request_hash, response, created_at) VALUES ($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING', [scope, key, reqHash, JSON.stringify(created), ctx.clock.now()]);
      return reply.status(201).send(created);
    }
    return reply.status(201).send(presentPractice(await platform.practices.create(principal, body)));
  });

  app.get('/v1/practices', async (req) => {
    const q = parse(paginationQuery, req.query);
    const page = await platform.practices.list(req.principal, q.cursor, q.limit);
    const people = await platform.practices.people(page.items);
    const linked = await platform.practices.vacancyMap(page.items.map((p) => p.id));
    return { items: page.items.map((p) => presentPractice(p, people.get(p.id), linked.get(p.id) ?? [])), nextCursor: page.nextCursor };
  });

  app.get('/v1/practices/:id', async (req) => {
    const p = await platform.practices.authorized(req.principal, 'practice:read', (req.params as any).id);
    const ws = p.workspace_id ? await ctx.db.one<any>('SELECT id, lifecycle, driver, expires_at, failure_reason, policy_version FROM workspaces WHERE id = $1', [p.workspace_id]) : null;
    const people = await platform.practices.people([p]);
    const linked = await platform.practices.vacancyMap([p.id]);
    return { ...presentPractice(p, people.get(p.id), linked.get(p.id) ?? []), workspace: ws, retentionUntil: await platform.practices.retentionUntil(p) };
  });

  app.delete('/v1/practices/:id', async (req, reply) => {
    const id = (req.params as { id: string }).id;
    const p = await platform.practices.authorized(req.principal, 'practice:invite', id);
    if (p.workspace_id) {
      await platform.workspaces.teardown(id, 'deleted').catch((e) => {
        ctx.log.warn('workspace teardown skipped', { practiceId: id, error: e instanceof Error ? e.message : String(e) });
      });
      await rm(platform.workspaces.layout(p.workspace_id).root, { recursive: true, force: true }).catch(() => undefined);
    }
    await platform.git.deletePracticeRepo(id);
    await platform.practices.purge(req.principal, id);
    return reply.status(204).send();
  });

  app.post('/v1/practices/:id/invitations', async (req, reply) => {
    const body = parse(createInviteReq, req.body);
    return reply.status(201).send(await platform.practices.createInvitation(req.principal, (req.params as any).id, body));
  });

  app.put('/v1/practices/:id/vacancy', async (req) => {
    const body = (req.body ?? {}) as { vacancyId?: unknown; vacancyIds?: unknown };
    const vacancyIds = Array.isArray(body.vacancyIds)
      ? body.vacancyIds.filter((id): id is string => typeof id === 'string')
      : typeof body.vacancyId === 'string' ? [body.vacancyId] : [];
    const p = await platform.practices.attachVacancy(req.principal, (req.params as { id: string }).id, vacancyIds);
    const people = await platform.practices.people([p]);
    const linked = await platform.practices.vacancyMap([p.id]);
    return presentPractice(p, people.get(p.id), linked.get(p.id) ?? []);
  });

  app.get('/v1/practices/:id/attempts', async (req) => {
    const rows = await platform.practices.attempts(req.principal, (req.params as { id: string }).id);
    const people = await platform.practices.people(rows);
    return { items: rows.map((p) => presentPractice(p, people.get(p.id))) };
  });

  app.post('/v1/vacancy-tasks/lookup', async (req) => {
    const raw = (req.body as { vacancyIds?: unknown } | null)?.vacancyIds;
    const vacancyIds = Array.isArray(raw) ? raw.filter((id): id is string => typeof id === 'string') : [];
    return { vacancyIds: await platform.practices.vacanciesWithTasks(vacancyIds) };
  });

  app.post('/v1/vacancies/:vacancyId/join', async (req) => {
    const { practice, copyRepoFrom } = await platform.practices.joinVacancy(req.principal, (req.params as { vacancyId: string }).vacancyId);
    if (copyRepoFrom) await platform.git.cloneBare(copyRepoFrom, practice.id).catch(() => undefined);
    const people = await platform.practices.people([practice]);
    return presentPractice(practice, people.get(practice.id));
  });

  app.post('/v1/practices/:id/join', async (req) => {
    const { practice, copyRepoFrom } = await platform.practices.joinPractice(req.principal, (req.params as { id: string }).id);
    if (copyRepoFrom) await platform.git.cloneBare(copyRepoFrom, practice.id).catch(() => undefined);
    const people = await platform.practices.people([practice]);
    return presentPractice(practice, people.get(practice.id));
  });

  // ---------- Candidate: invite, consent, start ----------
  app.post('/v1/invitations/redeem', async (req) => {
    platform.limits.redeem.consume(`redeem:${req.ip}`);
    const body = parse(redeemInviteReq, req.body);
    return platform.practices.redeemInvitation(body.token);
  });

  app.get('/v1/practices/:id/consent-notice', async (req) => platform.practices.getConsentNotice(req.principal, (req.params as any).id));

  app.post('/v1/practices/:id/consent', async (req) => {
    const body = parse(acceptConsentReq, req.body);
    return platform.practices.acceptConsent(req.principal, (req.params as any).id, body);
  });

  app.post('/v1/practices/:id/start', async (req, reply) => {
    const p = await platform.practices.start(req.principal, (req.params as any).id);
    return reply.status(202).send(presentPractice(p));
  });

  app.post('/v1/practices/:id/vscode-link', async (req) => platform.workspaces.issueVscodeLink(req.principal, (req.params as any).id));
  app.get('/v1/practices/:id/vscode', async (req) => {
    const p = await platform.practices.authorized(req.principal, 'practice:timeline', (req.params as any).id);
    return platform.workspaces.vscodeStatus(p.id);
  });

  app.get('/v1/practices/:id/workspace', async (req) => {
    const p = await platform.practices.authorized(req.principal, 'practice:work', (req.params as any).id);
    if (!p.workspace_id) throw new DomainError('CONFLICT', 'practice has not been started');
    const ws = await platform.workspaces.getRow(p.workspace_id);
    return { workspaceId: ws.id, lifecycle: ws.lifecycle, expiresAt: ws.expires_at, failureReason: ws.failure_reason, idePath: `/candidate.html#practice=${p.id}`, sshAccess: false };
  });

  // ---------- Workspace gateway (browser IDE) ----------
  app.get('/v1/workspaces/:id/files', async (req) => ({ items: await platform.workspaces.listFiles(req.principal, (req.params as any).id) }));
  app.get('/v1/workspaces/:id/file', async (req) => {
    const q = parse(fileQuery, req.query);
    return { path: q.path, content: await platform.workspaces.readFile(req.principal, (req.params as any).id, q.path) };
  });
  app.put('/v1/workspaces/:id/file', async (req) => platform.workspaces.writeFile(req.principal, (req.params as any).id, parse(writeFileReq, req.body)));
  app.delete('/v1/workspaces/:id/file', async (req) => platform.workspaces.deleteFile(req.principal, (req.params as any).id, parse(fileQuery, req.query).path));
  app.post('/v1/workspaces/:id/commands', async (req) => platform.workspaces.runCommand(req.principal, (req.params as any).id, parse(runCommandReq, req.body).command));
  app.post('/v1/workspaces/:id/tests', async (req) => platform.workspaces.runTests(req.principal, (req.params as any).id));
  app.post('/v1/workspaces/:id/commits', async (req, reply) => reply.status(201).send(await platform.workspaces.commit(req.principal, (req.params as any).id, parse(commitReq, req.body).message)));

  // ---------- Submit ----------
  app.post('/v1/practices/:id/submissions', async (req, reply) => {
    const key = req.headers['idempotency-key'];
    const r = await platform.submissions.submit(req.principal, (req.params as any).id, typeof key === 'string' ? key : '');
    return reply.status(r.created ? 201 : 200).send({ submission: presentSubmission(r.submission), testRunId: r.testRunId, created: r.created });
  });
  app.get('/v1/practices/:id/submissions', async (req) => {
    const p = await platform.practices.authorized(req.principal, 'practice:timeline', (req.params as any).id);
    return { items: (await platform.submissions.list(p.id)).map(presentSubmission) };
  });

  // ---------- Workspace agent (out-of-process) ----------
  app.post('/v1/agent/events:batch', async (req, reply) => {
    const r = await platform.ingestion.ingest(req.principal, req.body);
    return reply.status(r.gap ? 409 : 200).send(r);
  });
  app.post('/v1/agent/snapshots', async (req, reply) => {
    const principal = req.principal;
    if (!principal || principal.kind !== 'agent') throw new DomainError('FORBIDDEN', 'agent credential required');
    const p = await platform.practices.load(principal.practiceId);
    authorize(principal, 'telemetry:ingest', scopeOf(p));
    if (p.status !== 'IN_PROGRESS') throw new DomainError('CONFLICT', 'practice is not in progress');
    const body = req.body as { files?: unknown; reason?: string };
    const allowed = new Set(['interval', 'significant_save', 'pre_submit', 'git_commit', 'manual']);
    const reason = allowed.has(body?.reason ?? '') ? (body!.reason as 'interval' | 'significant_save' | 'pre_submit' | 'git_commit' | 'manual') : 'manual';
    const res = await platform.snapshots.createFromUpload(p.id, body?.files as any, reason, buildSnapshotPolicy(p.snapshot_policy as any));
    return reply.status(201).send({
      snapshotId: res.snapshot.id,
      manifestHash: res.snapshot.manifest_hash,
      reused: res.reused,
      kind: res.snapshot.kind,
      baseSnapshotId: res.snapshot.base_snapshot_id,
      reason: res.snapshot.reason,
    });
  });
  app.post('/v1/agent/login', async (req) => {
    platform.limits.redeem.consume(`extension:${req.ip}`);
    const body = parse(extensionLoginReq, req.body);
    const candidate = await platform.auth.candidateForExtension(body.username, body.password);
    const practice = await ctx.db.one<{ id: string }>(
      `SELECT id FROM practices WHERE candidate_id = $1 AND status = 'IN_PROGRESS' ORDER BY updated_at DESC LIMIT 1`,
      [candidate.id],
    );
    if (!practice) throw new DomainError('CONFLICT', 'сначала начните практику на странице кандидата');
    return platform.workspaces.issueVscodeLink({ kind: 'candidate', id: candidate.id }, practice.id);
  });
  app.post('/v1/agent/heartbeat', async (req) => platform.workspaces.touchAgent(req.principal));
  app.post('/v1/agent/submit', async () => {
    throw new DomainError('FORBIDDEN', 'закрыть задачу можно только кнопкой на странице кандидата');
  });

  // ---------- Timeline, snapshots, git ----------
  app.get('/v1/practices/:id/timeline', async (req) => {
    const p = await platform.practices.authorized(req.principal, 'practice:timeline', (req.params as any).id);
    if (p.purged_at) throw new DomainError('GONE', 'timeline purged by retention policy');
    const q = parse(paginationQuery, req.query);
    const page = await platform.timeline.list(p.id, q.cursor, q.limit);
    return { ...page, interruptions: q.cursor ? undefined : await platform.timeline.interruptions(p.id) };
  });
  app.get('/v1/practices/:id/timeline/integrity', async (req) => {
    const p = await platform.practices.authorized(req.principal, 'practice:report', (req.params as any).id);
    return platform.timeline.verifyIntegrity(p.id);
  });
  app.get('/v1/practices/:id/snapshots', async (req) => {
    const p = await platform.practices.authorized(req.principal, 'practice:timeline', (req.params as any).id);
    return { items: (await platform.snapshots.list(p.id)).map(presentSnapshot) };
  });
  const snapshotFor = async (req: FastifyRequest) => {
    const snap = await platform.snapshots.get((req.params as any).id);
    const p = await platform.practices.load(snap.practice_id);
    authorize(req.principal, 'practice:timeline', scopeOf(p));
    return snap;
  };
  app.get('/v1/snapshots/:id', async (req) => presentSnapshot(await snapshotFor(req)));
  app.get('/v1/snapshots/:id/tree', async (req) => {
    const snap = await snapshotFor(req);
    return { snapshotId: snap.id, files: await platform.snapshots.manifest(snap.id) };
  });
  app.get('/v1/snapshots/:id/file', async (req) => {
    const snap = await snapshotFor(req);
    const q = parse(fileQuery, req.query);
    const data = await platform.snapshots.readFile(snap.id, q.path);
    return { snapshotId: snap.id, path: q.path, content: data.toString('utf8') };
  });
  app.get('/v1/practices/:id/commits', async (req) => {
    const p = await platform.practices.authorized(req.principal, 'practice:timeline', (req.params as any).id);
    const rows = await ctx.db.query<any>('SELECT * FROM git_commits WHERE practice_id = $1 ORDER BY committed_at', [p.id]);
    return { items: rows.map((c) => ({ sha: c.sha, message: c.message, author: c.author, changedFiles: c.changed_files, snapshotId: c.snapshot_id, committedAt: c.committed_at })), history: await platform.git.log(p.id).catch(() => []) };
  });

  // ---------- Sandbox results ----------
  app.get('/v1/practices/:id/test-runs', async (req) => {
    const p = await platform.practices.authorized(req.principal, 'practice:timeline', (req.params as any).id);
    return { items: (await platform.sandbox.listForPractice(p.id)).map(presentRun) };
  });
  app.get('/v1/test-runs/:id', async (req) => {
    const run = await platform.sandbox.get((req.params as any).id);
    authorize(req.principal, 'practice:timeline', scopeOf(await platform.practices.load(run.practice_id)));
    return presentRun(run);
  });
  app.post('/v1/test-runs/:id/log-link', async (req) => {
    const run = await platform.sandbox.get((req.params as any).id);
    const p = await platform.practices.load(run.practice_id);
    authorize(req.principal, 'artifact:read', scopeOf(p));
    if (!run.log_object_key) throw new DomainError('GONE', 'log not available');
    const grant = ctx.signer.sign({ key: run.log_object_key, principal: `${req.principal!.kind}:${req.principal!.id}` });
    return { url: `/v1/objects/${grant.token}`, expiresAt: grant.expiresAt };
  });
  app.get('/v1/objects/:token', async (req, reply) => {
    const grant = ctx.signer.verify((req.params as any).token);
    const data = await ctx.objects.get(grant.key);
    return reply.header('content-type', grant.contentType).header('content-disposition', 'attachment').send(data);
  });

  // ---------- Review ----------
  app.post('/v1/practices/:id/review', async (req) => presentPractice(await platform.review.startReview(req.principal, (req.params as any).id)));
  app.post('/v1/submissions/:id/comments', async (req, reply) => reply.status(201).send(await platform.review.addComment(req.principal, (req.params as any).id, parse(createCommentReq, req.body))));
  app.get('/v1/practices/:id/comments', async (req) => ({ items: await platform.review.listComments(req.principal, (req.params as any).id) }));
  app.post('/v1/comments/:id/resolve', async (req) => platform.review.resolve(req.principal, (req.params as any).id));
  app.post('/v1/practices/:id/request-changes', async (req) => presentPractice(await platform.review.requestChanges(req.principal, (req.params as any).id)));
  app.post('/v1/practices/:id/requirement-changes', async (req, reply) => reply.status(201).send(await platform.review.createRequirementChange(req.principal, (req.params as any).id, parse(requirementChangeReq, req.body))));
  app.get('/v1/practices/:id/requirement-changes', async (req) => ({ items: await platform.review.listRequirementChanges(req.principal, (req.params as any).id) }));
  app.post('/v1/practices/:id/complete', async (req) => presentPractice(await platform.review.complete(req.principal, (req.params as any).id)));

  // ---------- AI ----------
  app.post('/v1/submissions/:id/analysis', async (req, reply) => reply.status(202).send({ analysisId: await platform.ai.requestAnalysis(req.principal, (req.params as any).id) }));
  app.get('/v1/practices/:id/ai', async (req) => platform.ai.listForPractice(req.principal, (req.params as any).id));
  app.post('/v1/practices/:id/materials-review', async (req) => {
    await platform.practices.authorized(req.principal, 'practice:invite', (req.params as any).id);
    return { analysisId: await platform.ai.enqueueMaterialsReview((req.params as any).id) };
  });
  app.post('/v1/practices/:id/improvements', async (req) => {
    await platform.practices.authorized(req.principal, 'practice:invite', (req.params as any).id);
    return { analysisId: await platform.ai.enqueueImprovements((req.params as any).id) };
  });
  app.post('/v1/practices/:id/task-suggestions', async (req) => {
    await platform.practices.authorized(req.principal, 'practice:invite', (req.params as any).id);
    return { analysisId: await platform.ai.enqueueTaskSuggestion((req.params as any).id) };
  });
  app.post('/v1/practices/:id/process-review', async (req) => {
    await platform.practices.authorized(req.principal, 'practice:review', (req.params as any).id);
    return { analysisId: await platform.ai.enqueueProcessReview((req.params as any).id) };
  });
  app.post('/v1/interview/questions/:id/answers', async (req, reply) => reply.status(202).send(await platform.ai.answer(req.principal, (req.params as any).id, parse(interviewAnswerReq, req.body).text)));

  // ---------- Assessment & report ----------
  app.post('/v1/practices/:id/assessments', async (req, reply) => reply.status(201).send(await platform.assessment.generateDraft(req.principal, (req.params as any).id)));
  app.post('/v1/assessments/:id/approve', async (req) => platform.assessment.approve(req.principal, (req.params as any).id));
  app.get('/v1/practices/:id/report', async (req) => platform.assessment.report(req.principal, (req.params as any).id));

  // ---------- Audit ----------
  app.get('/v1/practices/:id/audit', async (req) => {
    const p = await platform.practices.authorized(req.principal, 'audit:read', (req.params as any).id);
    const rows = await ctx.db.query<any>('SELECT seq, at, actor_kind, actor_id, action, entity_type, entity_id, detail, hash FROM audit_log WHERE practice_id = $1 ORDER BY seq', [p.id]);
    return { items: rows, chain: await ctx.audit.verifyChain(ctx.db) };
  });

  app.setNotFoundHandler((_req: FastifyRequest, reply: FastifyReply) => reply.status(404).send({ error: { code: 'NOT_FOUND', message: 'route not found' } }));
  void notFound;
  return app;
}

const presentSubmission = (s: any) => ({
  id: s.id,
  practiceId: s.practice_id,
  version: s.version,
  snapshotId: s.snapshot_id,
  commitSha: s.commit_sha,
  baselineSubmissionId: s.baseline_submission_id,
  requirementChangeId: s.requirement_change_id,
  submittedAt: s.submitted_at,
});

const presentSnapshot = (s: any) => ({
  id: s.id,
  practiceId: s.practice_id,
  baseSnapshotId: s.base_snapshot_id,
  checkpointId: s.checkpoint_id,
  kind: s.kind,
  reason: s.reason,
  chainLength: s.chain_length,
  manifestHash: s.manifest_hash,
  fileCount: s.file_count,
  totalBytes: Number(s.total_bytes),
  skipped: s.skipped,
  createdAt: s.created_at,
  purged: !!s.purged_at,
});

const presentRun = (r: any) => ({
  id: r.id,
  practiceId: r.practice_id,
  snapshotId: r.snapshot_id,
  submissionId: r.submission_id,
  origin: r.origin,
  command: r.command,
  status: r.status,
  summary: r.summary,
  hasLog: !!r.log_object_key,
  createdAt: r.created_at,
  startedAt: r.started_at,
  finishedAt: r.finished_at,
});
