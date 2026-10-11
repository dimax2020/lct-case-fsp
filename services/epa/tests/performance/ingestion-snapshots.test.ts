import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { SOLUTION, call, createTestPlatform, startPractice, type TestPlatform } from '@epa/test-fixtures';
import { FakeClock } from '@epa/platform';
import { applyPatch, diffTrees, manifestHash, type Tree } from '@epa/snapshots';

describe('performance: telemetry volume and snapshot chains', () => {
  let t: TestPlatform;
  let clock: FakeClock;
  beforeAll(async () => {
    clock = new FakeClock(new Date());
    t = await createTestPlatform({ clock });
  });
  afterAll(async () => t.close());

  it('ingests many workspace saves and lists Timeline within a bounded time', async () => {
    const s = await startPractice(t, { snapshotPolicy: { intervalSec: 10, significantSaveBytes: 8, checkpointEvery: 4 } });
    const t0 = Date.now();
    for (let i = 0; i < 36; i++) {
      clock.advance(11_000);
      const content = `${SOLUTION['src/auth/session.js']}\nexport const tick = ${i};\n`;
      const w = await call(t.app, 'PUT', `/v1/workspaces/${s.workspaceId}/file`, s.candidateToken, {
        path: 'src/auth/session.js',
        content,
        editorStats: { pastedChars: 0 },
      });
      expect(w.status).toBe(200);
    }
    await t.platform.workspaces.flushAll();
    const pages: any[] = [];
    let cursor: string | undefined;
    do {
      const q = cursor ? `&cursor=${encodeURIComponent(cursor)}` : '';
      const tl = await call(t.app, 'GET', `/v1/practices/${s.practiceId}/timeline?limit=100${q}`, t.employerToken);
      expect(tl.status).toBe(200);
      pages.push(...tl.body.items);
      cursor = tl.body.nextCursor ?? undefined;
    } while (cursor);
    expect(pages.length).toBeGreaterThan(40);
    const types = new Set(pages.map((e) => e.type));
    expect(types.has('file_saved')).toBe(true);
    expect(types.has('snapshot_created')).toBe(true);
    const lastSnap = [...pages].reverse().find((e) => e.type === 'snapshot_created');
    const file = await call(t.app, 'GET', `/v1/snapshots/${lastSnap.refs.snapshotId}/file?path=src/auth/session.js`, t.employerToken);
    expect(file.body.content).toContain('tick = 35');
    expect(Date.now() - t0).toBeLessThan(90_000);
  });

  it('reconstructs a long patch chain byte-identically', () => {
    const t0 = Date.now();
    let cur: Tree = new Map([['a.txt', Buffer.from('v0\n')]]);
    const hashes = [manifestHash(cur)];
    const patches = [];
    for (let i = 1; i <= 40; i++) {
      const next: Tree = new Map([['a.txt', Buffer.from(`v${i}\n`)]]);
      if (i % 7 === 0) next.set('extra.txt', Buffer.from(String(i)));
      const patch = diffTrees(cur, next);
      patches.push(patch);
      cur = applyPatch(cur, patch);
      hashes.push(manifestHash(cur));
    }
    let replay: Tree = new Map([['a.txt', Buffer.from('v0\n')]]);
    for (const p of patches) replay = applyPatch(replay, p);
    expect(manifestHash(replay)).toBe(hashes[hashes.length - 1]);
    expect(replay.get('a.txt')!.toString()).toBe('v40\n');
    expect(Date.now() - t0).toBeLessThan(5_000);
  });
});
