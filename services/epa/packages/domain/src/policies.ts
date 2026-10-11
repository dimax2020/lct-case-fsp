import { DomainError } from './errors.js';

// ---------- Workspace (RDE) policy ----------

export const WORKSPACE_POLICY_VERSION = 'rde-policy-v1';

export interface WorkspacePolicy {
  version: string;
  cpus: number;
  memoryMb: number;
  diskMb: number;
  pidsLimit: number;
  network: 'none';
  sessionTtlMinutes: number;
  commandTimeoutSec: number;
  maxFileBytes: number;
  readOnlyRootFs: true;
  dropAllCapabilities: true;
  noNewPrivileges: true;
  user: string;
}

export const WORKSPACE_POLICY_LIMITS = {
  cpus: { min: 0.25, max: 4 },
  memoryMb: { min: 128, max: 4096 },
  diskMb: { min: 64, max: 4096 },
  pidsLimit: { min: 16, max: 1024 },
  sessionTtlMinutes: { min: 5, max: 24 * 60 },
  commandTimeoutSec: { min: 1, max: 600 },
  maxFileBytes: { min: 1024, max: 5 * 1024 * 1024 },
} as const;

const DEFAULT_WORKSPACE_POLICY: WorkspacePolicy = {
  version: WORKSPACE_POLICY_VERSION,
  cpus: 1,
  memoryMb: 512,
  diskMb: 4096,
  pidsLimit: 256,
  network: 'none',
  sessionTtlMinutes: 240,
  commandTimeoutSec: 120,
  maxFileBytes: 5 * 1024 * 1024,
  readOnlyRootFs: true,
  dropAllCapabilities: true,
  noNewPrivileges: true,
  user: '1000:1000',
};

export type WorkspacePolicyOverrides = Partial<
  Pick<WorkspacePolicy, 'cpus' | 'memoryMb' | 'diskMb' | 'pidsLimit' | 'sessionTtlMinutes' | 'commandTimeoutSec' | 'maxFileBytes'>
>;

function bounded(name: keyof typeof WORKSPACE_POLICY_LIMITS, value: number): number {
  const { min, max } = WORKSPACE_POLICY_LIMITS[name];
  if (!Number.isFinite(value) || value < min || value > max) {
    throw new DomainError('VALIDATION', `${name} must be within ${min}..${max}`);
  }
  return value;
}

/** Builds an effective policy. Security-relevant flags (network, caps, root fs) cannot be overridden. */
export function buildWorkspacePolicy(overrides: WorkspacePolicyOverrides = {}): WorkspacePolicy {
  const p: WorkspacePolicy = { ...DEFAULT_WORKSPACE_POLICY };
  for (const key of Object.keys(overrides) as (keyof WorkspacePolicyOverrides)[]) {
    const v = overrides[key];
    if (v === undefined) continue;
    if (!(key in WORKSPACE_POLICY_LIMITS)) throw new DomainError('VALIDATION', `policy field ${key} is not overridable`);
    p[key] = bounded(key, v);
  }
  return p;
}

// ---------- Sandbox policy ----------

export const SANDBOX_POLICY_VERSION = 'sandbox-policy-v1';

export interface SandboxPolicy {
  version: string;
  cpus: number;
  memoryMb: number;
  tmpfsMb: number;
  pidsLimit: number;
  timeoutSec: number;
  maxLogBytes: number;
  network: 'none';
}

export const DEFAULT_SANDBOX_POLICY: SandboxPolicy = {
  version: SANDBOX_POLICY_VERSION,
  cpus: 1,
  memoryMb: 256,
  tmpfsMb: 64,
  pidsLimit: 64,
  timeoutSec: 60,
  maxLogBytes: 64 * 1024,
  network: 'none',
};

// ---------- Snapshot policy ----------

export interface SnapshotPolicy {
  /** Minimum seconds between interval snapshots. */
  intervalSec: number;
  /** Bytes changed in a single save that count as a "significant save". */
  significantSaveBytes: number;
  /** A new full checkpoint is written after this many patches in a chain. */
  checkpointEvery: number;
  maxFileBytes: number;
  maxTotalBytes: number;
  maxFiles: number;
}

export const DEFAULT_SNAPSHOT_POLICY: SnapshotPolicy = {
  intervalSec: 120,
  significantSaveBytes: 400,
  checkpointEvery: 10,
  maxFileBytes: 5 * 1024 * 1024,
  maxTotalBytes: 64 * 1024 * 1024,
  maxFiles: 8000,
};

export function buildSnapshotPolicy(overrides: Partial<SnapshotPolicy> = {}): SnapshotPolicy {
  const p = { ...DEFAULT_SNAPSHOT_POLICY, ...overrides };
  if (p.intervalSec < 10) throw new DomainError('VALIDATION', 'snapshot interval must be at least 10s');
  if (p.checkpointEvery < 1 || p.checkpointEvery > 100) throw new DomainError('VALIDATION', 'checkpointEvery must be 1..100');
  if (p.significantSaveBytes < 1) throw new DomainError('VALIDATION', 'significantSaveBytes must be positive');
  return p;
}

// ---------- Telemetry policy ----------

export const TELEMETRY_POLICY = {
  largeInsertionThresholdChars: 800,
  maxBatchEvents: 500,
  maxBatchBytes: 256 * 1024,
  maxCommandLength: 2000,
  maxSafeLogBytes: 16 * 1024,
} as const;

// ---------- Consent ----------

export const CONSENT_VERSION = 'consent-v1';

// ---------- Retention ----------

export interface RetentionPolicy {
  /** Days after COMPLETED/EXPIRED before artifacts are deleted/anonymised. */
  artifactRetentionDays: number;
}

export const DEFAULT_RETENTION_POLICY: RetentionPolicy = { artifactRetentionDays: 90 };

export function retentionDeadline(terminalAt: Date, policy: RetentionPolicy): Date {
  if (policy.artifactRetentionDays < 1 || policy.artifactRetentionDays > 3650) {
    throw new DomainError('VALIDATION', 'artifactRetentionDays must be within 1..3650');
  }
  return new Date(terminalAt.getTime() + policy.artifactRetentionDays * 86_400_000);
}

export type RetentionDecision =
  | { eligible: false; reason: 'not_terminal' | 'retention_active' | 'already_purged' }
  | { eligible: true; deadline: Date };

export function retentionEligibility(input: {
  status: string;
  terminalAt: Date | null;
  purgedAt: Date | null;
  policy: RetentionPolicy;
  now: Date;
}): RetentionDecision {
  if (input.purgedAt) return { eligible: false, reason: 'already_purged' };
  if (!input.terminalAt || (input.status !== 'COMPLETED' && input.status !== 'EXPIRED')) {
    return { eligible: false, reason: 'not_terminal' };
  }
  const deadline = retentionDeadline(input.terminalAt, input.policy);
  if (input.now.getTime() < deadline.getTime()) return { eligible: false, reason: 'retention_active' };
  return { eligible: true, deadline };
}

// ---------- Retry/backoff ----------

export function backoffMs(attempt: number, baseMs = 1000, capMs = 5 * 60_000): number {
  if (attempt < 1) return 0;
  return Math.min(capMs, baseMs * 2 ** (attempt - 1));
}
