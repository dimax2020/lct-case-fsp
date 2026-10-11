import { describe, expect, it } from 'vitest';
import { classifyCommand, computeEditStats, parseTestCounts, pasteOrigin, redactCommand, workspaceRelative } from '../src/logic.js';

describe('vscode telemetry boundaries', () => {
  it('keeps paths inside the practice folder and drops secrets and dependencies', () => {
    const root = '/work/task';
    expect(workspaceRelative(root, '/work/task/src/auth/password.js')).toBe('src/auth/password.js');
    expect(workspaceRelative(root, '/work/other/file.js')).toBeNull();
    expect(workspaceRelative(root, '/work/task/node_modules/left-pad/index.js')).toBeNull();
    expect(workspaceRelative(root, '/work/task/.env')).toBeNull();
    expect(workspaceRelative(root, '/work/task/.git/config')).toBeNull();
  });

  it('classifies test commands and redacts secrets before they leave the machine', () => {
    expect(classifyCommand('npm test')).toBe('test');
    expect(classifyCommand('node --test')).toBe('test');
    expect(classifyCommand('ls src')).toBe('terminal');
    expect(redactCommand('curl -H "Authorization: Bearer super-secret-token" https://example.test')).not.toContain('super-secret-token');
  });

  it('marks a paste as internal only when the same fragment was copied in this folder', () => {
    const copied = new Set(['abc']);
    expect(pasteOrigin('abc', copied)).toBe('workspace');
    expect(pasteOrigin('other', copied)).toBe('external');
  });

  it('counts an insertion against the previous file text', () => {
    const stats = computeEditStats('a\n', 'a\nhello\n');
    expect(stats.insertedChars).toBeGreaterThan(0);
    expect(parseTestCounts('# pass 2\n# fail 1\n')).toEqual({ passed: 2, failed: 1 });
  });
});
