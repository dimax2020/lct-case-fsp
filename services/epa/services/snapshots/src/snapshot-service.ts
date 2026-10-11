import { lstat, mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { DEFAULT_SNAPSHOT_POLICY, DomainError, normalizeWorkspacePath, notFound, type SnapshotPolicy } from '@epa/domain';
import { newId, type Ctx, type Queryable } from '@epa/platform';
import {
  applyPatch,
  buildCheckpoint,
  decodeObject,
  diffTrees,
  encodeObject,
  manifestHash,
  manifestOf,
  readCheckpoint,
  type Checkpoint,
  type Patch,
  type Tree,
} from './format.js';

export type SnapshotReason = 'interval' | 'significant_save' | 'pre_submit' | 'git_commit' | 'pre_sandbox' | 'post_sandbox' | 'manual' | 'initial';

export interface SnapshotRow {
  id: string;
  practice_id: string;
  ordinal: number;
  base_snapshot_id: string | null;
  checkpoint_id: string | null;
  kind: 'checkpoint' | 'patch';
  reason: SnapshotReason;
  chain_length: number;
  object_key: string;
  object_hash: string;
  manifest_hash: string;
  file_count: number;
  total_bytes: number;
  skipped: { path: string; reason: string }[];
  created_at: Date;
  purged_at: Date | null;
}

const IGNORED_DIRS = new Set(['.git', 'node_modules', '.epa']);
const MAX_CHAIN = 100;

/** Reads a workspace directory without following symlinks and within policy limits. */
export async function readWorkspaceTree(root: string, policy: SnapshotPolicy = DEFAULT_SNAPSHOT_POLICY): Promise<{ tree: Tree; skipped: { path: string; reason: string }[] }> {
  const tree: Tree = new Map();
  const skipped: { path: string; reason: string }[] = [];
  let total = 0;
  const walk = async (rel: string) => {
    const entries = (await readdir(path.join(root, rel), { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name));
    for (const e of entries) {
      const r = rel ? `${rel}/${e.name}` : e.name;
      let safe: string;
      try {
        safe = normalizeWorkspacePath(r, { allowInternal: true });
      } catch {
        skipped.push({ path: r.slice(0, 200), reason: 'unsafe_name' });
        continue;
      }
      const st = await lstat(path.join(root, safe));
      if (st.isSymbolicLink()) {
        skipped.push({ path: safe, reason: 'symlink' });
        continue;
      }
      if (st.isDirectory()) {
        if (IGNORED_DIRS.has(e.name)) continue;
        await walk(safe);
        continue;
      }
      if (!st.isFile()) {
        skipped.push({ path: safe, reason: 'special_file' });
        continue;
      }
      if (st.size > policy.maxFileBytes) {
        skipped.push({ path: safe, reason: 'file_too_large' });
        continue;
      }
      if (tree.size >= policy.maxFiles || total + st.size > policy.maxTotalBytes) {
        skipped.push({ path: safe, reason: 'workspace_limit' });
        continue;
      }
      tree.set(safe, await readFile(path.join(root, safe)));
      total += st.size;
    }
  };
  await walk('');
  return { tree, skipped };
}

export class SnapshotService {
  private cache = new Map<string, Tree>();

  constructor(private readonly ctx: Ctx) {}

  private remember(id: string, tree: Tree) {
    this.cache.set(id, tree);
    if (this.cache.size > 32) this.cache.delete(this.cache.keys().next().value!);
  }

  async get(id: string, q: Queryable = this.ctx.db): Promise<SnapshotRow> {
    if (typeof id !== 'string' || id.length > 100) throw notFound('snapshot');
    const row = await q.one<SnapshotRow>('SELECT * FROM snapshots WHERE id = $1', [id]);
    if (!row) throw notFound('snapshot');
    return row;
  }

  async latest(practiceId: string): Promise<SnapshotRow | null> {
    return this.ctx.db.one<SnapshotRow>('SELECT * FROM snapshots WHERE practice_id = $1 AND purged_at IS NULL ORDER BY ordinal DESC LIMIT 1', [practiceId]);
  }

  async captureWorkspace(practiceId: string, repositoryDir: string, reason: SnapshotReason, policy: SnapshotPolicy) {
    const { tree, skipped } = await readWorkspaceTree(repositoryDir, policy);
    return this.create(practiceId, tree, reason, policy, skipped);
  }

  /** Validates an agent-uploaded file set (paths, sizes, counts) before snapshotting it. */
  async createFromUpload(practiceId: string, files: { path: string; contentBase64: string }[], reason: SnapshotReason, policy: SnapshotPolicy) {
    if (!Array.isArray(files) || files.length > policy.maxFiles) throw new DomainError('PAYLOAD_TOO_LARGE', 'too many files');
    const tree: Tree = new Map();
    let total = 0;
    for (const f of files) {
      const p = normalizeWorkspacePath(f.path);
      if (tree.has(p)) throw new DomainError('VALIDATION', `duplicate path ${p}`);
      if (typeof f.contentBase64 !== 'string' || f.contentBase64.length > Math.ceil((policy.maxFileBytes * 4) / 3) + 4) {
        throw new DomainError('PAYLOAD_TOO_LARGE', `file too large: ${p}`);
      }
      const data = Buffer.from(f.contentBase64, 'base64');
      total += data.length;
      if (data.length > policy.maxFileBytes || total > policy.maxTotalBytes) throw new DomainError('PAYLOAD_TOO_LARGE', 'snapshot exceeds size limits');
      tree.set(p, data);
    }
    return this.create(practiceId, tree, reason, policy, []);
  }

  /**
   * Creates an immutable snapshot. Unchanged trees reuse the latest snapshot (no snapshot per
   * keystroke). After `checkpointEvery` patches a new full checkpoint starts a fresh chain.
   */
  async create(practiceId: string, tree: Tree, reason: SnapshotReason, policy: SnapshotPolicy, skipped: { path: string; reason: string }[] = []): Promise<{ snapshot: SnapshotRow; reused: boolean }> {
    const mHash = manifestHash(tree);
    const last = await this.latest(practiceId);
    const lastSkipped = Array.isArray(last?.skipped) ? last.skipped : [];
    const sameSkipped =
      lastSkipped.length === skipped.length &&
      [...lastSkipped].map((x) => `${x.path}\0${x.reason}`).sort().join('|') ===
        [...skipped].map((x) => `${x.path}\0${x.reason}`).sort().join('|');
    if (last && last.manifest_hash === mHash && sameSkipped) return { snapshot: last, reused: true };

    const id = newId('snap');
    let kind: 'checkpoint' | 'patch' = 'checkpoint';
    let body: Checkpoint | Patch;
    let chainLength = 0;
    let checkpointId: string | null = null;
    let baseId: string | null = null;
    if (last && last.chain_length + 1 <= policy.checkpointEvery) {
      try {
        const base = await this.reconstruct(last.id);
        body = diffTrees(base, tree);
        kind = 'patch';
        chainLength = last.chain_length + 1;
        checkpointId = last.kind === 'checkpoint' ? last.id : last.checkpoint_id;
        baseId = last.id;
      } catch (e) {
        // A broken previous chain must not block new work: start a fresh checkpoint instead.
        this.ctx.log.warn('snapshot base unavailable, writing checkpoint', { practiceId, base: last.id, error: String(e) });
        body = buildCheckpoint(tree);
      }
    } else {
      body = buildCheckpoint(tree);
      if (last) baseId = last.id;
    }
    const key = `snapshots/${practiceId}/${id}.json.gz`;
    const stored = await this.ctx.objects.put(key, encodeObject(body));
    const total = [...tree.values()].reduce((n, b) => n + b.length, 0);
    const row = await this.ctx.db.tx(async (tx) => {
      await tx.query('SELECT pg_advisory_xact_lock(hashtext($1))', [`snapshots:${practiceId}`]);
      return tx.one<SnapshotRow>(
        `INSERT INTO snapshots (id, practice_id, ordinal, base_snapshot_id, checkpoint_id, kind, reason, chain_length, object_key, object_hash, manifest_hash, file_count, total_bytes, skipped, created_at)
         VALUES ($1,$2,(SELECT COALESCE(MAX(ordinal), 0) + 1 FROM snapshots WHERE practice_id = $2),$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) RETURNING *`,
        [id, practiceId, baseId, checkpointId, kind, reason, chainLength, key, stored.sha256, mHash, tree.size, total, JSON.stringify(skipped.slice(0, 200)), this.ctx.clock.now()],
      );
    });
    this.remember(id, tree);
    this.ctx.metrics.inc('snapshots_created_total', { kind, reason });
    return { snapshot: row!, reused: false };
  }

  private async loadObject<T>(row: SnapshotRow): Promise<T> {
    if (row.purged_at) throw new DomainError('GONE', 'snapshot purged by retention policy');
    const data = await this.ctx.objects.get(row.object_key, row.object_hash).catch((e) => {
      if (e instanceof DomainError && e.code === 'GONE') {
        throw new DomainError('INTEGRITY', 'snapshot chain corrupted: object missing', { snapshotId: row.id });
      }
      throw e;
    });
    return decodeObject<T>(data, Math.ceil(DEFAULT_SNAPSHOT_POLICY.maxTotalBytes * 3) + 1024 * 1024);
  }

  /**
   * Restores the exact state of a snapshot: load the checkpoint, then apply each verified patch.
   * Any broken link raises INTEGRITY; a later state is never substituted.
   */
  async reconstruct(snapshotId: string): Promise<Tree> {
    const head = await this.get(snapshotId);
    if (head.purged_at) {
      this.cache.delete(snapshotId);
      throw new DomainError('GONE', 'snapshot purged by retention policy');
    }
    const cached = this.cache.get(snapshotId);
    if (cached) return new Map(cached);
    const chain: SnapshotRow[] = [];
    let cur: SnapshotRow | null = head;
    while (cur) {
      chain.unshift(cur);
      if (cur.kind === 'checkpoint') break;
      if (chain.length > MAX_CHAIN || !cur.base_snapshot_id) throw new DomainError('INTEGRITY', 'snapshot chain corrupted: missing base', { snapshotId: cur.id });
      cur = await this.ctx.db.one<SnapshotRow>('SELECT * FROM snapshots WHERE id = $1', [cur.base_snapshot_id]);
      if (!cur) throw new DomainError('INTEGRITY', 'snapshot chain corrupted: base row missing', { snapshotId });
    }
    let tree: Tree | null = null;
    for (const row of chain) {
      try {
        if (row.kind === 'checkpoint') tree = readCheckpoint(await this.loadObject<Checkpoint>(row));
        else tree = applyPatch(tree!, await this.loadObject<Patch>(row));
      } catch (e) {
        if (e instanceof DomainError && (e.code === 'INTEGRITY' || e.code === 'PAYLOAD_TOO_LARGE')) {
          throw new DomainError('INTEGRITY', e.message, { ...e.details, snapshotId: row.id, requested: snapshotId });
        }
        throw e;
      }
      if (manifestHash(tree!) !== row.manifest_hash) {
        throw new DomainError('INTEGRITY', 'snapshot chain corrupted: manifest mismatch', { snapshotId: row.id });
      }
    }
    this.remember(snapshotId, tree!);
    return new Map(tree!);
  }

  async manifest(snapshotId: string) {
    return manifestOf(await this.reconstruct(snapshotId));
  }

  async readFile(snapshotId: string, relPath: string): Promise<Buffer> {
    const p = normalizeWorkspacePath(relPath);
    const tree = await this.reconstruct(snapshotId);
    const data = tree.get(p);
    if (!data) throw notFound('file in snapshot');
    return data;
  }

  /** Writes a verified snapshot into a fresh directory (used to feed the sandbox a read-only copy). */
  async materialize(snapshotId: string, destDir: string): Promise<number> {
    const tree = await this.reconstruct(snapshotId);
    await mkdir(destDir, { recursive: true });
    for (const [rel, data] of tree) {
      const abs = path.join(destDir, normalizeWorkspacePath(rel, { allowInternal: true }));
      if (!abs.startsWith(path.resolve(destDir) + path.sep)) throw new DomainError('VALIDATION', 'path escapes destination');
      await mkdir(path.dirname(abs), { recursive: true, mode: 0o755 });
      await writeFile(abs, data, { flag: 'wx', mode: 0o644 });
    }
    return tree.size;
  }

  async list(practiceId: string): Promise<SnapshotRow[]> {
    return this.ctx.db.query<SnapshotRow>('SELECT * FROM snapshots WHERE practice_id = $1 ORDER BY ordinal', [practiceId]);
  }
}
