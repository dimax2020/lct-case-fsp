import { spawn } from 'node:child_process';

export interface ExecResult {
  exitCode: number | null;
  stdout: string;
  stderr: string;
  durationMs: number;
  timedOut: boolean;
  truncated: boolean;
}

/** Spawns a process without a shell, caps captured output and enforces a hard timeout. */
export function runProcess(
  cmd: string,
  args: string[],
  opts: { cwd?: string; env?: NodeJS.ProcessEnv; timeoutMs: number; maxOutputBytes?: number; onTimeout?: () => void },
): Promise<ExecResult> {
  const max = opts.maxOutputBytes ?? 256 * 1024;
  const started = Date.now();
  return new Promise((resolve) => {
    let stdout = '';
    let stderr = '';
    let truncated = false;
    let timedOut = false;
    let settled = false;
    const child = spawn(cmd, args, { cwd: opts.cwd, env: opts.env ?? {}, stdio: ['ignore', 'pipe', 'pipe'], detached: process.platform !== 'win32' });
    const append = (which: 'out' | 'err', d: Buffer) => {
      const cur = which === 'out' ? stdout : stderr;
      if (cur.length >= max) {
        truncated = true;
        return;
      }
      const next = cur + d.toString('utf8').slice(0, max - cur.length);
      if (which === 'out') stdout = next;
      else stderr = next;
    };
    child.stdout.on('data', (d: Buffer) => append('out', d));
    child.stderr.on('data', (d: Buffer) => append('err', d));
    const timer = setTimeout(() => {
      timedOut = true;
      opts.onTimeout?.();
      try {
        if (child.pid) process.kill(-child.pid, 'SIGKILL');
      } catch {
        child.kill('SIGKILL');
      }
    }, opts.timeoutMs);
    const finish = (exitCode: number | null, extraErr = '') => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ exitCode: timedOut ? null : exitCode, stdout, stderr: stderr + extraErr, durationMs: Date.now() - started, timedOut, truncated });
    };
    child.on('error', (e) => finish(null, `spawn error: ${e.message}`));
    child.on('close', (code) => finish(code));
  });
}
