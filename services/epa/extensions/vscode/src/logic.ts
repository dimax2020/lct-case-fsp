import { createHash } from 'node:crypto';
import { redactSecrets } from './redact.js';

export const LARGE_INSERTION_THRESHOLD = 800;
export const PASTE_MIN_UNMARKED_CHARS = 8;

/** A paste matches an earlier copy in this folder when the snippet hashes are equal. */
export function pasteOrigin(snippetHash: string, copiedHashes: ReadonlySet<string>): 'workspace' | 'external' {
  return copiedHashes.has(snippetHash) ? 'workspace' : 'external';
}
export const MAX_COMMAND_LENGTH = 2000;
export const MAX_SAFE_LOG = 16 * 1024;
export const SNAPSHOT_MAX_FILE_BYTES = 1024 * 1024;
export const SNAPSHOT_MAX_TOTAL_BYTES = 4 * 1024 * 1024;
export const SNAPSHOT_MAX_FILES = 400;

const IGNORED = new Set(['node_modules', '.git', '.epa', 'dist', 'out', 'coverage', '.next']);
const SECRET_FILE = /(^|\/)\.env($|\.)|(^|\/)(id_rsa|\.npmrc|\.pypirc|credentials\.json)$|\.(pem|key|p12)$/i;

export interface EditStats {
  insertedChars: number;
  deletedChars: number;
  insertedLines: number;
  deletedLines: number;
}

export function sha256Hex(data: string): string {
  return createHash('sha256').update(data).digest('hex');
}

export function computeEditStats(before: string, after: string): EditStats {
  const a = before.length ? before.split('\n') : [];
  const b = after.length ? after.split('\n') : [];
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let endA = a.length - 1;
  let endB = b.length - 1;
  while (endA >= start && endB >= start && a[endA] === b[endB]) {
    endA--;
    endB--;
  }
  const removed = a.slice(start, endA + 1);
  const added = b.slice(start, endB + 1);
  const chars = (lines: string[]) => lines.reduce((n, l) => n + l.length, 0) + Math.max(0, lines.length - 1);
  return {
    insertedChars: chars(added),
    deletedChars: chars(removed),
    insertedLines: added.length,
    deletedLines: removed.length,
  };
}

/** Workspace-relative POSIX path, or null when the file is outside the practice folder or ignored. */
export function workspaceRelative(rootFsPath: string, fileFsPath: string): string | null {
  const root = rootFsPath.replace(/\\/g, '/').replace(/\/$/, '');
  const file = fileFsPath.replace(/\\/g, '/');
  if (file !== root && !file.startsWith(root + '/')) return null;
  const rel = file.slice(root.length).replace(/^\//, '');
  if (!rel || rel.length > 512) return null;
  const segments = rel.split('/');
  if (segments.some((s) => s === '..' || s === '' || IGNORED.has(s))) return null;
  if (SECRET_FILE.test(rel)) return null;
  if (/[\u0000-\u001f\u007f\\:*?"<>|]/.test(rel)) return null;
  return rel;
}

export function isInsideRoot(rootFsPath: string, fileFsPath: string): boolean {
  const root = rootFsPath.replace(/\\/g, '/').replace(/\/$/, '');
  const file = fileFsPath.replace(/\\/g, '/').replace(/\/$/, '');
  return file === root || file.startsWith(root + '/');
}

export function classifyCommand(command: string): 'test' | 'terminal' {
  const c = command.trim();
  if (/\b(npm|pnpm|yarn|bun)\b[^\n]*\b(test|vitest|jest)\b/.test(c)) return 'test';
  if (/\bnode\b[^\n]*--test\b/.test(c)) return 'test';
  if (/^\s*(vitest|jest|pytest)\b/.test(c)) return 'test';
  if (/\b(pytest|cargo|go)\b[^\n]*\btest\b/.test(c)) return 'test';
  return 'terminal';
}

export function redactCommand(command: string): string {
  return redactSecrets(command).slice(0, MAX_COMMAND_LENGTH);
}

export function clipLog(input: string): string {
  const text = redactSecrets(input);
  const buf = Buffer.from(text, 'utf8');
  if (buf.length <= MAX_SAFE_LOG) return text;
  const marker = '\n...[truncated]';
  return buf.subarray(0, MAX_SAFE_LOG - Buffer.byteLength(marker)).toString('utf8').replace(/\uFFFD+$/, '') + marker;
}

export function testStatus(exitCode: number | null | undefined): 'PASSED' | 'FAILED' | 'UNKNOWN' {
  if (exitCode === null || exitCode === undefined) return 'UNKNOWN';
  return exitCode === 0 ? 'PASSED' : 'FAILED';
}

/** Best-effort counts from node:test / jest summaries. Null when the log has no counts. */
export function parseTestCounts(log: string): { passed: number; failed: number } | null {
  const nodePass = log.match(/#\s+pass\s+(\d+)/);
  const nodeFail = log.match(/#\s+fail\s+(\d+)/);
  if (nodePass || nodeFail) return { passed: Number(nodePass?.[1] ?? 0), failed: Number(nodeFail?.[1] ?? 0) };
  const jestFail = log.match(/(\d+)\s+failed/);
  const jestPass = log.match(/(\d+)\s+passed/);
  if (jestPass || jestFail) return { passed: Number(jestPass?.[1] ?? 0), failed: Number(jestFail?.[1] ?? 0) };
  return null;
}

export function looksBinary(bytes: Uint8Array): boolean {
  const n = Math.min(bytes.length, 8000);
  for (let i = 0; i < n; i++) if (bytes[i] === 0) return true;
  return false;
}
