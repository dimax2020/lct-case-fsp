import { DomainError } from '@epa/domain';

export type ParsedCommand =
  | { kind: 'exec'; argv: string[] }
  | { kind: 'git'; sub: 'status' | 'log' | 'diff' };

const SHELL_META = /[;&|<>`$(){}\n\r\\]/;

/** Splits a command line into argv, honouring simple single/double quotes. No shell is ever used. */
export function splitArgv(line: string): string[] {
  const out: string[] = [];
  let cur = '';
  let quote: '"' | "'" | null = null;
  let has = false;
  for (const ch of line) {
    if (quote) {
      if (ch === quote) quote = null;
      else cur += ch;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      has = true;
    } else if (ch === ' ' || ch === '\t') {
      if (has || cur) out.push(cur);
      cur = '';
      has = false;
    } else {
      cur += ch;
      has = true;
    }
  }
  if (quote) throw new DomainError('VALIDATION', 'unterminated quote');
  if (has || cur) out.push(cur);
  return out;
}

const ALLOWED_BINARIES = new Set(['node', 'npm', 'ls', 'cat', 'pwd', 'echo', 'head', 'tail', 'wc', 'grep', 'find', 'mkdir', 'touch', 'rm', 'mv', 'cp']);
const NPM_SUBCOMMANDS = new Set(['test', 't', 'run', 'run-script', 'ls', '--version', '-v']);

/**
 * Commands are executed inside the isolated RDE (never on the host). The allowlist keeps the
 * surface small and auditable; git is routed to the server-side git service.
 */
export function parseWorkspaceCommand(line: string): ParsedCommand {
  const trimmed = line.trim();
  if (!trimmed) throw new DomainError('VALIDATION', 'empty command');
  if (trimmed.length > 2000) throw new DomainError('VALIDATION', 'command too long');
  if (SHELL_META.test(trimmed)) throw new DomainError('VALIDATION', 'shell operators are not supported; run one command at a time');
  const argv = splitArgv(trimmed);
  const [bin, sub] = argv;
  if (bin === 'git') {
    if (sub === 'status' || sub === 'log' || sub === 'diff') return { kind: 'git', sub };
    throw new DomainError('VALIDATION', 'only git status/log/diff are available in the terminal; use Commit in the IDE');
  }
  if (!ALLOWED_BINARIES.has(bin)) throw new DomainError('VALIDATION', `command "${bin}" is not allowed in this workspace`);
  if (bin === 'npm' && !NPM_SUBCOMMANDS.has(sub ?? '')) throw new DomainError('VALIDATION', 'only npm test/run/ls are allowed');
  for (const a of argv.slice(1)) {
    if (a.startsWith('/') && !a.startsWith('/workspace') && !a.startsWith('/tmp')) {
      throw new DomainError('VALIDATION', 'absolute paths outside the workspace are not allowed');
    }
    if (a.split('/').includes('..') && bin !== 'node' && bin !== 'npm') {
      throw new DomainError('VALIDATION', 'path traversal is not allowed');
    }
  }
  return { kind: 'exec', argv };
}
