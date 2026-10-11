import { closeSync, existsSync, openSync, readFileSync, unlinkSync, writeSync } from 'node:fs';
import { readdir, readFile, rename, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

export interface Queryable {
  query<T = Record<string, any>>(sql: string, params?: unknown[]): Promise<T[]>;
  one<T = Record<string, any>>(sql: string, params?: unknown[]): Promise<T | null>;
}

export interface Db extends Queryable {
  /** Runs fn in a transaction. Nested calls reuse the outer transaction. */
  tx<T>(fn: (tx: Queryable) => Promise<T>): Promise<T>;
  /** Executes a multi-statement script without parameters (migrations only). */
  exec(script: string): Promise<void>;
  close(): Promise<void>;
  readonly dialect: 'pglite' | 'postgres';
}

type RawQuery = (sql: string, params?: unknown[]) => Promise<{ rows: any[] }>;

function makeQueryable(raw: RawQuery): Queryable {
  return {
    async query(sql, params = []) {
      return (await raw(sql, params)).rows;
    },
    async one(sql, params = []) {
      return (await raw(sql, params)).rows[0] ?? null;
    },
  };
}

function pidAlive(pid: number): boolean {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/** Exclusive lock next to the PGlite directory so a second seed/dev fails with a clear error. */
function acquireDirLock(dataDir: string): () => void {
  const lockPath = `${dataDir}.lock`;
  const create = () => {
    const fd = openSync(lockPath, 'wx');
    writeSync(fd, String(process.pid));
    return () => {
      try {
        closeSync(fd);
      } catch {
        /* already closed */
      }
      try {
        unlinkSync(lockPath);
      } catch {
        /* already removed */
      }
    };
  };
  try {
    return create();
  } catch (e: any) {
    if (e?.code !== 'EEXIST') throw e;
    let other = 0;
    try {
      other = Number(readFileSync(lockPath, 'utf8').trim());
    } catch {
      other = 0;
    }
    if (other && pidAlive(other) && other !== process.pid) {
      throw new Error(`PGlite уже открыт процессом ${other}. Остановите его: kill ${other}`);
    }
    try {
      unlinkSync(lockPath);
    } catch {
      /* raced */
    }
    return create();
  }
}

async function openPglite(dataDir?: string) {
  const { PGlite } = await import('@electric-sql/pglite');
  const pg = dataDir ? new PGlite(dataDir) : new PGlite();
  await pg.waitReady;
  return pg;
}

export async function createPgliteDb(dataDir?: string): Promise<Db> {
  const release = dataDir ? acquireDirLock(dataDir) : () => undefined;
  let pg;
  try {
    try {
      pg = await openPglite(dataDir);
    } catch (first) {
      if (!dataDir) throw first;
      const broken = `${dataDir}.broken-${Date.now()}`;
      if (existsSync(dataDir)) {
        try {
          await rename(dataDir, broken);
        } catch {
          await rm(dataDir, { recursive: true, force: true });
        }
      }
      process.stderr.write(`PGlite data was unreadable; started a fresh database (old files in ${broken})\n`);
      pg = await openPglite(dataDir);
    }
  } catch (e) {
    release();
    throw new Error(
      `PGlite не открыл базу (${dataDir ?? 'memory'}). Остановите другой seed/dev или удалите каталог базы.`,
      { cause: e },
    );
  }
  const root = makeQueryable((sql, params) => pg.query(sql, params as any[]));
  return {
    dialect: 'pglite',
    ...root,
    async tx(fn) {
      return pg.transaction(async (t) => fn(makeQueryable((sql, params) => t.query(sql, params as any[]))));
    },
    async exec(script) {
      await pg.exec(script);
    },
    async close() {
      try {
        await pg.close();
      } finally {
        release();
      }
    },
  };
}

export async function createPostgresDb(connectionString: string): Promise<Db> {
  const { default: pg } = await import('pg');
  const pool = new pg.Pool({ connectionString, max: 10 });
  const root = makeQueryable((sql, params) => pool.query(sql, params as any[]));
  return {
    dialect: 'postgres',
    ...root,
    async tx(fn) {
      const client = await pool.connect();
      try {
        await client.query('BEGIN');
        const result = await fn(makeQueryable((sql, params) => client.query(sql, params as any[])));
        await client.query('COMMIT');
        return result;
      } catch (e) {
        await client.query('ROLLBACK').catch(() => undefined);
        throw e;
      } finally {
        client.release();
      }
    },
    async exec(script) {
      await pool.query(script);
    },
    async close() {
      await pool.end();
    },
  };
}

export async function createDb(url: string): Promise<Db> {
  if (url.startsWith('postgres://') || url.startsWith('postgresql://')) return createPostgresDb(url);
  if (url === 'memory://' || url === '') return createPgliteDb();
  if (url.startsWith('pglite://')) return createPgliteDb(url.slice('pglite://'.length));
  throw new Error(`unsupported DATABASE_URL scheme: ${url.split(':')[0]}`);
}

const MIGRATIONS_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../migrations');

export async function migrate(db: Db): Promise<string[]> {
  await db.query(`CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())`);
  const applied = new Set((await db.query<{ name: string }>('SELECT name FROM schema_migrations')).map((r) => r.name));
  const files = (await readdir(MIGRATIONS_DIR)).filter((f) => f.endsWith('.sql')).sort();
  const newlyApplied: string[] = [];
  for (const file of files) {
    if (applied.has(file)) continue;
    if (!/^[0-9a-z_]+\.sql$/.test(file)) throw new Error(`invalid migration file name ${file}`);
    const sql = await readFile(path.join(MIGRATIONS_DIR, file), 'utf8');
    await db.exec(`BEGIN;\n${sql}\n;INSERT INTO schema_migrations (name) VALUES ('${file}');\nCOMMIT;`);
    newlyApplied.push(file);
  }
  return newlyApplied;
}
