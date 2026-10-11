import { mkdir, readFile, rename, rm, writeFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { DomainError } from '@epa/domain';
import { hmac, safeEqual, type Clock } from './core.js';

const KEY_PATTERN = /^[a-z0-9_]+(\/[a-z0-9_.-]+){1,6}$/i;

export interface StoredObject {
  key: string;
  sha256: string;
  bytes: number;
}

export interface ObjectStore {
  put(key: string, data: Buffer): Promise<StoredObject>;
  get(key: string, expectedSha256?: string): Promise<Buffer>;
  delete(key: string): Promise<void>;
  exists(key: string): Promise<boolean>;
}

export function assertObjectKey(key: string): void {
  if (!KEY_PATTERN.test(key) || key.includes('..')) {
    throw new DomainError('VALIDATION', 'invalid object key');
  }
}

/** Write-once filesystem object store. Objects are immutable: overwriting a key fails. */
export class FsObjectStore implements ObjectStore {
  constructor(private readonly root: string) {}

  private abs(key: string): string {
    assertObjectKey(key);
    const p = path.resolve(this.root, key);
    if (!p.startsWith(path.resolve(this.root) + path.sep)) throw new DomainError('VALIDATION', 'object key escapes store');
    return p;
  }

  async put(key: string, data: Buffer): Promise<StoredObject> {
    const p = this.abs(key);
    await mkdir(path.dirname(p), { recursive: true });
    const tmp = `${p}.tmp-${process.pid}-${Date.now()}`;
    await writeFile(tmp, data, { flag: 'wx' });
    try {
      await stat(p);
      await rm(tmp, { force: true });
      throw new DomainError('CONFLICT', 'object already exists (objects are immutable)');
    } catch (e) {
      if (e instanceof DomainError) throw e;
    }
    await rename(tmp, p);
    return { key, sha256: createHash('sha256').update(data).digest('hex'), bytes: data.length };
  }

  async get(key: string, expectedSha256?: string): Promise<Buffer> {
    let data: Buffer;
    try {
      data = await readFile(this.abs(key));
    } catch (e: any) {
      if (e?.code === 'ENOENT') throw new DomainError('GONE', 'object not available');
      throw e;
    }
    if (expectedSha256) {
      const actual = createHash('sha256').update(data).digest('hex');
      if (actual !== expectedSha256) {
        throw new DomainError('INTEGRITY', 'object hash mismatch', { key });
      }
    }
    return data;
  }

  async delete(key: string): Promise<void> {
    await rm(this.abs(key), { force: true });
  }

  async exists(key: string): Promise<boolean> {
    try {
      await stat(this.abs(key));
      return true;
    } catch {
      return false;
    }
  }
}

// ---------- Short-lived signed access ----------

export interface SignedGrant {
  key: string;
  principal: string;
  expiresAt: number;
  contentType: string;
}

export class ObjectAccessSigner {
  constructor(
    private readonly secret: string,
    private readonly clock: Clock,
    private readonly ttlSec = 60,
  ) {}

  sign(input: { key: string; principal: string; contentType?: string }): { token: string; expiresAt: Date } {
    assertObjectKey(input.key);
    const grant: SignedGrant = {
      key: input.key,
      principal: input.principal,
      expiresAt: this.clock.now().getTime() + this.ttlSec * 1000,
      contentType: input.contentType ?? 'text/plain; charset=utf-8',
    };
    const body = Buffer.from(JSON.stringify(grant)).toString('base64url');
    return { token: `${body}.${hmac(this.secret, body)}`, expiresAt: new Date(grant.expiresAt) };
  }

  verify(token: string): SignedGrant {
    const [body, sig] = token.split('.');
    if (!body || !sig || !safeEqual(hmac(this.secret, body), sig)) {
      throw new DomainError('FORBIDDEN', 'invalid signature');
    }
    const grant = JSON.parse(Buffer.from(body, 'base64url').toString('utf8')) as SignedGrant;
    if (this.clock.now().getTime() > grant.expiresAt) throw new DomainError('GONE', 'signed link expired');
    assertObjectKey(grant.key);
    return grant;
  }
}
