import { writeFile } from 'node:fs/promises';
import path from 'node:path';
import { loadConfig } from '@epa/platform';
import { buildPlatform } from './container.js';
import { buildServer } from './server.js';

const config = loadConfig();
const platform = await buildPlatform({ config });
const app = await buildServer(platform);

const existing = await platform.ctx.db.one('SELECT id FROM organisations LIMIT 1');
if (!existing) {
  const orgId = await platform.auth.createOrganisation('Demo Org');
  const employer = await platform.auth.createStaff(orgId, 'employer@demo.local', 'employer');
  const auditor = await platform.auth.createStaff(orgId, 'auditor@demo.local', 'auditor');
  const platformToken = await platform.auth.platformToken();
  const tokenFile = path.join(config.dataDir, 'dev-tokens.json');
  await writeFile(tokenFile, JSON.stringify({ organisationId: orgId, employerToken: employer.token, auditorToken: auditor.token, platformToken, ui: `${config.publicUrl}/employer.html` }, null, 2) + '\n');
}
process.stdout.write(`\nВход: ${config.publicUrl}/employer.html\n  укажите своё имя, пароль не нужен\n\n`);

if (config.embeddedWorker) {
  platform.worker.start(500);
  await platform.scheduleMaintenance();
  setInterval(() => void platform.scheduleMaintenance(), 60_000).unref();
}

await app.listen({ port: config.port, host: process.env.HOST ?? '0.0.0.0' });
platform.ctx.log.info('api listening', { port: config.port, rdeDriver: config.rdeDriver, sandboxDriver: config.sandboxDriver, model: config.ollamaModel });

const shutdown = async () => {
  await app.close();
  await platform.close();
  process.exit(0);
};
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
