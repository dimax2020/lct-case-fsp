import { loadConfig } from '@epa/platform';
import { buildPlatform } from '@epa/api';

/** Standalone worker process (use with a shared Postgres DATABASE_URL and EPA_EMBEDDED_WORKER=false on the API). */
const config = loadConfig();
if (!config.databaseUrl.startsWith('postgres')) {
  throw new Error('a standalone worker needs a shared Postgres DATABASE_URL; PGlite is single-process (use the embedded worker instead)');
}
const platform = await buildPlatform({ config });
platform.worker.start(500);
await platform.scheduleMaintenance();
setInterval(() => void platform.scheduleMaintenance(), 60_000);
platform.ctx.log.info('worker started');

const shutdown = async () => {
  await platform.close();
  process.exit(0);
};
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
