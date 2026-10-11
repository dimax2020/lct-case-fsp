import { constants as fsc } from 'node:fs';
import { lstat, mkdir, open, readdir, rm, unlink } from 'node:fs/promises';
import path from 'node:path';
import { authorize, type Principal } from '@epa/authz';
import {
  DomainError,
  buildSnapshotPolicy,
  normalizeWorkspacePath,
  notFound,
  resolveInsideRoot,
  type SnapshotPolicy,
  type WorkspacePolicy,
} from '@epa/domain';
import { newId, type Ctx, type JobRow } from '@epa/platform';
import { mapSandboxOutcome } from '@epa/domain';
import { parseNodeTestOutput, redactSecrets, safeLog } from '@epa/telemetry';
import { WorkspaceAgent, type TelemetryTransport } from '@epa/workspace-agent';
import type { GitService } from '@epa/git';
import type { SnapshotService, SnapshotReason } from '@epa/snapshots';
import { readWorkspaceTree } from '@epa/snapshots';
import type { TelemetryIngestion } from '@epa/timeline';
import type { AuthService, PracticeRow, PracticeService, TemplateCatalog } from '@epa/practice';
import { scopeOf } from '@epa/practice';
import type { RdeDriver } from './drivers.js';
import { parseWorkspaceCommand } from './command-policy.js';

export interface WorkspaceRow {
  id: string;
  practice_id: string;
  driver: string;
  runtime_ref: string | null;
  identity: string;
  lifecycle: 'PROVISIONING' | 'READY' | 'FAILED' | 'TEARING_DOWN' | 'DESTROYED';
  policy: WorkspacePolicy;
  expires_at: Date;
  failure_reason: string | null;
}

export interface WorkspaceLayout {
  root: string;
  repository: string;
  gitDir: string;
  outbox: string;
}

const MAX_OUTPUT_TO_CLIENT = 64 * 1024;
const READ_STATUSES = new Set(['IN_PROGRESS', 'SUBMITTED', 'REVIEW']);

/** In-process transport: the agent hands batches straight to ingestion with its own scoped principal. */
class DirectTransport implements TelemetryTransport {
  constructor(private readonly ingestion: TelemetryIngestion, private readonly principal: Principal) {}
  send(batch: Parameters<TelemetryTransport['send']>[0]) {
    return this.ingestion.ingest(this.principal, batch);
  }
}

interface SchedulerState {
  lastSnapshotAt: number;
  bytesSinceSnapshot: number;
  dirty: boolean;
}

/**
 * RDE control plane + gateway. The candidate never reaches the host: file operations are confined
 * to the workspace volume (no symlink following), and commands run inside the isolated runtime.
 */
export class WorkspaceService {
  private agents = new Map<string, WorkspaceAgent>();
  private scheduler = new Map<string, SchedulerState>();

  constructor(
    private readonly ctx: Ctx,
    private readonly driver: RdeDriver,
    private readonly git: GitService,
    private readonly snapshots: SnapshotService,
    private readonly ingestion: TelemetryIngestion,
    private readonly auth: AuthService,
    private readonly practices: PracticeService,
    private readonly templates: TemplateCatalog,
  ) {}

  layout(workspaceId: string): WorkspaceLayout {
    if (!/^ws_[a-f0-9]{32}$/.test(workspaceId)) throw new DomainError('VALIDATION', 'invalid workspace id');
    const root = path.join(this.ctx.config.dataDir, 'workspaces', workspaceId);
    return { root, repository: path.join(root, 'repository'), gitDir: path.join(root, 'meta', 'git'), outbox: path.join(root, 'meta', 'outbox') };
  }

  async getRow(workspaceId: string): Promise<WorkspaceRow> {
    const ws = await this.ctx.db.one<WorkspaceRow>('SELECT * FROM workspaces WHERE id = $1', [workspaceId]);
    if (!ws) throw notFound('workspace');
    return ws;
  }

  // ---------- Provisioning / teardown ----------

  async provision(job: JobRow): Promise<void> {
    const { practiceId, workspaceId } = job.payload as { practiceId: string; workspaceId: string };
    const ws = await this.getRow(workspaceId);
    if (ws.lifecycle === 'READY' || ws.lifecycle === 'DESTROYED') return;
    const practice = await this.practices.load(practiceId);
    if (practice.status !== 'STARTED') return;
    const lay = this.layout(workspaceId);
    try {
      const template = await this.templates.get(practice.template);
      await this.git.initPracticeRepo(practiceId, template.repoDir);
      await rm(lay.root, { recursive: true, force: true });
      await mkdir(lay.outbox, { recursive: true });
      await this.git.checkoutWorkspace(practiceId, lay.repository, lay.gitDir);
      const { runtimeRef } = await this.driver.provision({ workspaceId, identity: ws.identity, repositoryDir: lay.repository, policy: ws.policy });
      const sessionId = newId('ses');
      await this.ctx.db.tx(async (tx) => {
        await tx.query(`UPDATE workspaces SET lifecycle = 'READY', runtime_ref = $2, ready_at = $3, failure_reason = NULL WHERE id = $1`, [workspaceId, runtimeRef, this.ctx.clock.now()]);
        await tx.query(`INSERT INTO dev_sessions (id, practice_id, workspace_id, kind, consent_id, started_at) VALUES ($1,$2,$3,'workspace',$4,$5)`, [
          sessionId,
          practiceId,
          workspaceId,
          practice.consent_id,
          this.ctx.clock.now(),
        ]);
        await this.practices.transition(tx, practiceId, 'IN_PROGRESS', { actorType: 'platform', actorId: 'platform' }, { workspaceId, driver: this.driver.name });
        await this.ctx.audit.append(tx, {
          actorKind: 'platform',
          actorId: 'platform',
          action: 'workspace.provisioned',
          entityType: 'workspace',
          entityId: workspaceId,
          organisationId: practice.organisation_id,
          practiceId,
          detail: { driver: this.driver.name, isolated: this.driver.isolated, policyVersion: ws.policy.version },
        });
      });
      const agent = await this.agentFor(workspaceId);
      await agent.sessionStarted('workspace-agent');
      await this.snapshot(practice, workspaceId, 'initial');
      await agent.flush();
    } catch (e) {
      const reason = (e instanceof Error ? e.message : String(e)).slice(0, 500);
      if (job.attempts >= job.max_attempts) {
        await this.ctx.db.query(`UPDATE workspaces SET lifecycle = 'FAILED', failure_reason = $2 WHERE id = $1`, [workspaceId, reason]);
      }
      await this.driver.teardown(`epa-${workspaceId.replace('_', '-')}`).catch(() => undefined);
      throw e;
    }
  }

  /** Issues a session-scoped credential for an out-of-process agent (e.g. a sidecar in the RDE pod). */
  async issueAgentCredential(workspaceId: string): Promise<{ token: string; expiresAt: Date; sessionId: string }> {
    const ws = await this.getRow(workspaceId);
    if (ws.lifecycle !== 'READY') throw new DomainError('CONFLICT', 'workspace is not ready');
    const practice = await this.practices.load(ws.practice_id);
    const sessionId = newId('ses');
    return this.ctx.db.tx(async (tx) => {
      await tx.query(`INSERT INTO dev_sessions (id, practice_id, workspace_id, kind, client, consent_id, started_at) VALUES ($1,$2,$3,'workspace','sidecar',$4,$5)`, [
        sessionId,
        ws.practice_id,
        workspaceId,
        practice.consent_id,
        this.ctx.clock.now(),
      ]);
      const grant = await this.auth.issue(tx, {
        kind: 'agent',
        principalId: `agent:${sessionId}`,
        ttlMs: ws.policy.sessionTtlMinutes * 60_000,
        scope: { sessionId, practiceId: ws.practice_id, workspaceId },
      });
      return { ...grant, sessionId };
    });
  }

  /**
   * One-time credential for the candidate's VS Code extension. A new code revokes the previous
   * extension session. The plaintext token is returned only here and is not stored.
   */
  async issueVscodeLink(principal: Principal | null, practiceId: string): Promise<{ token: string; sessionId: string; expiresAt: Date; practiceId: string; workspaceId: string }> {
    const practice = await this.practices.authorized(principal, 'practice:work', practiceId);
    if (practice.status !== 'IN_PROGRESS' || !practice.workspace_id) throw new DomainError('CONFLICT', 'practice is not in progress');
    const ws = await this.getRow(practice.workspace_id);
    if (ws.lifecycle !== 'READY') throw new DomainError('CONFLICT', 'workspace is not ready');
    return this.ctx.db.tx(async (tx) => {
      const now = this.ctx.clock.now();
      const open = await tx.query<{ id: string }>(`SELECT id FROM dev_sessions WHERE practice_id = $1 AND client = 'vscode' AND ended_at IS NULL`, [practiceId]);
      for (const s of open) {
        await tx.query(`UPDATE dev_sessions SET ended_at = $2, end_reason = 'replaced' WHERE id = $1`, [s.id, now]);
        await tx.query(`UPDATE auth_tokens SET revoked_at = $2 WHERE principal_kind = 'agent' AND scope->>'sessionId' = $1 AND revoked_at IS NULL`, [s.id, now]);
      }
      const sessionId = newId('ses');
      await tx.query(
        `INSERT INTO dev_sessions (id, practice_id, workspace_id, kind, client, consent_id, started_at) VALUES ($1,$2,$3,'workspace','vscode',$4,$5)`,
        [sessionId, practiceId, ws.id, practice.consent_id, now],
      );
      const grant = await this.auth.issue(tx, {
        kind: 'agent',
        principalId: `agent:${sessionId}`,
        ttlMs: ws.policy.sessionTtlMinutes * 60_000,
        scope: { sessionId, practiceId, workspaceId: ws.id },
      });
      await this.ctx.audit.append(tx, {
        actorKind: principal!.kind,
        actorId: principal!.id,
        action: 'vscode.link_issued',
        entityType: 'dev_session',
        entityId: sessionId,
        organisationId: practice.organisation_id,
        practiceId,
        detail: { expiresAt: grant.expiresAt.toISOString() },
      });
      return { token: grant.token, sessionId, expiresAt: grant.expiresAt, practiceId, workspaceId: ws.id };
    });
  }

  /** Presence of the VS Code extension. Idle time without a signal is missing data, not a verdict. */
  async vscodeStatus(practiceId: string) {
    const session = await this.ctx.db.one<any>(
      `SELECT s.id, s.started_at, s.ended_at, s.end_reason, s.last_seen_at,
              (SELECT count(*)::int FROM telemetry_events e WHERE e.session_id = s.id) AS event_count,
              (SELECT type FROM telemetry_events e WHERE e.session_id = s.id ORDER BY sequence DESC LIMIT 1) AS last_type,
              (SELECT occurred_at FROM telemetry_events e WHERE e.session_id = s.id ORDER BY sequence DESC LIMIT 1) AS last_event_at
       FROM dev_sessions s
       WHERE s.practice_id = $1 AND s.client = 'vscode'
       ORDER BY s.started_at DESC LIMIT 1`,
      [practiceId],
    );
    if (!session) {
      return { linked: false, connected: false, sessionId: null, eventCount: 0, lastEventAt: null, lastEventType: null, lastSeenAt: null, startedAt: null, endedAt: null };
    }
    const seen = session.last_seen_at ? new Date(session.last_seen_at).getTime() : 0;
    const connected = !session.ended_at && seen > 0 && this.ctx.clock.now().getTime() - seen < 45_000;
    return {
      linked: true,
      connected,
      sessionId: session.id,
      eventCount: Number(session.event_count ?? 0),
      lastEventAt: session.last_event_at,
      lastEventType: session.last_type,
      lastSeenAt: session.last_seen_at,
      startedAt: session.started_at,
      endedAt: session.ended_at,
    };
  }

  async touchAgent(principal: Principal | null): Promise<{ ok: true; sessionId: string }> {
    if (!principal) throw new DomainError('UNAUTHENTICATED', 'authentication required');
    if (principal.kind !== 'agent') throw new DomainError('FORBIDDEN', 'agent credential required');
    const row = await this.ctx.db.one<{ id: string }>(
      `UPDATE dev_sessions SET last_seen_at = $2 WHERE id = $1 AND ended_at IS NULL RETURNING id`,
      [principal.sessionId, this.ctx.clock.now()],
    );
    if (!row) throw new DomainError('CONFLICT', 'session is not active');
    return { ok: true, sessionId: principal.sessionId };
  }

  private async activeSession(workspaceId: string) {
    const s = await this.ctx.db.one<{ id: string; practice_id: string }>(
      `SELECT id, practice_id FROM dev_sessions WHERE workspace_id = $1 AND kind = 'workspace' AND client = 'gateway' ORDER BY started_at DESC LIMIT 1`,
      [workspaceId],
    );
    if (!s) throw new DomainError('CONFLICT', 'workspace has no session');
    return s;
  }

  async agentFor(workspaceId: string): Promise<WorkspaceAgent> {
    const cached = this.agents.get(workspaceId);
    if (cached) return cached;
    const s = await this.activeSession(workspaceId);
    const principal: Principal = { kind: 'agent', id: `agent:${s.id}`, sessionId: s.id, practiceId: s.practice_id, workspaceId };
    const agent = await WorkspaceAgent.open({
      sessionId: s.id,
      outboxDir: this.layout(workspaceId).outbox,
      transport: new DirectTransport(this.ingestion, principal),
      now: () => this.ctx.clock.now(),
    });
    this.agents.set(workspaceId, agent);
    return agent;
  }

  async teardown(practiceId: string, reason: string): Promise<void> {
    const practice = await this.practices.load(practiceId);
    if (!practice.workspace_id) return;
    const ws = await this.getRow(practice.workspace_id);
    if (ws.lifecycle === 'DESTROYED') return;
    await this.ctx.db.query(`UPDATE workspaces SET lifecycle = 'TEARING_DOWN' WHERE id = $1`, [ws.id]);
    const agent = this.agents.get(ws.id) ?? (await this.agentFor(ws.id).catch(() => null));
    if (agent) {
      await agent.sessionEnded(reason === 'EXPIRED' ? 'expired' : 'teardown');
      await agent.flush();
      agent.close();
      this.agents.delete(ws.id);
    }
    if (ws.runtime_ref) await this.driver.teardown(ws.runtime_ref);
    await rm(this.layout(ws.id).root, { recursive: true, force: true });
    this.scheduler.delete(ws.id);
    await this.ctx.db.tx(async (tx) => {
      await tx.query(`UPDATE workspaces SET lifecycle = 'DESTROYED', destroyed_at = $2 WHERE id = $1`, [ws.id, this.ctx.clock.now()]);
      await tx.query(`UPDATE dev_sessions SET ended_at = COALESCE(ended_at, $2), end_reason = COALESCE(end_reason, 'teardown') WHERE workspace_id = $1`, [ws.id, this.ctx.clock.now()]);
      await this.auth.revokeWhere(tx, 'agent', 'workspaceId', ws.id);
      await this.ctx.audit.append(tx, {
        actorKind: 'platform',
        actorId: 'platform',
        action: 'workspace.destroyed',
        entityType: 'workspace',
        entityId: ws.id,
        organisationId: practice.organisation_id,
        practiceId,
        detail: { reason },
      });
    });
  }

  // ---------- Access ----------

  private async access(principal: Principal | null, workspaceId: string, mode: 'read' | 'write') {
    const ws = await this.getRow(workspaceId);
    const practice = await this.practices.load(ws.practice_id);
    authorize(principal, 'practice:work', scopeOf(practice));
    if (ws.lifecycle !== 'READY') throw new DomainError(ws.lifecycle === 'DESTROYED' ? 'GONE' : 'CONFLICT', `workspace is ${ws.lifecycle}`);
    if (new Date(ws.expires_at).getTime() <= this.ctx.clock.now().getTime() || practice.status === 'EXPIRED') {
      await this.practices.expireOverdue();
      throw new DomainError('EXPIRED', 'workspace access has expired');
    }
    if (mode === 'write') await this.practices.assertWorkable(practice.id);
    else if (!READ_STATUSES.has(practice.status)) throw new DomainError('CONFLICT', `practice is ${practice.status}`);
    return { ws, practice, lay: this.layout(workspaceId) };
  }

  /** Rejects any path whose components (or target) are symlinks, so writes cannot escape the volume. */
  private async safePath(lay: WorkspaceLayout, rel: string): Promise<{ rel: string; abs: string; exists: boolean }> {
    const norm = normalizeWorkspacePath(rel);
    const abs = resolveInsideRoot(lay.repository, norm);
    let cur = lay.repository;
    const parts = norm.split('/');
    for (let i = 0; i < parts.length; i++) {
      cur = path.join(cur, parts[i]);
      try {
        const st = await lstat(cur);
        if (st.isSymbolicLink()) throw new DomainError('VALIDATION', 'symlinks are not allowed in workspace paths');
        if (i < parts.length - 1 && !st.isDirectory()) throw new DomainError('VALIDATION', 'path component is not a directory');
      } catch (e: any) {
        if (e instanceof DomainError) throw e;
        if (e?.code === 'ENOENT') return { rel: norm, abs, exists: false };
        throw e;
      }
    }
    return { rel: norm, abs, exists: true };
  }

  private async readNoFollow(abs: string, maxBytes: number): Promise<Buffer> {
    const fh = await open(abs, fsc.O_RDONLY | fsc.O_NOFOLLOW);
    try {
      const st = await fh.stat();
      if (!st.isFile()) throw new DomainError('VALIDATION', 'not a regular file');
      if (st.size > maxBytes) throw new DomainError('PAYLOAD_TOO_LARGE', 'file too large');
      return await fh.readFile();
    } finally {
      await fh.close();
    }
  }

  async listFiles(principal: Principal | null, workspaceId: string) {
    const { lay } = await this.access(principal, workspaceId, 'read');
    const out: { path: string; size: number; type: 'file' | 'symlink' }[] = [];
    const walk = async (rel: string) => {
      const entries = (await readdir(path.join(lay.repository, rel), { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name));
      for (const e of entries) {
        if (e.name === 'node_modules' || e.name === '.git') continue;
        const r = rel ? `${rel}/${e.name}` : e.name;
        if (e.isSymbolicLink()) out.push({ path: r, size: 0, type: 'symlink' });
        else if (e.isDirectory()) await walk(r);
        else if (e.isFile()) out.push({ path: r, size: (await lstat(path.join(lay.repository, r))).size, type: 'file' });
        if (out.length > 5000) return;
      }
    };
    await walk('');
    return out;
  }

  async readFile(principal: Principal | null, workspaceId: string, rel: string): Promise<string> {
    const { lay, ws } = await this.access(principal, workspaceId, 'read');
    const p = await this.safePath(lay, rel);
    if (!p.exists) throw notFound('file');
    return (await this.readNoFollow(p.abs, ws.policy.maxFileBytes)).toString('utf8');
  }

  async writeFile(principal: Principal | null, workspaceId: string, input: { path: string; content: string; editorStats?: { pastedChars: number } }) {
    const { lay, ws, practice } = await this.access(principal, workspaceId, 'write');
    const bytes = Buffer.byteLength(input.content);
    if (bytes > ws.policy.maxFileBytes) throw new DomainError('PAYLOAD_TOO_LARGE', 'file exceeds workspace limit');
    const p = await this.safePath(lay, input.path);
    const before = p.exists ? (await this.readNoFollow(p.abs, ws.policy.maxFileBytes)).toString('utf8') : null;
    await mkdir(path.dirname(p.abs), { recursive: true });
    await this.safePath(lay, input.path);
    const fh = await open(p.abs, fsc.O_WRONLY | fsc.O_CREAT | fsc.O_TRUNC | fsc.O_NOFOLLOW, 0o644);
    try {
      await fh.writeFile(input.content, 'utf8');
    } finally {
      await fh.close();
    }
    const agent = await this.agentFor(workspaceId);
    const { stats, signal } = await agent.fileWritten({ path: p.rel, before, after: input.content, pastedChars: input.editorStats?.pastedChars });
    await this.afterChange(practice, workspaceId, stats.insertedChars + stats.deletedChars);
    return { path: p.rel, bytes, stats, largeInsertionSignal: signal };
  }

  async deleteFile(principal: Principal | null, workspaceId: string, rel: string) {
    const { lay, practice } = await this.access(principal, workspaceId, 'write');
    const p = await this.safePath(lay, rel);
    if (!p.exists) throw notFound('file');
    await unlink(p.abs);
    await (await this.agentFor(workspaceId)).fileDeleted(p.rel);
    await this.afterChange(practice, workspaceId, 1);
    return { path: p.rel, deleted: true };
  }

  // ---------- Snapshot scheduling ----------

  private policyOf(practice: PracticeRow): SnapshotPolicy {
    return buildSnapshotPolicy(practice.snapshot_policy as Partial<SnapshotPolicy>);
  }

  private state(workspaceId: string): SchedulerState {
    let s = this.scheduler.get(workspaceId);
    if (!s) {
      s = { lastSnapshotAt: this.ctx.clock.now().getTime(), bytesSinceSnapshot: 0, dirty: false };
      this.scheduler.set(workspaceId, s);
    }
    return s;
  }

  /** Snapshot on significant saves or after the configured interval — never on every edit. */
  private async afterChange(practice: PracticeRow, workspaceId: string, bytesChanged: number) {
    const policy = this.policyOf(practice);
    const s = this.state(workspaceId);
    s.dirty = true;
    s.bytesSinceSnapshot += bytesChanged;
    const now = this.ctx.clock.now().getTime();
    if (s.bytesSinceSnapshot >= policy.significantSaveBytes) await this.snapshot(practice, workspaceId, 'significant_save');
    else if (now - s.lastSnapshotAt >= policy.intervalSec * 1000) await this.snapshot(practice, workspaceId, 'interval');
  }

  /** Called by the interval sweep job for workspaces with unsnapshotted changes. */
  async intervalSweep(): Promise<number> {
    let n = 0;
    for (const [workspaceId, s] of this.scheduler) {
      if (!s.dirty) continue;
      const ws = await this.getRow(workspaceId).catch(() => null);
      if (!ws || ws.lifecycle !== 'READY') continue;
      const practice = await this.practices.load(ws.practice_id);
      if (practice.status !== 'IN_PROGRESS') continue;
      if (this.ctx.clock.now().getTime() - s.lastSnapshotAt >= this.policyOf(practice).intervalSec * 1000) {
        await this.snapshot(practice, workspaceId, 'interval');
        n++;
      }
    }
    return n;
  }

  async snapshot(practice: PracticeRow, workspaceId: string, reason: SnapshotReason) {
    const res = await this.snapshots.captureWorkspace(practice.id, this.layout(workspaceId).repository, reason, this.policyOf(practice));
    const s = this.state(workspaceId);
    s.lastSnapshotAt = this.ctx.clock.now().getTime();
    s.bytesSinceSnapshot = 0;
    s.dirty = false;
    if (!res.reused) {
      await (await this.agentFor(workspaceId)).snapshotCreated({
        snapshotId: res.snapshot.id,
        baseSnapshotId: res.snapshot.base_snapshot_id,
        manifestHash: res.snapshot.manifest_hash,
        kind: res.snapshot.kind,
        reason,
      });
    }
    return res.snapshot;
  }

  // ---------- Commands, tests, git ----------

  async runCommand(principal: Principal | null, workspaceId: string, command: string) {
    const { lay, ws, practice } = await this.access(principal, workspaceId, 'write');
    const parsed = parseWorkspaceCommand(command);
    const agent = await this.agentFor(workspaceId);
    const started = Date.now();
    let result: { exitCode: number | null; output: string; timedOut: boolean };
    if (parsed.kind === 'git') {
      const out =
        parsed.sub === 'status' ? await this.git.status(lay.gitDir, lay.repository)
        : parsed.sub === 'diff' ? await this.git.diffStat(lay.gitDir, lay.repository)
        : (await this.git.log(practice.id, 30)).map((c) => `${c.sha.slice(0, 8)} ${c.author} ${c.message}`).join('\n');
      result = { exitCode: 0, output: out, timedOut: false };
    } else {
      const before = await readWorkspaceTree(lay.repository, this.policyOf(practice));
      const r = await this.driver.exec(ws.runtime_ref!, parsed.argv, { timeoutSec: ws.policy.commandTimeoutSec, repositoryDir: lay.repository });
      result = { exitCode: r.exitCode, output: `${r.stdout}${r.stderr}`, timedOut: r.timedOut };
      await this.recordCommandFileChanges(practice, workspaceId, before.tree);
    }
    const durationMs = Date.now() - started;
    await agent.terminalCommand({ command, exitCode: result.exitCode, durationMs, timedOut: result.timedOut });
    return { exitCode: result.exitCode, timedOut: result.timedOut, durationMs, output: safeLog(result.output, MAX_OUTPUT_TO_CLIENT).text };
  }

  /** Files changed by a command are reported like saves (without editor paste information). */
  private async recordCommandFileChanges(practice: PracticeRow, workspaceId: string, before: Map<string, Buffer>) {
    const after = (await readWorkspaceTree(this.layout(workspaceId).repository, this.policyOf(practice))).tree;
    const agent = await this.agentFor(workspaceId);
    let changed = 0;
    for (const [p, data] of after) {
      const prev = before.get(p);
      if (prev && prev.equals(data)) continue;
      const r = await agent.fileWritten({ path: p, before: prev ? prev.toString('utf8') : null, after: data.toString('utf8') });
      changed += r.stats.insertedChars + r.stats.deletedChars;
    }
    for (const p of before.keys()) {
      if (!after.has(p)) {
        await agent.fileDeleted(p);
        changed++;
      }
    }
    if (changed > 0) await this.afterChange(practice, workspaceId, changed);
  }

  async runTests(principal: Principal | null, workspaceId: string) {
    const { lay, ws, practice } = await this.access(principal, workspaceId, 'write');
    const agent = await this.agentFor(workspaceId);
    const runId = newId('tr');
    const command = practice.test_command.join(' ');
    await this.ctx.db.query(`INSERT INTO test_runs (id, practice_id, origin, command, status, created_at, started_at) VALUES ($1,$2,'workspace',$3,'RUNNING',$4,$4)`, [
      runId,
      practice.id,
      JSON.stringify(practice.test_command),
      this.ctx.clock.now(),
    ]);
    await agent.testStarted(runId, command);
    const r = await this.driver.exec(ws.runtime_ref!, practice.test_command, { timeoutSec: ws.policy.commandTimeoutSec, repositoryDir: lay.repository });
    const output = `${r.stdout}\n${r.stderr}`;
    const parsed = parseNodeTestOutput(output, { coverageEnabled: practice.coverage });
    const status = mapSandboxOutcome({ timedOut: r.timedOut, infraError: false, exitCode: r.exitCode, parsed });
    const summary = {
      status,
      exitCode: r.exitCode,
      durationMs: parsed?.durationMs ?? r.durationMs,
      tests: parsed?.tests ?? 0,
      passed: parsed?.passed ?? 0,
      failed: parsed?.failed ?? 0,
      skipped: parsed?.skipped ?? 0,
      failedTests: parsed?.failedTests ?? [],
      coverage: parsed?.coverage ?? null,
    };
    await this.ctx.db.query('UPDATE test_runs SET status = $2, summary = $3, finished_at = $4 WHERE id = $1', [runId, status, JSON.stringify(summary), this.ctx.clock.now()]);
    await agent.testFinished({ runId, command, status: status as any, exitCode: r.exitCode, passed: summary.passed, failed: summary.failed, durationMs: summary.durationMs, log: output });
    return { runId, ...summary, log: safeLog(output, MAX_OUTPUT_TO_CLIENT).text };
  }

  async commit(principal: Principal | null, workspaceId: string, message: string) {
    const { lay, practice } = await this.access(principal, workspaceId, 'write');
    const session = await this.activeSession(workspaceId);
    const author = `candidate:${practice.candidate_id}`;
    const { sha, changedFiles } = await this.git.commit({
      practiceId: practice.id,
      gitDir: lay.gitDir,
      workTree: lay.repository,
      message: redactSecrets(message),
      authorName: author,
      authorEmail: `${session.id}@sessions.epa.local`,
    });
    const snap = await this.snapshot(practice, workspaceId, 'git_commit');
    await this.ctx.db.query(
      `INSERT INTO git_commits (sha, practice_id, message, author, changed_files, snapshot_id, committed_at) VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT DO NOTHING`,
      [sha, practice.id, redactSecrets(message), author, JSON.stringify(changedFiles), snap.id, this.ctx.clock.now()],
    );
    await (await this.agentFor(workspaceId)).gitCommit({ sha, message, author, changedFiles, snapshotId: snap.id });
    return { sha, changedFiles, snapshotId: snap.id };
  }

  async headSha(workspaceId: string): Promise<string | null> {
    return this.git.headSha(this.layout(workspaceId).gitDir);
  }

  async flushAll(): Promise<void> {
    await Promise.all([...this.agents.values()].map((a) => a.flush()));
  }

  async shutdown(): Promise<void> {
    for (const a of this.agents.values()) a.close();
    this.agents.clear();
  }
}
