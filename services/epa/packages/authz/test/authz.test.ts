import { describe, expect, it } from 'vitest';
import { authorize, can, type Principal, type PracticeScope } from '@epa/authz';

const scope: PracticeScope = { practiceId: 'prc_1', organisationId: 'org_a', candidateId: 'cand_1' };
const employerA: Principal = { kind: 'employer', id: 'emp_a', organisationId: 'org_a' };
const employerB: Principal = { kind: 'employer', id: 'emp_b', organisationId: 'org_b' };
const auditorA: Principal = { kind: 'auditor', id: 'aud_a', organisationId: 'org_a' };
const cand1: Principal = { kind: 'candidate', id: 'cand_1' };
const cand2: Principal = { kind: 'candidate', id: 'cand_2' };
const agent: Principal = { kind: 'agent', id: 'agent:ses_1', sessionId: 'ses_1', practiceId: 'prc_1', workspaceId: 'ws_1' };
const otherAgent: Principal = { kind: 'agent', id: 'agent:ses_2', sessionId: 'ses_2', practiceId: 'prc_2', workspaceId: 'ws_2' };

describe('RBAC and practice-scoped authorisation', () => {
  it('employer sees only own organisation', () => {
    expect(can(employerA, 'practice:review', scope)).toBe(true);
    expect(can(employerB, 'practice:review', scope)).toBe(false);
    expect(can(employerB, 'practice:read', scope)).toBe(false);
    expect(can(employerB, 'practice:report', scope)).toBe(false);
  });

  it('candidate sees only own practices and cannot act as employer', () => {
    expect(can(cand1, 'practice:work', scope)).toBe(true);
    expect(can(cand2, 'practice:work', scope)).toBe(false);
    expect(can(cand1, 'practice:review', scope)).toBe(false);
    expect(can(cand1, 'practice:report', scope)).toBe(false);
    expect(can(cand1, 'audit:read', scope)).toBe(false);
  });

  it('auditor is read-only', () => {
    expect(can(auditorA, 'audit:read', scope)).toBe(true);
    expect(can(auditorA, 'practice:report', scope)).toBe(true);
    expect(can(auditorA, 'practice:review', scope)).toBe(false);
    expect(can(auditorA, 'practice:work', scope)).toBe(false);
  });

  it('agents may only ingest for their own practice', () => {
    expect(can(agent, 'telemetry:ingest', scope)).toBe(true);
    expect(can(otherAgent, 'telemetry:ingest', scope)).toBe(false);
    expect(can(agent, 'practice:read', scope)).toBe(false);
  });

  it('retention purge is platform-only; authorize throws typed errors', () => {
    expect(can(employerA, 'retention:purge', scope)).toBe(false);
    expect(() => authorize(null, 'practice:read', scope)).toThrowError(/authentication/);
    expect(() => authorize(employerB, 'practice:read', scope)).toThrowError(/not allowed/);
  });
});
