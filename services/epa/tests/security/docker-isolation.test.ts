import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { DEFAULT_SANDBOX_POLICY } from '@epa/domain';
import { call, createTestPlatform, dockerAvailable, runSandboxFixture, startPractice, type TestPlatform } from '@epa/test-fixtures';

const HOST_SECRET = 'host-secret-value';

/** Runs inside the RDE as candidate code would (written via the IDE, executed via the terminal). */
const PROBE = `
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
const leak = (w) => console.log('LEAK:' + w);
const tryConnect = (host, port) => new Promise((resolve) => {
  const s = net.connect({ host, port, timeout: 1500 }, () => { s.destroy(); resolve(true); });
  s.on('error', () => resolve(false));
  s.on('timeout', () => { s.destroy(); resolve(false); });
});
(async () => {
  const ifaces = Object.entries(os.networkInterfaces()).filter(([n]) => n !== 'lo');
  if (ifaces.length) leak('net:interfaces:' + ifaces.map(([n]) => n).join(','));
  for (const [h, p] of [['1.1.1.1', 443], ['169.254.169.254', 80], ['host.docker.internal', 22], ['172.17.0.1', 2375], [process.argv[2] || 'none', 3000]]) {
    if (await tryConnect(h, p)) leak('net:' + h + ':' + p);
  }
  for (const p of ['/usr/sbin/sshd', '/usr/bin/ssh', '/var/run/docker.sock', '/run/docker.sock']) if (fs.existsSync(p)) leak('bin:' + p);
  const mounts = fs.readFileSync('/proc/mounts', 'utf8').split('\\n').filter(Boolean).map((l) => l.split(' ')[1]);
  const allowed = new Set(['/', '/workspace', '/tmp', '/proc', '/dev', '/dev/pts', '/dev/mqueue', '/dev/shm', '/sys', '/sys/fs/cgroup', '/etc/hosts', '/etc/hostname', '/etc/resolv.conf', '/dev/console']);
  for (const m of mounts) if (!allowed.has(m) && !m.startsWith('/proc/') && !m.startsWith('/sys/') && !m.startsWith('/dev/')) leak('mount:' + m);
  for (const [k, v] of Object.entries(process.env)) if (/SECRET|TOKEN|PASSWORD|DATABASE_URL|EPA_/i.test(k) || String(v).includes('${HOST_SECRET}')) leak('env:' + k);
  if (process.getuid() === 0) leak('priv:root');
  try { fs.writeFileSync('/etc/evil', 'x'); leak('priv:rootfs-writable'); } catch {}
  try { fs.readFileSync('/proc/1/root/etc/shadow'); leak('fs:shadow'); } catch {}
  console.log('PROBE:DONE');
})();
`;

describe.skipIf(!dockerAvailable())('security: docker isolation (RDE + sandbox)', () => {
  let t: TestPlatform;
  let a: Awaited<ReturnType<typeof startPractice>>;
  let b: Awaited<ReturnType<typeof startPractice>>;
  const prevEnv = process.env.EPA_HOST_SECRET;

  beforeAll(async () => {
    process.env.EPA_HOST_SECRET = HOST_SECRET;
    t = await createTestPlatform({ drivers: 'docker', overrides: { sandboxPolicy: { ...DEFAULT_SANDBOX_POLICY, timeoutSec: 6 } } });
    a = await startPractice(t);
    b = await startPractice(t);
  }, 120_000);
  afterAll(async () => {
    if (prevEnv === undefined) delete process.env.EPA_HOST_SECRET;
    else process.env.EPA_HOST_SECRET = prevEnv;
    await t?.close();
  });

  it('RDE container: no SSH, no published ports, not privileged, only the workspace is mounted', async () => {
    const host = await (t.platform.rdeDriver as any).inspectHostConfig(`epa-${a.workspaceId.replace('_', '-')}`);
    expect(host.NetworkMode).toBe('none');
    expect(host.Privileged).toBe(false);
    expect(host.ReadonlyRootfs).toBe(true);
    expect(host.CapDrop).toContain('ALL');
    expect(host.SecurityOpt).toContain('no-new-privileges');
    expect(host.PortBindings ?? {}).toEqual({});
    expect(host.PidsLimit).toBeGreaterThan(0);
    expect(host.Memory).toBeGreaterThan(0);
    expect(host.NanoCpus).toBeGreaterThan(0);
    const binds = (host.Mounts ?? []).map((m: any) => m.Target);
    expect(binds).toEqual(['/workspace']);
  });

  it('candidate code inside the RDE cannot reach the network, metadata, host, docker or the other workspace', async () => {
    await call(t.app, 'PUT', `/v1/workspaces/${a.workspaceId}/file`, a.candidateToken, { path: 'probe.js', content: PROBE });
    const r = await call(t.app, 'POST', `/v1/workspaces/${a.workspaceId}/commands`, a.candidateToken, { command: `node probe.js epa-${b.workspaceId.replace('_', '-')}` });
    expect(r.status).toBe(200);
    expect(r.body.output).toContain('PROBE:DONE');
    expect(r.body.output).not.toContain('LEAK:');
  }, 60_000);

  it('sandbox escape attempts (env, network, metadata, host fs, docker socket, privileges) all fail', async () => {
    const run = await runSandboxFixture(t, a.practiceId, 'escape-attempts');
    const log = (await t.platform.ctx.objects.get(run.log_object_key!)).toString();
    expect(log).not.toContain('LEAK:');
    expect(run.status).toBe('PASSED');
  }, 120_000);

  it('fork bomb is contained by the PID limit', async () => {
    const run = await runSandboxFixture(t, a.practiceId, 'fork-bomb');
    const log = (await t.platform.ctx.objects.get(run.log_object_key!)).toString();
    const m = /SPAWNED:(\d+) FAILED:(\d+)/.exec(log);
    if (m) expect(Number(m[2])).toBeGreaterThan(0);
    else expect(['FAILED', 'TIMED_OUT']).toContain(run.status);
    const health = await call(t.app, 'GET', '/healthz');
    expect(health.status).toBe(200);
  }, 120_000);

  it('endless loop is killed at the time limit', async () => {
    const run = await runSandboxFixture(t, a.practiceId, 'endless-loop');
    expect(run.status).toBe('TIMED_OUT');
    expect(run.summary!.reason).toMatch(/time limit/);
  }, 120_000);

  it('memory hog is stopped by the memory limit and never reported as passed', async () => {
    const run = await runSandboxFixture(t, a.practiceId, 'memory-hog');
    expect(['FAILED', 'TIMED_OUT', 'UNKNOWN']).toContain(run.status);
  }, 120_000);
});
