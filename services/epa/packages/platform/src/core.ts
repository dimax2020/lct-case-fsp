import { createHash, randomBytes, randomUUID, timingSafeEqual, createHmac } from 'node:crypto';
import { DomainError } from '@epa/domain';

export type IdPrefix =
  | 'org' | 'emp' | 'cand' | 'prc' | 'inv' | 'cns' | 'ws' | 'ses' | 'evt' | 'diag' | 'snap'
  | 'sub' | 'tr' | 'cmt' | 'rvd' | 'rc' | 'ai' | 'q' | 'ans' | 'asm' | 'job' | 'aud';

export function newId(prefix: IdPrefix): string {
  return `${prefix}_${randomUUID().replace(/-/g, '')}`;
}

export function newSecretToken(bytes = 32): string {
  return randomBytes(bytes).toString('base64url');
}

export function hashToken(token: string): string {
  return createHash('sha256').update(token).digest('hex');
}

export function hmac(secret: string, data: string): string {
  return createHmac('sha256', secret).update(data).digest('base64url');
}

export function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  return ab.length === bb.length && timingSafeEqual(ab, bb);
}

// ---------- Clock ----------

export interface Clock {
  now(): Date;
}

export const systemClock: Clock = { now: () => new Date() };

export class FakeClock implements Clock {
  private t: number;
  constructor(start: Date | string = '2026-10-01T09:00:00.000Z') {
    this.t = new Date(start).getTime();
  }
  now(): Date {
    return new Date(this.t);
  }
  advance(ms: number): void {
    this.t += ms;
  }
  set(d: Date | string): void {
    this.t = new Date(d).getTime();
  }
}

// ---------- Rate limiting ----------

export class RateLimiter {
  private buckets = new Map<string, { tokens: number; updated: number }>();
  constructor(
    private readonly capacity: number,
    private readonly refillPerSec: number,
    private readonly clock: Clock = systemClock,
  ) {}

  consume(key: string, cost = 1): void {
    const now = this.clock.now().getTime();
    const b = this.buckets.get(key) ?? { tokens: this.capacity, updated: now };
    b.tokens = Math.min(this.capacity, b.tokens + ((now - b.updated) / 1000) * this.refillPerSec);
    b.updated = now;
    if (b.tokens < cost) {
      this.buckets.set(key, b);
      throw new DomainError('RATE_LIMITED', 'too many requests', { retryAfterSec: Math.ceil((cost - b.tokens) / this.refillPerSec) });
    }
    b.tokens -= cost;
    this.buckets.set(key, b);
    if (this.buckets.size > 50_000) this.buckets.clear();
  }
}
