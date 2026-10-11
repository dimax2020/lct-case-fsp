import { describe, expect, it } from 'vitest';
import { buildWorkspacePolicy } from '@epa/domain';
import { containerName, dockerWorkspaceArgs, parseWorkspaceCommand, splitArgv } from '@epa/rde';

const spec = (overrides = {}) => ({
  workspaceId: 'ws_0123456789abcdef0123456789abcdef',
  identity: 'ws-identity-1',
  repositoryDir: '/data/workspaces/ws_1/repository',
  policy: buildWorkspacePolicy({ cpus: 1.5, memoryMb: 768, sessionTtlMinutes: 30, ...overrides }),
});

describe('RDE docker policy', () => {
  it('applies CPU/RAM/disk/PID limits, no network, read-only root, dropped capabilities', () => {
    const args = dockerWorkspaceArgs(spec(), 'node:20-alpine');
    const joined = args.join(' ');
    expect(joined).toContain('--network none');
    expect(joined).toContain('--read-only');
    expect(joined).toContain('--cpus 1.5');
    expect(joined).toContain('--memory 768m');
    expect(joined).toContain('--memory-swap 768m');
    expect(joined).toContain('--pids-limit 256');
    expect(joined).toContain('--cap-drop ALL');
    expect(joined).toContain('--security-opt no-new-privileges');
    expect(joined).toContain('--user 1000:1000');
    expect(joined).toMatch(/--tmpfs \/tmp:rw,nosuid,nodev,size=4096m/);
    expect(joined).not.toMatch(/--privileged|docker\.sock|--network host|-p |--publish/);
    const mounts = args.filter((a, i) => args[i - 1] === '--mount');
    expect(mounts).toEqual(['type=bind,source=/data/workspaces/ws_1/repository,target=/workspace']);
  });

  it('only accepts canonical workspace ids for container names', () => {
    expect(containerName('ws_0123456789abcdef0123456789abcdef')).toBe('epa-ws-0123456789abcdef0123456789abcdef');
    expect(() => containerName('ws_../../x')).toThrow();
    expect(() => dockerWorkspaceArgs({ ...spec(), repositoryDir: 'relative/path' }, 'img')).toThrow();
  });
});

describe('workspace command policy', () => {
  it('splits argv with quotes, never via a shell', () => {
    expect(splitArgv(`node -e "console.log('a b')"`)).toEqual(['node', '-e', "console.log('a b')"]);
    expect(() => splitArgv('echo "unterminated')).toThrow();
  });

  it.each(['npm test', 'node --test', 'ls src', 'cat README.md', 'git status', 'npm run lint'])('allows %j', (c) => {
    expect(() => parseWorkspaceCommand(c)).not.toThrow();
  });

  it.each(['ssh host', 'curl http://x', 'npm install left-pad', 'ls; rm -rf /', 'cat $(whoami)', 'echo `id`', 'cat /etc/passwd', 'cat ../../secret', 'git push', 'sudo ls', 'bash -c ls', 'nc -l 1'])('rejects %j', (c) => {
    expect(() => parseWorkspaceCommand(c)).toThrow();
  });
});
