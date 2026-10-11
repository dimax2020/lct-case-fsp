import { describe, expect, it } from 'vitest';
import { gzipSync } from 'node:zlib';
import { applyPatch, buildCheckpoint, decodeObject, diffTrees, encodeObject, manifestHash, readCheckpoint, reversePatch, type Tree } from '@epa/snapshots';

const tree = (o: Record<string, string | Buffer>): Tree => new Map(Object.entries(o).map(([k, v]) => [k, Buffer.isBuffer(v) ? v : Buffer.from(v)]));

describe('snapshot patch format', () => {
  const base = tree({ 'src/a.js': 'line1\nline2\nline3\n', 'src/b.js': 'remove me', 'img.bin': Buffer.from([0, 1, 2, 3]) });
  const next = tree({ 'src/a.js': 'line1\nCHANGED\nline3\nline4\n', 'src/c.js': 'new file', 'img.bin': Buffer.from([0, 9, 9]) });

  it('applies forward and reverses back to byte-identical trees', () => {
    const patch = diffTrees(base, next);
    const forward = applyPatch(base, patch);
    expect(manifestHash(forward)).toBe(manifestHash(next));
    for (const [k, v] of next) expect(forward.get(k)!.equals(v)).toBe(true);
    const back = reversePatch(forward, patch);
    expect(manifestHash(back)).toBe(manifestHash(base));
    expect(back.get('img.bin')!.equals(base.get('img.bin')!)).toBe(true);
  });

  it('manifest hash is order independent and content sensitive', () => {
    expect(manifestHash(tree({ a: '1', b: '2' }))).toBe(manifestHash(tree({ b: '2', a: '1' })));
    expect(manifestHash(tree({ a: '1' }))).not.toBe(manifestHash(tree({ a: '2' })));
  });

  it('a corrupted patch yields an explicit integrity error, never a different state', () => {
    const patch = diffTrees(base, next);
    const tampered = structuredClone(patch);
    const op = tampered.ops.find((o) => o.op === 'modify' && o.encoding === 'lines') as any;
    op.inserted = ['EVIL'];
    expect(() => applyPatch(base, tampered)).toThrow(/corrupted/);
    expect(() => applyPatch(tree({ other: 'x' }), patch)).toThrow(/corrupted/);
  });

  it('checkpoints verify per-file hashes and reject unsafe paths', () => {
    const cp = buildCheckpoint(base);
    expect(manifestHash(readCheckpoint(cp))).toBe(manifestHash(base));
    const bad = structuredClone(cp);
    bad.files[0].content = Buffer.from('tampered').toString('base64');
    expect(() => readCheckpoint(bad)).toThrow(/corrupted/);
    const traversal = structuredClone(cp);
    traversal.files[0].path = '../../etc/passwd';
    expect(() => readCheckpoint(traversal)).toThrow();
  });

  it('decoding enforces a decompression cap (archive bomb)', () => {
    const bomb = gzipSync(Buffer.alloc(50 * 1024 * 1024, 0x20));
    expect(bomb.length).toBeLessThan(200 * 1024);
    expect(() => decodeObject(bomb, 1024 * 1024)).toThrow(/decompression limit/);
    expect(decodeObject<{ a: number }>(encodeObject({ a: 1 }), 1024)).toEqual({ a: 1 });
    expect(() => decodeObject(Buffer.from('not gzip'), 1024)).toThrow(/corrupted/);
  });
});
