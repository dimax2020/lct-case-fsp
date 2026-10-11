import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { DomainError, type SandboxPolicy } from '@epa/domain';
import { runProcess } from '@epa/rde';

export interface SandboxRunInput {
  runId: string;
  sourceDir: string;
  argv: string[];
  policy: SandboxPolicy;
}

export interface SandboxRunOutput {
  exitCode: number | null;
  stdout: string;
  stderr: string;
  durationMs: number;
  timedOut: boolean;
  infraError: string | null;
}

export interface SandboxDriver {
  readonly name: 'docker' | 'local';
  readonly isolated: boolean;
  run(input: SandboxRunInput): Promise<SandboxRunOutput>;
}

const ARG_SAFE = /^[A-Za-z0-9_./:=@+,-]+$/;

/**
 * docker run arguments for one sandbox job. The snapshot copy is mounted read-only and copied to a
 * size-limited tmpfs; there is no network, no host env, no capabilities and a hard kill timeout.
 */
export function dockerSandboxArgs(input: SandboxRunInput, image: string, containerName: string): string[] {
  const p = input.policy;
  if (p.network !== 'none') throw new DomainError('VALIDATION', 'sandbox network must be none');
  if (!path.isAbsolute(input.sourceDir)) throw new DomainError('VALIDATION', 'source dir must be absolute');
  for (const a of input.argv) if (!ARG_SAFE.test(a)) throw new DomainError('VALIDATION', `unsafe test command argument: ${a}`);
  return [
    'run', '--rm',
    '--name', containerName,
    '--label', `epa.sandbox_run=${input.runId}`,
    '--network', 'none',
    '--read-only',
    '--tmpfs', `/tmp:rw,nosuid,nodev,size=${p.tmpfsMb}m,mode=1777`,
    '--cpus', String(p.cpus),
    '--memory', `${p.memoryMb}m`,
    '--memory-swap', `${p.memoryMb}m`,
    '--pids-limit', String(p.pidsLimit),
    '--cap-drop', 'ALL',
    '--security-opt', 'no-new-privileges',
    '--user', '1000:1000',
    '--ulimit', 'nofile=256:256',
    '--ulimit', `fsize=${p.tmpfsMb * 1024 * 1024}`,
    '--env', 'HOME=/tmp',
    '--env', 'CI=1',
    '--mount', `type=bind,source=${input.sourceDir},target=/src,readonly`,
    '--workdir', '/tmp',
    image,
    'sh', '-c', 'cp -R /src /tmp/w && cd /tmp/w && exec timeout -s KILL "$0" "$@"',
    String(p.timeoutSec),
    ...input.argv,
  ];
}

export class DockerSandboxDriver implements SandboxDriver {
  readonly name = 'docker' as const;
  readonly isolated = true;
  constructor(private readonly image: string, private readonly dockerBin = 'docker') {}

  async run(input: SandboxRunInput): Promise<SandboxRunOutput> {
    const name = `epa-sbx-${randomUUID().slice(0, 12)}`;
    const env = { PATH: process.env.PATH, HOME: process.env.HOME, DOCKER_HOST: process.env.DOCKER_HOST };
    const kill = () => void runProcess(this.dockerBin, ['kill', name], { env, timeoutMs: 15_000 });
    const r = await runProcess(this.dockerBin, dockerSandboxArgs(input, this.image, name), {
      env,
      timeoutMs: (input.policy.timeoutSec + 30) * 1000,
      maxOutputBytes: input.policy.maxLogBytes * 4,
      onTimeout: kill,
    });
    if (r.timedOut) await runProcess(this.dockerBin, ['rm', '-f', name], { env, timeoutMs: 15_000 });
    const killedByTimeout = r.exitCode === 137 && r.durationMs >= input.policy.timeoutSec * 1000 - 500;
    const timedOut = r.timedOut || killedByTimeout;
    // 125-127 are docker/runtime failures (image missing, daemon down) rather than test results.
    const infra = !timedOut && r.exitCode !== null && r.exitCode >= 125 && r.exitCode <= 127 && /docker|Error response|Unable to find|cannot connect/i.test(r.stderr);
    return {
      exitCode: timedOut ? null : r.exitCode,
      stdout: r.stdout,
      stderr: r.stderr,
      durationMs: r.durationMs,
      timedOut,
      infraError: infra ? `sandbox runtime error: ${r.stderr.trim().split('\n')[0].slice(0, 200)}` : r.exitCode === null && !timedOut ? 'sandbox process failed to start' : null,
    };
  }
}

/** Development-only, NOT isolated. Refused in production by config validation. */
export class LocalSandboxDriver implements SandboxDriver {
  readonly name = 'local' as const;
  readonly isolated = false;

  async run(input: SandboxRunInput): Promise<SandboxRunOutput> {
    const [bin, ...args] = input.argv;
    const r = await runProcess(bin === 'node' ? process.execPath : bin, args, {
      cwd: input.sourceDir,
      env: { PATH: path.dirname(process.execPath) + ':/usr/bin:/bin', HOME: input.sourceDir, CI: '1' },
      timeoutMs: input.policy.timeoutSec * 1000,
      maxOutputBytes: input.policy.maxLogBytes * 4,
    });
    return { exitCode: r.exitCode, stdout: r.stdout, stderr: r.stderr, durationMs: r.durationMs, timedOut: r.timedOut, infraError: null };
  }
}
