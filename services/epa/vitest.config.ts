import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';
import tsconfig from './tsconfig.json' with { type: 'json' };

const root = fileURLToPath(new URL('.', import.meta.url));
const alias = Object.fromEntries(
  Object.entries(tsconfig.compilerOptions.paths).map(([name, [target]]) => [name, root + target]),
);

const unitInclude = ['packages/*/test/**/*.test.ts', 'services/*/test/**/*.test.ts', 'apps/*/test/**/*.test.ts', 'extensions/vscode/test/**/*.test.ts'];

export default defineConfig({
  resolve: { alias },
  test: {
    pool: 'forks',
    testTimeout: 60_000,
    hookTimeout: 60_000,
    projects: [
      { resolve: { alias }, test: { name: 'unit', include: unitInclude } },
      { resolve: { alias }, test: { name: 'integration', include: ['tests/integration/**/*.test.ts'], testTimeout: 120_000 } },
      { resolve: { alias }, test: { name: 'e2e', include: ['tests/e2e/**/*.test.ts'], testTimeout: 300_000, hookTimeout: 120_000 } },
      { resolve: { alias }, test: { name: 'security', include: ['tests/security/**/*.test.ts'], testTimeout: 300_000, hookTimeout: 120_000 } },
      { resolve: { alias }, test: { name: 'performance', include: ['tests/performance/**/*.test.ts'], testTimeout: 300_000 } },
    ],
  },
});
