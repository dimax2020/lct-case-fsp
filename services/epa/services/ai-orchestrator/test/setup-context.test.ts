import { describe, expect, it } from 'vitest';
import { pickSetupPaths } from '../src/setup-context.js';

describe('pickSetupPaths', () => {
  it('prefers the readme, manifest and source over lint config', () => {
    const picked = pickSetupPaths([
      'eslint.config.mjs',
      'src/lib/ats.ts',
      'package-lock.json',
      'README.md',
      'src/app/page.tsx',
      'package.json',
      'AGENTS.md',
    ]);
    expect(picked.slice(0, 4)).toEqual(['README.md', 'package.json', 'src/app/page.tsx', 'src/lib/ats.ts']);
    expect(picked).not.toContain('package-lock.json');
    expect(picked).not.toContain('AGENTS.md');
  });
});
