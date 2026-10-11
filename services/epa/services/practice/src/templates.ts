import { readdir, readFile, stat, lstat } from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { DomainError } from '@epa/domain';

export interface TaskTemplate {
  name: string;
  repoDir: string;
  version: string;
  testCommand: string[];
  coverage: boolean;
}

async function hashTree(dir: string, rel = ''): Promise<string[]> {
  const out: string[] = [];
  const entries = (await readdir(path.join(dir, rel), { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name));
  for (const e of entries) {
    const r = rel ? `${rel}/${e.name}` : e.name;
    if (e.isDirectory()) out.push(...(await hashTree(dir, r)));
    else if (e.isFile()) out.push(`${r}:${createHash('sha256').update(await readFile(path.join(dir, r))).digest('hex')}`);
  }
  return out;
}

/** Practice templates live on the platform side: `<templatesDir>/<name>/{task.json, repo/}`. */
export class TemplateCatalog {
  constructor(private readonly dir: string) {}

  async get(name: string): Promise<TaskTemplate> {
    if (!/^[a-z0-9-]{1,64}$/.test(name)) throw new DomainError('VALIDATION', 'invalid template name');
    const base = path.join(this.dir, name);
    const repoDir = path.join(base, 'repo');
    try {
      if (!(await stat(repoDir)).isDirectory() || (await lstat(base)).isSymbolicLink()) throw new Error();
    } catch {
      throw new DomainError('VALIDATION', `unknown template ${name}`);
    }
    const task = JSON.parse(await readFile(path.join(base, 'task.json'), 'utf8')) as { testCommand?: string[]; coverage?: boolean };
    const version = createHash('sha256').update((await hashTree(repoDir)).join('\n')).digest('hex').slice(0, 16);
    return { name, repoDir, version: `${name}@${version}`, testCommand: task.testCommand ?? ['node', '--test'], coverage: task.coverage ?? false };
  }

  async list(): Promise<string[]> {
    const entries = await readdir(this.dir, { withFileTypes: true });
    return entries.filter((e) => e.isDirectory() && e.name !== 'auth-service').map((e) => e.name).sort();
  }
}
