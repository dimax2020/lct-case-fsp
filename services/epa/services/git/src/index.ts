import { spawn, type ChildProcess } from 'node:child_process';
import { createReadStream } from 'node:fs';
import type { Readable } from 'node:stream';
import { cp, mkdir, readdir, rm, mkdtemp } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { DomainError, isSafeRelativePath } from '@epa/domain';
import { unzipSafe } from './zip.js';

export interface GitResult {
  code: number;
  stdout: string;
  stderr: string;
}

export interface CommitInfo {
  sha: string;
  author: string;
  committedAt: string;
  message: string;
}

const PLATFORM_AUTHOR = { name: 'EPA Platform', email: 'platform@epa.local' };

/**
 * Git integration. Each practice has a bare repository in git storage; each workspace has
 * a git dir kept *outside* the candidate-writable volume, so repository config, hooks and
 * refs cannot be tampered with from inside the RDE. Commits are created by the server with
 * the session identity, which makes the history server-verified.
 */
export class GitService {
  constructor(private readonly storageDir: string) {}

  barePath(practiceId: string): string {
    if (!/^prc_[a-f0-9]{32}$/.test(practiceId)) throw new DomainError('VALIDATION', 'invalid practice id');
    return path.join(this.storageDir, `${practiceId}.git`);
  }

  private async run(args: string[], opts: { gitDir?: string; workTree?: string; cwd?: string; input?: string } = {}): Promise<GitResult> {
    const home = await mkdtemp(path.join(os.tmpdir(), 'epa-git-home-'));
    const env: NodeJS.ProcessEnv = {
      PATH: process.env.PATH,
      HOME: home,
      GIT_CONFIG_NOSYSTEM: '1',
      GIT_CONFIG_GLOBAL: '/dev/null',
      GIT_TERMINAL_PROMPT: '0',
      GIT_ASKPASS: '/bin/false',
      LC_ALL: 'C',
    };
    if (opts.gitDir) env.GIT_DIR = opts.gitDir;
    if (opts.workTree) env.GIT_WORK_TREE = opts.workTree;
    const safeArgs = [
      '-c', 'core.hooksPath=/dev/null',
      '-c', 'core.fsmonitor=false',
      '-c', 'core.symlinks=false',
      '-c', 'protocol.allow=never',
      '-c', 'protocol.file.allow=always',
      '-c', 'commit.gpgsign=false',
      ...args,
    ];
    try {
      return await new Promise<GitResult>((resolve, reject) => {
        const child = spawn('git', safeArgs, { env, cwd: opts.cwd ?? opts.workTree ?? this.storageDir, stdio: ['pipe', 'pipe', 'pipe'] });
        let stdout = '';
        let stderr = '';
        child.stdout.on('data', (d) => (stdout += d));
        child.stderr.on('data', (d) => (stderr += d));
        child.on('error', reject);
        child.on('close', (code) => resolve({ code: code ?? -1, stdout, stderr }));
        if (opts.input) child.stdin.write(opts.input);
        child.stdin.end();
      });
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }

  private async must(args: string[], opts: Parameters<GitService['run']>[1] = {}): Promise<string> {
    const r = await this.run(args, opts);
    if (r.code !== 0) throw new Error(`git ${args[0]} failed: ${r.stderr.trim().slice(0, 500)}`);
    return r.stdout;
  }

  /** Creates the practice repository from a template with a single platform-authored commit. */
  async initPracticeRepo(practiceId: string, templateRepoDir: string): Promise<string> {
    const bare = this.barePath(practiceId);
    await mkdir(this.storageDir, { recursive: true });
    const exists = await this.run(['rev-parse', '--verify', 'refs/heads/main'], { gitDir: bare });
    if (exists.code === 0) return exists.stdout.trim();
    await this.must(['init', '--bare', '--initial-branch=main', bare]);
    const tmp = await mkdtemp(path.join(os.tmpdir(), 'epa-tpl-'));
    const tmpGit = `${tmp}-git`;
    try {
      await cp(templateRepoDir, tmp, { recursive: true, verbatimSymlinks: true, filter: (src) => !src.split(path.sep).includes('.git') });
      await this.must(['init', '--initial-branch=main'], { gitDir: tmpGit, workTree: tmp });
      await this.must(['add', '-A'], { gitDir: tmpGit, workTree: tmp });
      await this.must(
        ['-c', `user.name=${PLATFORM_AUTHOR.name}`, '-c', `user.email=${PLATFORM_AUTHOR.email}`, 'commit', '-q', '-m', 'Initial task template'],
        { gitDir: tmpGit, workTree: tmp },
      );
      await this.must(['push', '-q', bare, 'HEAD:refs/heads/main'], { gitDir: tmpGit, workTree: tmp });
      return (await this.must(['rev-parse', 'HEAD'], { gitDir: tmpGit })).trim();
    } finally {
      await rm(tmp, { recursive: true, force: true });
      await rm(tmpGit, { recursive: true, force: true });
    }
  }

  /** Checks out the practice repository into a workspace with an external git dir. */
  async checkoutWorkspace(practiceId: string, repositoryDir: string, gitDir: string): Promise<void> {
    await mkdir(repositoryDir, { recursive: true });
    const opts = { gitDir, workTree: repositoryDir };
    await this.must(['init', '-q', '--initial-branch=main'], opts);
    await this.run(['remote', 'remove', 'origin'], opts);
    await this.must(['remote', 'add', 'origin', this.barePath(practiceId)], opts);
    await this.must(['fetch', '-q', 'origin', 'main'], opts);
    await this.must(['reset', '-q', '--hard', 'origin/main'], opts);
  }

  async headSha(gitDir: string): Promise<string | null> {
    const r = await this.run(['rev-parse', 'HEAD'], { gitDir });
    return r.code === 0 ? r.stdout.trim() : null;
  }

  async status(gitDir: string, workTree: string): Promise<string> {
    return this.must(['status', '--porcelain=v1', '--untracked-files=all'], { gitDir, workTree });
  }

  async diffStat(gitDir: string, workTree: string): Promise<string> {
    return this.must(['diff', '--stat', '--no-color', '--no-ext-diff', 'HEAD'], { gitDir, workTree });
  }

  /** Commits all workspace changes as the session identity and pushes to the practice repository. */
  async commit(input: {
    practiceId: string;
    gitDir: string;
    workTree: string;
    message: string;
    authorName: string;
    authorEmail: string;
  }): Promise<{ sha: string; changedFiles: string[] }> {
    const opts = { gitDir: input.gitDir, workTree: input.workTree };
    await this.must(['add', '-A'], opts);
    const staged = await this.must(['diff', '--cached', '--name-only', '-z'], opts);
    if (!staged.trim()) throw new DomainError('CONFLICT', 'nothing to commit');
    await this.must(
      ['-c', `user.name=${input.authorName}`, '-c', `user.email=${input.authorEmail}`, 'commit', '-q', '--no-verify', '-F', '-'],
      { ...opts, input: input.message },
    );
    const sha = (await this.must(['rev-parse', 'HEAD'], opts)).trim();
    const changed = (await this.must(['show', '--name-only', '--format=', '-z', sha], opts)).split('\0').filter(Boolean);
    await this.must(['push', '-q', 'origin', 'HEAD:refs/heads/main'], opts);
    return { sha, changedFiles: changed.filter(isSafeRelativePath) };
  }

  async log(practiceId: string, limit = 200): Promise<CommitInfo[]> {
    const r = await this.run(['log', `-n${limit}`, '--format=%H%x1f%an%x1f%aI%x1f%s%x1e', 'main'], { gitDir: this.barePath(practiceId) });
    if (r.code !== 0) return [];
    return r.stdout
      .split('\x1e')
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        const [sha, author, committedAt, message] = l.split('\x1f');
        return { sha, author, committedAt, message };
      });
  }

  async deletePracticeRepo(practiceId: string): Promise<void> {
    await rm(this.barePath(practiceId), { recursive: true, force: true });
  }

  /** Copies the employer repository so a candidate who applied gets the same project. */
  async cloneBare(fromId: string, toId: string): Promise<boolean> {
    const src = this.barePath(fromId);
    const probe = await this.run(['rev-parse', '--verify', 'refs/heads/main'], { gitDir: src });
    if (probe.code !== 0) return false;
    const dest = this.barePath(toId);
    await rm(dest, { recursive: true, force: true });
    await mkdir(this.storageDir, { recursive: true });
    await this.must(['clone', '--bare', '--quiet', src, dest]);
    return true;
  }

  /** Replaces the practice tree with a zip uploaded by the employer. Dependency folders are left out. */
  async importArchive(practiceId: string, zip: Buffer | string, message: string, onFile?: (done: number, total: number) => void): Promise<{ sha: string; files: number; skipped: number }> {
    const tmp = await mkdtemp(path.join(os.tmpdir(), 'epa-zip-'));
    try {
      const extracted = await unzipSafe(zip, tmp, onFile);
      const sha = await this.seedFromDirectory(practiceId, tmp, message);
      return { sha, files: extracted.files, skipped: extracted.skipped };
    } finally {
      await rm(tmp, { recursive: true, force: true });
    }
  }

  /** Commits `sourceDir` as `main`. An existing history gets one more commit, not a rewrite. */
  async seedFromDirectory(practiceId: string, sourceDir: string, message: string): Promise<string> {
    const bare = this.barePath(practiceId);
    await mkdir(this.storageDir, { recursive: true });
    const hasMain = (await this.run(['rev-parse', '--verify', 'refs/heads/main'], { gitDir: bare })).code === 0;
    if (!hasMain) await this.must(['init', '--bare', '--initial-branch=main', bare]);
    const tmp = await mkdtemp(path.join(os.tmpdir(), 'epa-seed-'));
    const tmpGit = `${tmp}-git`;
    try {
      if (hasMain) await this.must(['clone', '--quiet', bare, tmp]);
      else await this.copyTree(sourceDir, tmp);
      if (hasMain) {
        for (const name of await readdir(tmp)) {
          if (name === '.git') continue;
          await rm(path.join(tmp, name), { recursive: true, force: true });
        }
        await this.copyTree(sourceDir, tmp);
      }
      const opts = hasMain ? { cwd: tmp } : { gitDir: tmpGit, workTree: tmp };
      if (!hasMain) await this.must(['init', '--initial-branch=main'], opts);
      await this.must(['add', '-A'], opts);
      const status = await this.run(['status', '--porcelain'], opts);
      if (!status.stdout.trim()) throw new DomainError('VALIDATION', 'в архиве нет файлов');
      await this.must(
        ['-c', `user.name=${PLATFORM_AUTHOR.name}`, '-c', `user.email=${PLATFORM_AUTHOR.email}`, 'commit', '-q', '-m', message],
        opts,
      );
      if (hasMain) await this.must(['push', '--quiet', 'origin', 'HEAD:refs/heads/main'], { cwd: tmp });
      else await this.must(['push', '--quiet', bare, 'HEAD:refs/heads/main'], opts);
      return (await this.must(['rev-parse', 'HEAD'], opts)).trim();
    } finally {
      await rm(tmp, { recursive: true, force: true });
      await rm(tmpGit, { recursive: true, force: true });
    }
  }

  private async copyTree(src: string, dest: string): Promise<void> {
    await mkdir(dest, { recursive: true });
    for (const entry of await readdir(src, { withFileTypes: true })) {
      if (entry.name === '.git' || entry.name === '__MACOSX') continue;
      const from = path.join(src, entry.name);
      const to = path.join(dest, entry.name);
      if (entry.isDirectory()) await this.copyTree(from, to);
      else if (entry.isFile()) await cp(from, to);
    }
  }

  async listTree(practiceId: string): Promise<{ path: string; size: number }[]> {
    const gitDir = this.barePath(practiceId);
    const probe = await this.run(['rev-parse', '--verify', 'refs/heads/main'], { gitDir });
    if (probe.code !== 0) throw new DomainError('CONFLICT', 'репозиторий ещё не готов');
    const r = await this.run(['ls-tree', '-r', '-l', 'main'], { gitDir });
    if (r.code !== 0) return [];
    const out: { path: string; size: number }[] = [];
    for (const line of r.stdout.split('\n')) {
      const tab = line.indexOf('\t');
      if (tab < 0) continue;
      const filePath = line.slice(tab + 1);
      if (!isSafeRelativePath(filePath)) continue;
      const size = Number(line.slice(0, tab).trim().split(/\s+/).at(-1));
      out.push({ path: filePath, size: Number.isFinite(size) ? size : 0 });
    }
    return out;
  }

  async readBlob(practiceId: string, filePath: string): Promise<{ path: string; content: string; binary: boolean; size: number }> {
    if (!isSafeRelativePath(filePath)) throw new DomainError('VALIDATION', 'некорректный путь');
    const gitDir = this.barePath(practiceId);
    let buf: Buffer;
    try {
      buf = await this.runRaw(['show', `main:${filePath}`], null, gitDir);
    } catch {
      throw new DomainError('NOT_FOUND', 'файл не найден');
    }
    if (buf.length > 5_000_000 || buf.includes(0)) {
      return { path: filePath, content: '', binary: true, size: buf.length };
    }
    return { path: filePath, content: buf.toString('utf8'), binary: false, size: buf.length };
  }

  /** Checks out the practice repository so a push can be snapshotted. */
  async materialize(practiceId: string, dest: string): Promise<void> {
    await this.must(['clone', '--quiet', this.barePath(practiceId), dest]);
  }

  /**
   * Streams a packfile. `input` is a request body or a path to a spooled body, so a large
   * clone or push is not held in one buffer.
   */
  async streamRpc(practiceId: string, service: 'upload-pack' | 'receive-pack', input: Buffer | string | null): Promise<{ stdout: Readable; finished: Promise<void> }> {
    const gitDir = this.barePath(practiceId);
    const probe = await this.run(['rev-parse', '--is-bare-repository'], { gitDir });
    if (probe.code !== 0) throw new DomainError('CONFLICT', 'repository is not ready yet');
    const child = this.spawnGit(['-c', 'protocol.version=1', service === 'upload-pack' ? 'upload-pack' : 'receive-pack', '--stateless-rpc', gitDir]);
    const stdin = child.stdin;
    const stdout = child.stdout;
    if (!stdin || !stdout) throw new Error('git stdio is not piped');
    if (typeof input === 'string') createReadStream(input).pipe(stdin);
    else {
      if (input) stdin.write(input);
      stdin.end();
    }
    const finished = new Promise<void>((resolve, reject) => {
      let stderr = '';
      child.stderr.on('data', (d) => {
        stderr += d;
      });
      child.on('error', reject);
      child.on('close', (code) => {
        if (code !== 0) reject(new Error(`git ${service} failed: ${stderr.trim().slice(0, 400)}`));
        else resolve();
      });
    });
    return { stdout, finished };
  }

  async httpRpc(practiceId: string, service: 'upload-pack' | 'receive-pack', body: Buffer | null, advertise: boolean): Promise<Buffer> {
    const gitDir = this.barePath(practiceId);
    const probe = await this.run(['rev-parse', '--is-bare-repository'], { gitDir });
    if (probe.code !== 0) throw new DomainError('CONFLICT', 'repository is not ready yet');
    const command = service === 'upload-pack' ? 'upload-pack' : 'receive-pack';
    const args = ['-c', 'protocol.version=1', command, '--stateless-rpc', ...(advertise ? ['--advertise-refs'] : []), gitDir];
    return this.runRaw(args, advertise ? null : body);
  }

  private spawnGit(args: string[], gitDir?: string): ChildProcess {
    const safeArgs = [
      '-c', 'core.hooksPath=/dev/null',
      '-c', 'core.fsmonitor=false',
      '-c', 'core.symlinks=false',
      '-c', 'protocol.allow=never',
      '-c', 'protocol.file.allow=always',
      '-c', 'commit.gpgsign=false',
      ...args,
    ];
    return spawn('git', safeArgs, {
        env: {
          PATH: process.env.PATH,
          GIT_CONFIG_NOSYSTEM: '1',
          GIT_CONFIG_GLOBAL: '/dev/null',
          GIT_TERMINAL_PROMPT: '0',
          LC_ALL: 'C',
          ...(gitDir ? { GIT_DIR: gitDir } : {}),
        },
        cwd: this.storageDir,
        stdio: ['pipe', 'pipe', 'pipe'],
      });
  }

  private runRaw(args: string[], input: Buffer | null, gitDir?: string): Promise<Buffer> {
    return new Promise((resolve, reject) => {
      const child = this.spawnGit(args, gitDir);
      const chunks: Buffer[] = [];
      let stderr = '';
      child.stdout.on('data', (d) => chunks.push(Buffer.from(d)));
      child.stderr.on('data', (d) => (stderr += d));
      child.on('error', reject);
      child.on('close', (code) => {
        if (code !== 0) reject(new Error(`git ${args.filter((a) => !a.startsWith('-')).slice(-2, -1)[0] ?? 'rpc'} failed: ${stderr.trim().slice(0, 400)}`));
        else resolve(Buffer.concat(chunks));
      });
      if (input) child.stdin.write(input);
      child.stdin.end();
    });
  }
}
