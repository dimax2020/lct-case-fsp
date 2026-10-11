import { describe, expect, it } from 'vitest';
import { DEFAULT_SANDBOX_POLICY, assertTestRunTransition } from '@epa/domain';
import { dockerSandboxArgs } from '@epa/sandbox';

describe('sandbox job', () => {
  it('runs with no network, read-only source, resource limits and a kill timeout', () => {
    const args = dockerSandboxArgs({ runId: 'tr_1', sourceDir: '/data/sandbox-work/tr_1', argv: ['node', '--test'], policy: DEFAULT_SANDBOX_POLICY }, 'node:20-alpine', 'epa-sbx-1');
    const j = args.join(' ');
    expect(j).toContain('--rm');
    expect(j).toContain('--network none');
    expect(j).toContain('--read-only');
    expect(j).toContain('--pids-limit 64');
    expect(j).toContain('--memory 256m');
    expect(j).toContain('--cap-drop ALL');
    expect(j).toContain('type=bind,source=/data/sandbox-work/tr_1,target=/src,readonly');
    expect(j).toContain('timeout -s KILL');
    expect(args).toContain(String(DEFAULT_SANDBOX_POLICY.timeoutSec));
    expect(j).not.toMatch(/--env [A-Z_]*(SECRET|TOKEN|DATABASE)/);
  });

  it('rejects shell-injection in the configured test command', () => {
    expect(() => dockerSandboxArgs({ runId: 'tr', sourceDir: '/x', argv: ['node', '--test;curl evil'], policy: DEFAULT_SANDBOX_POLICY }, 'img', 'n')).toThrow();
  });

  it('job state machine: QUEUED → RUNNING → terminal; terminal is final', () => {
    expect(() => assertTestRunTransition('QUEUED', 'RUNNING')).not.toThrow();
    expect(() => assertTestRunTransition('RUNNING', 'PASSED')).not.toThrow();
    expect(() => assertTestRunTransition('RUNNING', 'TIMED_OUT')).not.toThrow();
    expect(() => assertTestRunTransition('PASSED', 'FAILED')).toThrow();
    expect(() => assertTestRunTransition('QUEUED', 'PASSED')).toThrow();
  });
});
