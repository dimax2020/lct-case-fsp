import { gzipSync, gunzipSync } from 'node:zlib';
import { DomainError, normalizeWorkspacePath } from '@epa/domain';
import { canonicalJson, sha256Hex } from '@epa/telemetry';

export type Tree = Map<string, Buffer>;

export interface ManifestEntry {
  path: string;
  sha256: string;
  size: number;
}

export function manifestOf(tree: Tree): ManifestEntry[] {
  return [...tree.entries()]
    .map(([path, data]) => ({ path, sha256: sha256Hex(data), size: data.length }))
    .sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
}

export function manifestHash(tree: Tree): string {
  return sha256Hex(canonicalJson(manifestOf(tree)));
}

// ---------- Patch format ----------

export type PatchOp =
  | { op: 'add'; path: string; sha256: string; content: string }
  | { op: 'delete'; path: string; baseSha256: string; content: string }
  | { op: 'modify'; path: string; encoding: 'lines'; baseSha256: string; resultSha256: string; start: number; deleted: string[]; inserted: string[] }
  | { op: 'modify'; path: string; encoding: 'binary'; baseSha256: string; resultSha256: string; previous: string; content: string };

export interface Patch {
  format: 'epa-patch-v1';
  baseManifestHash: string;
  resultManifestHash: string;
  ops: PatchOp[];
}

export interface Checkpoint {
  format: 'epa-checkpoint-v1';
  manifestHash: string;
  files: { path: string; sha256: string; content: string }[];
}

const isText = (b: Buffer) => !b.includes(0) && Buffer.from(b.toString('utf8'), 'utf8').equals(b);

/** Single-hunk line diff (common prefix/suffix trimmed). Stores removed lines so it is reversible. */
function lineHunk(before: string, after: string) {
  const a = before.split('\n');
  const b = after.split('\n');
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let ea = a.length;
  let eb = b.length;
  while (ea > start && eb > start && a[ea - 1] === b[eb - 1]) {
    ea--;
    eb--;
  }
  return { start, deleted: a.slice(start, ea), inserted: b.slice(start, eb) };
}

export function diffTrees(base: Tree, next: Tree): Patch {
  const ops: PatchOp[] = [];
  const paths = [...new Set([...base.keys(), ...next.keys()])].sort();
  for (const p of paths) {
    const a = base.get(p);
    const b = next.get(p);
    if (a && !b) ops.push({ op: 'delete', path: p, baseSha256: sha256Hex(a), content: a.toString('base64') });
    else if (!a && b) ops.push({ op: 'add', path: p, sha256: sha256Hex(b), content: b.toString('base64') });
    else if (a && b && !a.equals(b)) {
      if (isText(a) && isText(b)) {
        ops.push({ op: 'modify', path: p, encoding: 'lines', baseSha256: sha256Hex(a), resultSha256: sha256Hex(b), ...lineHunk(a.toString('utf8'), b.toString('utf8')) });
      } else {
        ops.push({ op: 'modify', path: p, encoding: 'binary', baseSha256: sha256Hex(a), resultSha256: sha256Hex(b), previous: a.toString('base64'), content: b.toString('base64') });
      }
    }
  }
  return { format: 'epa-patch-v1', baseManifestHash: manifestHash(base), resultManifestHash: manifestHash(next), ops };
}

const corrupt = (msg: string, details?: Record<string, unknown>) => new DomainError('INTEGRITY', `snapshot chain corrupted: ${msg}`, details);

function applyOps(tree: Tree, patch: Patch, direction: 'forward' | 'reverse'): Tree {
  const out = new Map(tree);
  const ops = direction === 'forward' ? patch.ops : [...patch.ops].reverse();
  for (const raw of ops) {
    const p = normalizeWorkspacePath(raw.path);
    const cur = out.get(p);
    const check = (buf: Buffer | undefined, expected: string) => {
      if (!buf || sha256Hex(buf) !== expected) throw corrupt(`content hash mismatch at ${p}`);
    };
    if (raw.op === 'add') {
      if (direction === 'forward') {
        if (cur) throw corrupt(`add over existing file ${p}`);
        const data = Buffer.from(raw.content, 'base64');
        check(data, raw.sha256);
        out.set(p, data);
      } else {
        check(cur, raw.sha256);
        out.delete(p);
      }
    } else if (raw.op === 'delete') {
      if (direction === 'forward') {
        check(cur, raw.baseSha256);
        out.delete(p);
      } else {
        if (cur) throw corrupt(`restore over existing file ${p}`);
        const data = Buffer.from(raw.content, 'base64');
        check(data, raw.baseSha256);
        out.set(p, data);
      }
    } else if (raw.encoding === 'lines') {
      check(cur, direction === 'forward' ? raw.baseSha256 : raw.resultSha256);
      const lines = cur!.toString('utf8').split('\n');
      const remove = direction === 'forward' ? raw.deleted : raw.inserted;
      const insert = direction === 'forward' ? raw.inserted : raw.deleted;
      const actual = lines.slice(raw.start, raw.start + remove.length);
      if (actual.length !== remove.length || actual.some((l, i) => l !== remove[i])) throw corrupt(`hunk does not apply at ${p}`);
      lines.splice(raw.start, remove.length, ...insert);
      const data = Buffer.from(lines.join('\n'), 'utf8');
      check(data, direction === 'forward' ? raw.resultSha256 : raw.baseSha256);
      out.set(p, data);
    } else {
      check(cur, direction === 'forward' ? raw.baseSha256 : raw.resultSha256);
      const data = Buffer.from(direction === 'forward' ? raw.content : raw.previous, 'base64');
      check(data, direction === 'forward' ? raw.resultSha256 : raw.baseSha256);
      out.set(p, data);
    }
  }
  return out;
}

export function applyPatch(base: Tree, patch: Patch): Tree {
  if (patch.format !== 'epa-patch-v1') throw corrupt('unknown patch format');
  if (manifestHash(base) !== patch.baseManifestHash) throw corrupt('patch base does not match reconstructed state');
  const out = applyOps(base, patch, 'forward');
  if (manifestHash(out) !== patch.resultManifestHash) throw corrupt('patch result manifest mismatch');
  return out;
}

export function reversePatch(result: Tree, patch: Patch): Tree {
  if (manifestHash(result) !== patch.resultManifestHash) throw corrupt('reverse base does not match patch result');
  const out = applyOps(result, patch, 'reverse');
  if (manifestHash(out) !== patch.baseManifestHash) throw corrupt('reverse result manifest mismatch');
  return out;
}

export function buildCheckpoint(tree: Tree): Checkpoint {
  return {
    format: 'epa-checkpoint-v1',
    manifestHash: manifestHash(tree),
    files: manifestOf(tree).map((m) => ({ path: m.path, sha256: m.sha256, content: tree.get(m.path)!.toString('base64') })),
  };
}

export function readCheckpoint(c: Checkpoint): Tree {
  if (c.format !== 'epa-checkpoint-v1' || !Array.isArray(c.files)) throw corrupt('unknown checkpoint format');
  const tree: Tree = new Map();
  for (const f of c.files) {
    const p = normalizeWorkspacePath(f.path);
    if (tree.has(p)) throw corrupt(`duplicate path ${p}`);
    const data = Buffer.from(f.content, 'base64');
    if (sha256Hex(data) !== f.sha256) throw corrupt(`content hash mismatch at ${p}`);
    tree.set(p, data);
  }
  if (manifestHash(tree) !== c.manifestHash) throw corrupt('checkpoint manifest mismatch');
  return tree;
}

export function encodeObject(obj: unknown): Buffer {
  return gzipSync(Buffer.from(JSON.stringify(obj), 'utf8'));
}

/** Decompresses with a hard output cap so a crafted object cannot exhaust memory (archive bomb). */
export function decodeObject<T>(data: Buffer, maxBytes: number): T {
  let raw: Buffer;
  try {
    raw = gunzipSync(data, { maxOutputLength: maxBytes });
  } catch (e: any) {
    if (e?.code === 'ERR_BUFFER_TOO_LARGE' || /maxOutputLength|too large/i.test(String(e?.message))) {
      throw new DomainError('PAYLOAD_TOO_LARGE', 'snapshot object exceeds decompression limit');
    }
    throw corrupt('object is not valid gzip');
  }
  try {
    return JSON.parse(raw.toString('utf8')) as T;
  } catch {
    throw corrupt('object is not valid JSON');
  }
}
