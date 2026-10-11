import { spawnSync } from 'node:child_process';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/** Runs the section-14 acceptance suite and records the outcome for Definition of Done. */
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const started = new Date();
const vitest = path.join(root, 'node_modules/.bin/vitest');
const r = spawnSync(vitest, ['run', '--project', 'e2e', 'tests/e2e/acceptance.test.ts'], {
  cwd: root,
  stdio: 'inherit',
  env: process.env,
});
const ended = new Date();
const status = r.status === 0 ? 'passed' : 'failed';
const drivers = process.env.EPA_E2E_DRIVERS ?? 'auto (docker if node:20-alpine is present)';
await writeFile(
  path.join(root, 'docs/runbooks/acceptance-result.md'),
  `# E2E acceptance log

- Status: **${status}** (exit ${r.status ?? 'null'})
- When: ${started.toISOString()} → ${ended.toISOString()}
- Drivers: ${drivers}
- Suite: \`tests/e2e/acceptance.test.ts\` (spec section 14)

${status === 'passed' ? 'All ten acceptance steps completed.' : 'See CI/console output above for the failing step.'}
`,
);
process.exit(r.status ?? 1);
