const NOISE = new Set([
  'agents.md',
  'claude.md',
  'package-lock.json',
  'pnpm-lock.yaml',
  'yarn.lock',
  '.ds_store',
  'eslint.config.mjs',
  'eslint.config.js',
  'postcss.config.mjs',
  'next-env.d.ts',
  'tsconfig.json',
  '.gitignore',
  '.env.example',
]);

/** Lower rank is more useful for answering what the project is and what it does. */
export function rankSetupPath(filePath: string): number {
  const base = filePath.split('/').pop()!.toLowerCase();
  if (NOISE.has(base)) return 9;
  if (base === 'readme.md') return 0;
  if (base === 'package.json' || base === 'pyproject.toml' || base === 'go.mod' || base === 'cargo.toml') return 1;
  if (/(^|\/)(page|layout|main|app|index)\.(tsx|ts|jsx|js|py|go)$/.test(filePath)) return 2;
  if (/^(src|app|lib|pages|server|services)\//.test(filePath) && /\.(tsx|ts|jsx|js|py|vue|go)$/.test(filePath)) return 3;
  if (/\.(tsx|ts|jsx|js|py|vue|go|md)$/.test(filePath)) return 4;
  return 8;
}

/** Keeps the files that explain the project and drops lockfiles, lint config and agent notes. */
export function pickSetupPaths(paths: string[], limit = 10): string[] {
  return [...paths]
    .filter((p) => rankSetupPath(p) < 8)
    .sort((a, b) => rankSetupPath(a) - rankSetupPath(b) || a.localeCompare(b))
    .slice(0, limit);
}
