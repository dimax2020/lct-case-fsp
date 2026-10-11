import { describe, expect, it } from 'vitest';
import {
  CONSENT_VERSION,
  DIMENSIONS,
  PRACTICE_STATUSES,
  PRACTICE_TRANSITIONS,
  aggregate,
  assertCanStart,
  assertCommentRange,
  assertCommentTransition,
  assertTransition,
  assertValidDimensionScore,
  assertValidRequirementChange,
  backoffMs,
  buildSnapshotPolicy,
  buildWorkspacePolicy,
  canTransition,
  mapSandboxOutcome,
  normalizeWorkspacePath,
  renderSafeMarkdown,
  resolveInsideRoot,
  retentionEligibility,
  shouldExpire,
  type DimensionScore,
} from '@epa/domain';

const ALLOWED: [string, string][] = [
  ['INVITED', 'STARTED'], ['INVITED', 'EXPIRED'],
  ['STARTED', 'IN_PROGRESS'], ['STARTED', 'EXPIRED'],
  ['IN_PROGRESS', 'SUBMITTED'], ['IN_PROGRESS', 'EXPIRED'],
  ['SUBMITTED', 'REVIEW'],
  ['REVIEW', 'IN_PROGRESS'], ['REVIEW', 'COMPLETED'],
];

describe('practice state machine', () => {
  it('matches the specification table exactly for every pair of statuses', () => {
    for (const from of PRACTICE_STATUSES) {
      for (const to of PRACTICE_STATUSES) {
        const expected = ALLOWED.some(([f, t]) => f === from && t === to);
        expect(canTransition(from, to), `${from} -> ${to}`).toBe(expected);
        if (expected) expect(() => assertTransition(from, to)).not.toThrow();
        else expect(() => assertTransition(from, to)).toThrowError(/not allowed/);
      }
    }
  });

  it('terminal statuses have no outgoing transitions', () => {
    expect(PRACTICE_TRANSITIONS.COMPLETED).toEqual([]);
    expect(PRACTICE_TRANSITIONS.EXPIRED).toEqual([]);
  });

  it('deadline moves only expirable statuses to EXPIRED', () => {
    const deadline = new Date('2026-01-01T00:00:00Z');
    const after = new Date('2026-01-01T00:00:00Z');
    const before = new Date('2025-12-31T23:59:59Z');
    for (const s of ['INVITED', 'STARTED', 'IN_PROGRESS'] as const) {
      expect(shouldExpire(s, deadline, after)).toBe(true);
      expect(shouldExpire(s, deadline, before)).toBe(false);
    }
    for (const s of ['SUBMITTED', 'REVIEW', 'COMPLETED', 'EXPIRED'] as const) expect(shouldExpire(s, deadline, after)).toBe(false);
  });

  it('consent is mandatory before STARTED', () => {
    const base = { status: 'INVITED' as const, requiredConsentVersion: CONSENT_VERSION, deadline: new Date(Date.now() + 1e6), now: new Date() };
    expect(() => assertCanStart({ ...base, consentAcceptedAt: null, consentVersion: null })).toThrowError(/consent/);
    expect(() => assertCanStart({ ...base, consentAcceptedAt: new Date(), consentVersion: 'consent-v0' })).toThrowError(/consent/);
    expect(() => assertCanStart({ ...base, consentAcceptedAt: new Date(), consentVersion: CONSENT_VERSION })).not.toThrow();
    expect(() => assertCanStart({ ...base, deadline: new Date(0), consentAcceptedAt: new Date(), consentVersion: CONSENT_VERSION })).toThrowError(/deadline/);
  });
});

describe('rubric aggregation', () => {
  const full = (score: number): DimensionScore[] => DIMENSIONS.map((dimension) => ({ dimension, score, rationale: 'x', evidence: [{ kind: 'submission', id: 'sub_1' }], aiDerived: false }));

  it('is deterministic and within 0..100', () => {
    const scores = full(70).map((d, i) => ({ ...d, score: (i * 13) % 101 }));
    const a = aggregate(scores);
    const b = aggregate(structuredClone(scores));
    expect(a).toEqual(b);
    expect(a.overall).toBeGreaterThanOrEqual(0);
    expect(a.overall).toBeLessThanOrEqual(100);
    expect(a.coverage).toBe(1);
  });

  it('uses the documented weighted mean and excludes missing dimensions', () => {
    expect(aggregate(full(80)).overall).toBe(80);
    const partial = full(100).map((d) => (d.dimension === 'adaptability' ? { ...d, score: null, rationale: '', evidence: [] } : d));
    const r = aggregate(partial);
    expect(r.overall).toBe(100);
    expect(r.missing).toEqual(['adaptability']);
    expect(r.coverage).toBe(0.9);
    expect(aggregate([]).overall).toBeNull();
  });

  it('rejects out-of-range scores, unknown rubric versions and rationale without evidence', () => {
    expect(() => assertValidDimensionScore({ dimension: 'security', score: 101, rationale: '', evidence: [], aiDerived: false })).toThrow();
    expect(() => assertValidDimensionScore({ dimension: 'security', score: -1, rationale: '', evidence: [], aiDerived: false })).toThrow();
    expect(() => assertValidDimensionScore({ dimension: 'security', score: 50, rationale: 'because', evidence: [], aiDerived: false })).toThrowError(/evidence/);
    expect(() => aggregate(full(50), 'rubric-v0')).toThrowError(/rubric/);
  });
});

describe('policies', () => {
  it('workspace policy applies limits and never allows network or privilege overrides', () => {
    const p = buildWorkspacePolicy({ cpus: 2, memoryMb: 1024, sessionTtlMinutes: 60 });
    expect(p).toMatchObject({ cpus: 2, memoryMb: 1024, network: 'none', readOnlyRootFs: true, dropAllCapabilities: true, noNewPrivileges: true, sessionTtlMinutes: 60 });
    expect(() => buildWorkspacePolicy({ cpus: 64 })).toThrow();
    expect(() => buildWorkspacePolicy({ memoryMb: 1 })).toThrow();
    expect(() => buildWorkspacePolicy({ network: 'bridge' } as any)).toThrowError(/not overridable/);
  });

  it('snapshot policy forbids per-keystroke snapshots', () => {
    expect(() => buildSnapshotPolicy({ intervalSec: 1 })).toThrow();
    expect(buildSnapshotPolicy({}).checkpointEvery).toBe(10);
  });

  it('retention eligibility', () => {
    const policy = { artifactRetentionDays: 30 };
    const terminalAt = new Date('2026-01-01T00:00:00Z');
    expect(retentionEligibility({ status: 'REVIEW', terminalAt, purgedAt: null, policy, now: new Date('2027-01-01') })).toEqual({ eligible: false, reason: 'not_terminal' });
    expect(retentionEligibility({ status: 'COMPLETED', terminalAt, purgedAt: null, policy, now: new Date('2026-01-15') })).toEqual({ eligible: false, reason: 'retention_active' });
    expect(retentionEligibility({ status: 'EXPIRED', terminalAt, purgedAt: null, policy, now: new Date('2026-02-01') }).eligible).toBe(true);
    expect(retentionEligibility({ status: 'EXPIRED', terminalAt, purgedAt: new Date(), policy, now: new Date('2026-02-01') })).toEqual({ eligible: false, reason: 'already_purged' });
  });

  it('backoff grows exponentially and is capped', () => {
    expect([1, 2, 3, 4].map((a) => backoffMs(a, 100, 1000))).toEqual([100, 200, 400, 800]);
    expect(backoffMs(20, 100, 1000)).toBe(1000);
  });
});

describe('workspace paths', () => {
  it('normalises safe relative paths', () => {
    expect(normalizeWorkspacePath('src/./auth//x.js')).toBe('src/auth/x.js');
  });
  it.each(['../etc/passwd', 'src/../../x', '/etc/passwd', '~/x', 'a\\b', 'a\u0000b', '.git/config', 'src/.git/hooks/pre-commit', 'C:x', ''])('rejects %j', (p) => {
    expect(() => normalizeWorkspacePath(p)).toThrow();
  });
  it('resolveInsideRoot keeps paths under the root', () => {
    expect(resolveInsideRoot('/tmp/ws', 'a/b.js')).toBe('/tmp/ws/a/b.js');
    expect(() => resolveInsideRoot('/tmp/ws', '../x')).toThrow();
  });
});

describe('review, requirement change and sandbox outcome rules', () => {
  it('comments go OPEN → RESOLVED only', () => {
    expect(() => assertCommentTransition('OPEN', 'RESOLVED')).not.toThrow();
    expect(() => assertCommentTransition('RESOLVED', 'OPEN')).toThrow();
    expect(() => assertCommentTransition('RESOLVED', 'RESOLVED')).toThrow();
  });
  it('comment range must belong to the file', () => {
    expect(() => assertCommentRange({ lineStart: 1, lineEnd: 3, fileLineCount: 3 })).not.toThrow();
    expect(() => assertCommentRange({ lineStart: 3, lineEnd: 2, fileLineCount: 10 })).toThrow();
    expect(() => assertCommentRange({ lineStart: 1, lineEnd: 11, fileLineCount: 10 })).toThrow();
    expect(() => assertCommentRange({ lineStart: 0, lineEnd: 1, fileLineCount: 10 })).toThrow();
  });
  it('requirement change needs text, reason, unique criteria and a future due date', () => {
    const now = new Date('2026-01-01');
    const ok = { text: 'Add sliding expiration', reason: 'product', acceptanceCriteria: ['a', 'b'], dueAt: new Date('2026-01-02') };
    expect(() => assertValidRequirementChange(ok, now)).not.toThrow();
    expect(() => assertValidRequirementChange({ ...ok, acceptanceCriteria: [] }, now)).toThrow();
    expect(() => assertValidRequirementChange({ ...ok, acceptanceCriteria: ['a', 'a'] }, now)).toThrow();
    expect(() => assertValidRequirementChange({ ...ok, dueAt: new Date('2025-12-31') }, now)).toThrow();
    expect(() => assertValidRequirementChange({ ...ok, text: 'short' }, now)).toThrow();
  });
  it('a sandbox run is never PASSED without exit 0 and parsed passing results', () => {
    expect(mapSandboxOutcome({ timedOut: false, infraError: false, exitCode: 0, parsed: { passed: 3, failed: 0 } })).toBe('PASSED');
    expect(mapSandboxOutcome({ timedOut: false, infraError: false, exitCode: 0, parsed: null })).toBe('UNKNOWN');
    expect(mapSandboxOutcome({ timedOut: false, infraError: false, exitCode: 0, parsed: { passed: 0, failed: 0 } })).toBe('FAILED');
    expect(mapSandboxOutcome({ timedOut: false, infraError: false, exitCode: 1, parsed: { passed: 2, failed: 1 } })).toBe('FAILED');
    expect(mapSandboxOutcome({ timedOut: true, infraError: false, exitCode: null, parsed: null })).toBe('TIMED_OUT');
    expect(mapSandboxOutcome({ timedOut: false, infraError: true, exitCode: 0, parsed: { passed: 3, failed: 0 } })).toBe('UNKNOWN');
  });
});

describe('safe markdown', () => {
  it('escapes HTML and only allows http(s) links', () => {
    const html = renderSafeMarkdown('<img src=x onerror=alert(1)> **b** `c` [x](javascript:alert(1)) [y](https://e.com)');
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
    expect(html).toContain('<strong>b</strong>');
    expect(html).toContain('<code>c</code>');
    expect(html).not.toContain('href="javascript');
    expect(html).toContain('href="https://e.com"');
  });
});
