import { mkdtemp, readdir } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { unzipSafe, zipStore } from '../src/zip.js';

const dirs: string[] = [];

afterEach(async () => {
  const { rm } = await import('node:fs/promises');
  await Promise.all(dirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

describe('unzipSafe', () => {
  it('skips a nested .git directory and keeps the project files', async () => {
    const dest = await mkdtemp(path.join(os.tmpdir(), 'epa-zip-'));
    dirs.push(dest);
    const zip = zipStore([
      { name: 'Resume_gen/.git/config', data: '[core]\n' },
      { name: 'Resume_gen/.next/cache/webpack.js', data: 'build\n' },
      { name: 'Resume_gen/node_modules/react/index.js', data: 'module.exports = {}\n' },
      { name: 'Resume_gen/src/app.js', data: 'console.log(1)\n' },
    ]);
    const result = await unzipSafe(zip, dest);
    expect(result).toEqual({ files: 1, skipped: 3 });
    expect(await readdir(path.join(dest, 'src'))).toEqual(['app.js']);
  });

  it('still rejects a path that leaves the archive', async () => {
    const dest = await mkdtemp(path.join(os.tmpdir(), 'epa-zip-'));
    dirs.push(dest);
    const zip = zipStore([{ name: '../secret.txt', data: 'no' }]);
    await expect(unzipSafe(zip, dest)).rejects.toThrow(/недопустимый путь/);
  });
});
