import { DomainError } from '@epa/domain';

export type Principal =
  | { kind: 'employer'; id: string; organisationId: string }
  | { kind: 'candidate'; id: string }
  | { kind: 'auditor'; id: string; organisationId: string }
  | { kind: 'agent'; id: string; sessionId: string; practiceId: string; workspaceId: string }
  | { kind: 'platform'; id: 'platform' };

export interface PracticeScope {
  practiceId: string;
  organisationId: string;
  candidateId: string | null;
}

export type Action =
  | 'practice:create'
  | 'practice:read'
  | 'practice:invite'
  | 'practice:review'
  | 'practice:report'
  | 'practice:timeline'
  | 'practice:consent'
  | 'practice:work'
  | 'comment:resolve'
  | 'interview:answer'
  | 'telemetry:ingest'
  | 'artifact:read'
  | 'audit:read'
  | 'report:export'
  | 'retention:purge';

type Rule = (p: Principal, s: PracticeScope) => boolean;

const isOrgEmployer: Rule = (p, s) => p.kind === 'employer' && p.organisationId === s.organisationId;
const isOrgAuditor: Rule = (p, s) => p.kind === 'auditor' && p.organisationId === s.organisationId;
const isOwnCandidate: Rule = (p, s) => p.kind === 'candidate' && s.candidateId !== null && p.id === s.candidateId;
const isPracticeAgent: Rule = (p, s) => p.kind === 'agent' && p.practiceId === s.practiceId;
const isPlatform: Rule = (p) => p.kind === 'platform';
const any = (...rules: Rule[]): Rule => (p, s) => rules.some((r) => r(p, s));

/**
 * Deny-by-default policy table. Every practice-scoped endpoint resolves the practice
 * scope from the database (never from the request body) and checks it here.
 */
const POLICY: Record<Action, Rule> = {
  'practice:create': (p, s) => p.kind === 'employer' && p.organisationId === s.organisationId,
  'practice:read': any(isOrgEmployer, isOrgAuditor, isOwnCandidate, isPlatform),
  'practice:invite': isOrgEmployer,
  'practice:review': isOrgEmployer,
  'practice:report': any(isOrgEmployer, isOrgAuditor),
  'practice:timeline': any(isOrgEmployer, isOrgAuditor, isOwnCandidate),
  'practice:consent': isOwnCandidate,
  'practice:work': isOwnCandidate,
  'comment:resolve': any(isOrgEmployer, isOwnCandidate),
  'interview:answer': isOwnCandidate,
  'telemetry:ingest': isPracticeAgent,
  'artifact:read': any(isOrgEmployer, isOrgAuditor, isOwnCandidate, isPlatform),
  'audit:read': isOrgAuditor,
  'report:export': any(isOrgEmployer, isOrgAuditor),
  'retention:purge': isPlatform,
};

export function can(principal: Principal, action: Action, scope: PracticeScope): boolean {
  return POLICY[action](principal, scope);
}

export function authorize(principal: Principal | null, action: Action, scope: PracticeScope): asserts principal is Principal {
  if (!principal) throw new DomainError('UNAUTHENTICATED', 'authentication required');
  if (!can(principal, action, scope)) throw new DomainError('FORBIDDEN', `not allowed: ${action}`);
}

export function requireKind<K extends Principal['kind']>(
  principal: Principal | null,
  ...kinds: K[]
): Extract<Principal, { kind: K }> {
  if (!principal) throw new DomainError('UNAUTHENTICATED', 'authentication required');
  if (!kinds.includes(principal.kind as K)) throw new DomainError('FORBIDDEN', 'principal kind not allowed');
  return principal as Extract<Principal, { kind: K }>;
}

export function actorOf(p: Principal): { actorType: Principal['kind']; actorId: string } {
  return { actorType: p.kind, actorId: p.id };
}
