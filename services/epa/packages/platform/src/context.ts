import type { Db } from './db.js';
import type { Clock } from './core.js';
import type { AuditLog } from './audit.js';
import type { JobQueue } from './jobs.js';
import type { ObjectStore, ObjectAccessSigner } from './object-store.js';
import type { Logger, Metrics } from './observability.js';
import type { PlatformConfig } from './config.js';

/** Infrastructure handles shared by every service. */
export interface Ctx {
  db: Db;
  clock: Clock;
  audit: AuditLog;
  jobs: JobQueue;
  objects: ObjectStore;
  signer: ObjectAccessSigner;
  log: Logger;
  metrics: Metrics;
  config: PlatformConfig;
}
