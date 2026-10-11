import path from 'node:path';
import { DomainError, type WorkspacePolicy } from '@epa/domain';
import { runProcess, type ExecResult } from './process.js';

export interface ProvisionSpec {
  workspaceId: string;
  identity: string;
  repositoryDir: string;
  policy: WorkspacePolicy;
}

export interface RdeDriver {
  readonly name: 'docker' | 'local';
  readonly isolated: boolean;
  provision(spec: ProvisionSpec): Promise<{ runtimeRef: string }>;
  exec(runtimeRef: string, argv: string[], opts: { timeoutSec: number; repositoryDir: string }): Promise<ExecResult>;
  health(runtimeRef: string): Promise<'running' | 'missing'>;
  teardown(runtimeRef: string): Promise<void>;
}

export const containerName = (workspaceId: string) => {
  if (!/^ws_[a-f0-9]{32}$/.test(workspaceId)) throw new DomainError('VALIDATION', 'invalid workspace id');
  return `epa-${workspaceId.replace('_', '-')}`;
};

/**
 * docker run arguments for an RDE container. No network, read-only root FS, all capabilities
 * dropped, no privilege escalation, unprivileged user, resource limits. The only writable
 * mounts are the workspace repository and a size-limited tmpfs.
 */
export function dockerWorkspaceArgs(spec: ProvisionSpec, image: string): string[] {
  const p = spec.policy;
  if (p.network !== 'none') throw new DomainError('VALIDATION', 'RDE network must be none');
  if (!path.isAbsolute(spec.repositoryDir)) throw new DomainError('VALIDATION', 'repository dir must be absolute');
  return [
    'run', '-d',
    '--name', containerName(spec.workspaceId),
    '--label', `epa.workspace=${spec.workspaceId}`,
    '--label', `epa.identity=${spec.identity}`,
    '--hostname', 'workspace',
    '--network', 'none',
    '--read-only',
    '--tmpfs', `/tmp:rw,nosuid,nodev,size=${p.diskMb}m,mode=1777`,
    '--cpus', String(p.cpus),
    '--memory', `${p.memoryMb}m`,
    '--memory-swap', `${p.memoryMb}m`,
    '--pids-limit', String(p.pidsLimit),
    '--cap-drop', 'ALL',
    '--security-opt', 'no-new-privileges',
    '--user', p.user,
    '--ulimit', 'nofile=1024:1024',
    '--env', 'HOME=/tmp',
    '--mount', `type=bind,source=${spec.repositoryDir},target=/workspace`,
    '--workdir', '/workspace',
    image,
    'sleep', 'infinity',
  ];
}

export class DockerRdeDriver implements RdeDriver {
  readonly name = 'docker' as const;
  readonly isolated = true;
  constructor(private readonly image: string, private readonly dockerBin = 'docker') {}

  private docker(args: string[], timeoutMs = 60_000) {
    return runProcess(this.dockerBin, args, { env: { PATH: process.env.PATH, HOME: process.env.HOME, DOCKER_HOST: process.env.DOCKER_HOST }, timeoutMs });
  }

  async provision(spec: ProvisionSpec) {
    const name = containerName(spec.workspaceId);
    await this.docker(['rm', '-f', name]);
    const r = await this.docker(dockerWorkspaceArgs(spec, this.image), 120_000);
    if (r.exitCode !== 0) throw new Error(`docker run failed: ${r.stderr.trim().slice(0, 300)}`);
    return { runtimeRef: name };
  }

  async exec(runtimeRef: string, argv: string[], opts: { timeoutSec: number }) {
    const r = await this.docker(
      ['exec', '-u', '1000:1000', '-w', '/workspace', '-e', 'HOME=/tmp', runtimeRef, 'timeout', '-s', 'KILL', String(opts.timeoutSec), ...argv],
      (opts.timeoutSec + 15) * 1000,
    );
    const timedOut = r.timedOut || (r.exitCode === 137 && r.durationMs >= opts.timeoutSec * 1000 - 250);
    return { ...r, timedOut, exitCode: timedOut ? null : r.exitCode };
  }

  async health(runtimeRef: string) {
    const r = await this.docker(['inspect', '-f', '{{.State.Running}}', runtimeRef]);
    return r.exitCode === 0 && r.stdout.trim() === 'true' ? 'running' : 'missing';
  }

  async teardown(runtimeRef: string) {
    await this.docker(['rm', '-f', runtimeRef]);
  }

  async inspectHostConfig(runtimeRef: string): Promise<Record<string, any>> {
    const r = await this.docker(['inspect', '-f', '{{json .HostConfig}}', runtimeRef]);
    return JSON.parse(r.stdout);
  }
}

/**
 * Development-only driver: runs commands as host processes in the workspace directory with a
 * scrubbed environment. Provides NO isolation and is refused in production by config.
 */
export class LocalRdeDriver implements RdeDriver {
  readonly name = 'local' as const;
  readonly isolated = false;
  private live = new Set<string>();

  async provision(spec: ProvisionSpec) {
    this.live.add(spec.workspaceId);
    return { runtimeRef: `local:${spec.workspaceId}` };
  }

  async exec(runtimeRef: string, argv: string[], opts: { timeoutSec: number; repositoryDir: string }) {
    if (!this.live.has(runtimeRef.replace('local:', ''))) throw new DomainError('GONE', 'workspace runtime not running');
    const [bin, ...args] = argv;
    const resolved = bin === 'node' ? process.execPath : bin;
    return runProcess(resolved, args, {
      cwd: opts.repositoryDir,
      env: { PATH: path.dirname(process.execPath) + ':/usr/bin:/bin', HOME: opts.repositoryDir, CI: '1' },
      timeoutMs: opts.timeoutSec * 1000,
    });
  }

  async health(runtimeRef: string) {
    return this.live.has(runtimeRef.replace('local:', '')) ? ('running' as const) : ('missing' as const);
  }

  async teardown(runtimeRef: string) {
    this.live.delete(runtimeRef.replace('local:', ''));
  }
}
