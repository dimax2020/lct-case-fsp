import { DomainError } from './errors.js';

export const PRACTICE_STATUSES = [
  'INVITED',
  'STARTED',
  'IN_PROGRESS',
  'SUBMITTED',
  'REVIEW',
  'COMPLETED',
  'EXPIRED',
] as const;
export type PracticeStatus = (typeof PRACTICE_STATUSES)[number];

export const PRACTICE_TRANSITIONS: Readonly<Record<PracticeStatus, readonly PracticeStatus[]>> = {
  INVITED: ['STARTED', 'EXPIRED'],
  STARTED: ['IN_PROGRESS', 'EXPIRED'],
  IN_PROGRESS: ['SUBMITTED', 'EXPIRED'],
  SUBMITTED: ['REVIEW'],
  REVIEW: ['IN_PROGRESS', 'COMPLETED'],
  COMPLETED: [],
  EXPIRED: [],
};

export const TERMINAL_STATUSES: readonly PracticeStatus[] = ['COMPLETED', 'EXPIRED'];

export function canTransition(from: PracticeStatus, to: PracticeStatus): boolean {
  return PRACTICE_TRANSITIONS[from].includes(to);
}

export function assertTransition(from: PracticeStatus, to: PracticeStatus): void {
  if (!canTransition(from, to)) {
    throw new DomainError('INVALID_TRANSITION', `transition ${from} -> ${to} is not allowed`, { from, to });
  }
}

export function isTerminal(status: PracticeStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}

/** A practice whose deadline passed and which can still move to EXPIRED. */
export function shouldExpire(status: PracticeStatus, deadline: Date, now: Date): boolean {
  return now.getTime() >= deadline.getTime() && canTransition(status, 'EXPIRED');
}

export interface StartPreconditions {
  status: PracticeStatus;
  consentAcceptedAt: Date | null;
  consentVersion: string | null;
  requiredConsentVersion: string;
  deadline: Date;
  now: Date;
}

export function assertCanStart(p: StartPreconditions): void {
  if (p.now.getTime() >= p.deadline.getTime()) {
    throw new DomainError('EXPIRED', 'practice deadline has passed');
  }
  if (!p.consentAcceptedAt || p.consentVersion !== p.requiredConsentVersion) {
    throw new DomainError('CONSENT_REQUIRED', 'telemetry consent must be accepted before start', {
      requiredConsentVersion: p.requiredConsentVersion,
    });
  }
  assertTransition(p.status, 'STARTED');
}
