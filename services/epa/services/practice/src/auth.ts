import { randomBytes, scryptSync, timingSafeEqual } from 'node:crypto';
import type { Principal } from '@epa/authz';
import { DomainError } from '@epa/domain';
import { hashToken, newId, newSecretToken, type Ctx, type Queryable } from '@epa/platform';

const STAFF_TTL_MS = 30 * 86_400_000;
const CANDIDATE_TTL_MS = 30 * 86_400_000;

/** Stores `scrypt$salt$hash`. The password itself is never kept. */
export function hashPassword(password: string): string {
  const salt = randomBytes(16).toString('hex');
  const hash = scryptSync(password, salt, 32).toString('hex');
  return `scrypt$${salt}$${hash}`;
}

export function verifyPassword(password: string, stored: string | null): boolean {
  if (!stored) return false;
  const [kind, salt, hash] = stored.split('$');
  if (kind !== 'scrypt' || !salt || !hash) return false;
  const candidate = scryptSync(password, salt, 32);
  const expected = Buffer.from(hash, 'hex');
  if (candidate.length !== expected.length) return false;
  return timingSafeEqual(candidate, expected);
}

export function assertPassword(password: string): void {
  if (typeof password !== 'string' || password.length < 8 || password.length > 200) {
    throw new DomainError('VALIDATION', 'password must be 8..200 characters');
  }
}

/** The name a person types. Stored as typed; later visits match without case sensitivity. */
export function normalizeName(name: string): string {
  const trimmed = name.trim().replace(/\s+/g, ' ');
  if (trimmed.length < 1 || trimmed.length > 80) throw new DomainError('VALIDATION', 'имя должно быть от 1 до 80 символов');
  if (/[\u0000-\u001f]/.test(trimmed)) throw new DomainError('VALIDATION', 'имя содержит недопустимые символы');
  return trimmed;
}

type TokenKind = 'employer' | 'auditor' | 'candidate' | 'agent' | 'platform';

interface TokenRow {
  token_hash: string;
  principal_kind: TokenKind;
  principal_id: string;
  scope: Record<string, string>;
  expires_at: Date;
  revoked_at: Date | null;
}

/** Bearer tokens are random 256-bit values; only their SHA-256 is stored. */
export class AuthService {
  constructor(private readonly ctx: Ctx) {}

  async issue(
    q: Queryable,
    input: { kind: TokenKind; principalId: string; ttlMs: number; scope?: Record<string, string> },
  ): Promise<{ token: string; expiresAt: Date }> {
    const token = newSecretToken();
    const now = this.ctx.clock.now();
    const expiresAt = new Date(now.getTime() + input.ttlMs);
    await q.query(
      `INSERT INTO auth_tokens (token_hash, principal_kind, principal_id, scope, expires_at, created_at) VALUES ($1,$2,$3,$4,$5,$6)`,
      [hashToken(token), input.kind, input.principalId, JSON.stringify(input.scope ?? {}), expiresAt, now],
    );
    return { token, expiresAt };
  }

  async revokeWhere(q: Queryable, kind: TokenKind, scopeKey: string, scopeValue: string): Promise<void> {
    await q.query(
      `UPDATE auth_tokens SET revoked_at = $1 WHERE principal_kind = $2 AND scope->>$3 = $4 AND revoked_at IS NULL`,
      [this.ctx.clock.now(), kind, scopeKey, scopeValue],
    );
  }

  async authenticate(token: string | undefined): Promise<Principal | null> {
    if (!token || token.length < 20 || token.length > 200) return null;
    const row = await this.ctx.db.one<TokenRow>('SELECT * FROM auth_tokens WHERE token_hash = $1', [hashToken(token)]);
    if (!row || row.revoked_at || new Date(row.expires_at).getTime() <= this.ctx.clock.now().getTime()) return null;
    switch (row.principal_kind) {
      case 'employer':
      case 'auditor': {
        const emp = await this.ctx.db.one<{ organisation_id: string; role: string }>(
          'SELECT organisation_id, role FROM employers WHERE id = $1',
          [row.principal_id],
        );
        if (!emp || emp.role !== row.principal_kind) return null;
        return { kind: row.principal_kind, id: row.principal_id, organisationId: emp.organisation_id };
      }
      case 'candidate':
        return { kind: 'candidate', id: row.principal_id };
      case 'agent':
        return {
          kind: 'agent',
          id: row.principal_id,
          sessionId: row.scope.sessionId,
          practiceId: row.scope.practiceId,
          workspaceId: row.scope.workspaceId,
        };
      case 'platform':
        return { kind: 'platform', id: 'platform' };
      default:
        return null;
    }
  }

  /**
   * Enters as the typed name. The first visit creates the employer or candidate.
   * The token stays in the browser and is not shown.
   */
  async enterByName(name: string, role: 'employer' | 'candidate'): Promise<{ token: string; role: 'employer' | 'candidate'; email: string }> {
    const identity = normalizeName(name);
    if (role === 'employer') {
      const existing = await this.ctx.db.one<{ id: string; identity: string }>(
        `SELECT id, identity FROM employers WHERE role = 'employer' AND lower(identity) = lower($1) ORDER BY created_at LIMIT 1`,
        [identity],
      );
      if (existing) {
        const { token } = await this.issue(this.ctx.db, { kind: 'employer', principalId: existing.id, ttlMs: STAFF_TTL_MS });
        return { token, role: 'employer', email: existing.identity };
      }
      let org = await this.ctx.db.one<{ id: string }>('SELECT id FROM organisations ORDER BY created_at LIMIT 1');
      if (!org) org = { id: await this.createOrganisation('Demo Org') };
      const created = await this.createStaff(org.id, identity, 'employer');
      return { token: created.token, role: 'employer', email: identity };
    }
    const existing = await this.ctx.db.one<{ id: string; identity: string }>(
      `SELECT id, identity FROM candidates WHERE anonymised_at IS NULL AND lower(identity) = lower($1) ORDER BY created_at DESC LIMIT 1`,
      [identity],
    );
    if (existing) {
      const { token } = await this.issue(this.ctx.db, { kind: 'candidate', principalId: existing.id, ttlMs: CANDIDATE_TTL_MS });
      return { token, role: 'candidate', email: existing.identity };
    }
    const id = newId('cand');
    await this.ctx.db.query('INSERT INTO candidates (id, identity, created_at) VALUES ($1,$2,$3)', [id, identity, this.ctx.clock.now()]);
    const { token } = await this.issue(this.ctx.db, { kind: 'candidate', principalId: id, ttlMs: CANDIDATE_TTL_MS });
    return { token, role: 'candidate', email: identity };
  }

  /** Email and password. The returned token is stored by the browser and is not shown to the person. */
  async login(email: string, password: string): Promise<{ token: string; role: 'employer' | 'auditor' | 'candidate'; email: string }> {
    const found = await this.principalForPassword(email, password);
    if (!found) throw new DomainError('UNAUTHENTICATED', 'неверная почта или пароль');
    const ttl = found.principal.kind === 'candidate' ? CANDIDATE_TTL_MS : STAFF_TTL_MS;
    const scope = found.principal.kind === 'candidate' ? {} : undefined;
    const { token } = await this.issue(this.ctx.db, { kind: found.principal.kind, principalId: found.principal.id, ttlMs: ttl, scope });
    return { token, role: found.principal.kind, email: found.email };
  }

  /** Checks email and password without creating a session. Used by git push/fetch. */
  async principalForPassword(
    email: string,
    password: string,
  ): Promise<{ principal: Extract<Principal, { kind: 'employer' | 'auditor' | 'candidate' }>; email: string } | null> {
    const normalized = email.trim().toLowerCase();
    const staff = await this.ctx.db.query<{ id: string; organisation_id: string; role: 'employer' | 'auditor'; password_hash: string | null; identity: string }>(
      'SELECT id, organisation_id, role, password_hash, identity FROM employers WHERE lower(identity) = $1',
      [normalized],
    );
    for (const row of staff) {
      if (!verifyPassword(password, row.password_hash)) continue;
      return { principal: { kind: row.role, id: row.id, organisationId: row.organisation_id }, email: row.identity };
    }
    const people = await this.ctx.db.query<{ id: string; password_hash: string | null; identity: string }>(
      'SELECT id, password_hash, identity FROM candidates WHERE lower(identity) = $1 AND anonymised_at IS NULL',
      [normalized],
    );
    for (const row of people) {
      if (!verifyPassword(password, row.password_hash)) continue;
      return { principal: { kind: 'candidate', id: row.id }, email: row.identity };
    }
    return null;
  }

  /** Login and password the candidate types in the VS Code extension. */
  async setExtensionCredentials(candidateId: string, username: string, password: string): Promise<string> {
    const login = username.trim();
    assertPassword(password);
    if (!/^[A-Za-z0-9._-]{3,40}$/.test(login)) throw new DomainError('VALIDATION', 'логин: латиница, цифры, точка, _ или -');
    const taken = await this.ctx.db.one<{ id: string }>('SELECT id FROM candidates WHERE lower(username) = lower($1) AND id <> $2', [login, candidateId]);
    if (taken) throw new DomainError('CONFLICT', 'этот логин уже занят');
    await this.ctx.db.query('UPDATE candidates SET username = $2, password_hash = $3 WHERE id = $1', [candidateId, login, hashPassword(password)]);
    return login;
  }

  async candidateForExtension(username: string, password: string): Promise<{ id: string; username: string }> {
    const row = await this.ctx.db.one<{ id: string; username: string; password_hash: string | null }>(
      'SELECT id, username, password_hash FROM candidates WHERE lower(username) = lower($1) AND anonymised_at IS NULL',
      [username.trim()],
    );
    if (!row?.username || !verifyPassword(password, row.password_hash)) throw new DomainError('UNAUTHENTICATED', 'неверный логин или пароль');
    return { id: row.id, username: row.username };
  }

  async setPassword(kind: 'employer' | 'candidate', id: string, password: string): Promise<void> {
    assertPassword(password);
    const table = kind === 'employer' ? 'employers' : 'candidates';
    await this.ctx.db.query(`UPDATE ${table} SET password_hash = $2 WHERE id = $1`, [id, hashPassword(password)]);
  }

  /** Sets a dev password only when the account has none yet. Returns true if it wrote one. */
  async ensurePassword(email: string, password: string): Promise<boolean> {
    assertPassword(password);
    const row = await this.ctx.db.one<{ id: string; password_hash: string | null }>(
      'SELECT id, password_hash FROM employers WHERE lower(identity) = $1',
      [email.trim().toLowerCase()],
    );
    if (!row || row.password_hash) return false;
    await this.setPassword('employer', row.id, password);
    return true;
  }

  async me(principal: Principal | null): Promise<{ email: string; role: Principal['kind']; username?: string | null }> {
    if (!principal) throw new DomainError('UNAUTHENTICATED', 'authentication required');
    if (principal.kind === 'employer' || principal.kind === 'auditor') {
      const row = await this.ctx.db.one<{ identity: string }>('SELECT identity FROM employers WHERE id = $1', [principal.id]);
      if (!row) throw new DomainError('UNAUTHENTICATED', 'authentication required');
      return { email: row.identity, role: principal.kind };
    }
    if (principal.kind === 'candidate') {
      const row = await this.ctx.db.one<{ identity: string; username: string | null }>('SELECT identity, username FROM candidates WHERE id = $1', [principal.id]);
      if (!row) throw new DomainError('UNAUTHENTICATED', 'authentication required');
      return { email: row.identity, role: 'candidate', username: row.username };
    }
    throw new DomainError('FORBIDDEN', 'not a person account');
  }

  // ---------- Organisation bootstrap (admin CLI / tests) ----------

  async createOrganisation(name: string, retentionDays = this.ctx.config.defaultRetentionDays): Promise<string> {
    const id = newId('org');
    await this.ctx.db.query('INSERT INTO organisations (id, name, retention_days, created_at) VALUES ($1,$2,$3,$4)', [
      id,
      name,
      retentionDays,
      this.ctx.clock.now(),
    ]);
    return id;
  }

  async createStaff(
    organisationId: string,
    identity: string,
    role: 'employer' | 'auditor' = 'employer',
    ttlMs = 30 * 86_400_000,
  ): Promise<{ id: string; token: string }> {
    return this.ctx.db.tx(async (tx) => {
      const id = newId('emp');
      await tx.query('INSERT INTO employers (id, organisation_id, identity, role, created_at) VALUES ($1,$2,$3,$4,$5)', [
        id,
        organisationId,
        identity,
        role,
        this.ctx.clock.now(),
      ]);
      const { token } = await this.issue(tx, { kind: role, principalId: id, ttlMs });
      await this.ctx.audit.append(tx, {
        actorKind: 'platform',
        actorId: 'platform',
        action: 'staff.created',
        entityType: 'employer',
        entityId: id,
        organisationId,
        detail: { role },
      });
      return { id, token };
    });
  }

  async platformToken(ttlMs = 86_400_000): Promise<string> {
    return (await this.issue(this.ctx.db, { kind: 'platform', principalId: 'platform', ttlMs })).token;
  }
}

export function requirePrincipal(p: Principal | null): Principal {
  if (!p) throw new DomainError('UNAUTHENTICATED', 'authentication required');
  return p;
}
