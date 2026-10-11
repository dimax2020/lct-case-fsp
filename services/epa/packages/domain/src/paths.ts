import path from 'node:path';
import { DomainError } from './errors.js';

export const MAX_WORKSPACE_PATH_LENGTH = 512;
const FORBIDDEN_SEGMENTS = new Set(['.git', '.epa']);
// eslint-disable-next-line no-control-regex
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/;
const UNSAFE_CHARS = /[\\:*?"<>|]/;

/**
 * Normalises a workspace-relative path and rejects anything that could escape the
 * workspace root or reference platform-internal directories.
 */
export function normalizeWorkspacePath(input: string, opts: { allowInternal?: boolean } = {}): string {
  if (typeof input !== 'string' || input.length === 0) {
    throw new DomainError('VALIDATION', 'path must be a non-empty string');
  }
  if (input.length > MAX_WORKSPACE_PATH_LENGTH) throw new DomainError('VALIDATION', 'path too long');
  if (CONTROL_CHARS.test(input)) throw new DomainError('VALIDATION', 'path contains control characters');
  if (UNSAFE_CHARS.test(input)) throw new DomainError('VALIDATION', 'path contains unsafe characters');
  if (input.startsWith('/') || input.startsWith('~')) {
    throw new DomainError('VALIDATION', 'path must be relative to the workspace');
  }
  const segments = input.split('/').filter((s) => s !== '' && s !== '.');
  if (segments.length === 0) throw new DomainError('VALIDATION', 'path resolves to workspace root');
  for (const seg of segments) {
    if (seg === '..') throw new DomainError('VALIDATION', 'path traversal is not allowed');
    if (!opts.allowInternal && FORBIDDEN_SEGMENTS.has(seg)) {
      throw new DomainError('VALIDATION', `path segment "${seg}" is reserved`);
    }
    if (seg.length > 255) throw new DomainError('VALIDATION', 'path segment too long');
  }
  return segments.join('/');
}

/** Resolves a normalised relative path under root and double-checks containment. */
export function resolveInsideRoot(root: string, relative: string): string {
  const rel = normalizeWorkspacePath(relative);
  const absRoot = path.resolve(root);
  const abs = path.resolve(absRoot, rel);
  if (abs !== absRoot && !abs.startsWith(absRoot + path.sep)) {
    throw new DomainError('VALIDATION', 'path escapes workspace root');
  }
  return abs;
}

export function isSafeRelativePath(input: string): boolean {
  try {
    normalizeWorkspacePath(input);
    return true;
  } catch {
    return false;
  }
}
