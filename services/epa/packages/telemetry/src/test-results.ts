export interface ParsedTestResults {
  tests: number;
  passed: number;
  failed: number;
  skipped: number;
  durationMs: number | null;
  failedTests: string[];
  coverage: { lines: number; branches: number | null; functions: number | null } | null;
}

const SUMMARY = /^(?:#|ℹ)\s+(tests|pass|fail|skipped|skip|duration_ms)\s+([\d.]+)\s*$/;
const NOT_OK = /^\s*not ok \d+ - (.+?)\s*$/;
const SPEC_FAIL = /^\s*✖ (.+?)(?: \([\d.]+m?s\))?\s*$/;
const COVERAGE_ALL = /^(?:#|ℹ)\s+all files\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)/;

/**
 * Parses node:test output (TAP or spec reporter). Returns null when no summary is present, so
 * a crash or unparsable output can never be interpreted as a successful run.
 */
export function parseNodeTestOutput(output: string, opts: { coverageEnabled: boolean }): ParsedTestResults | null {
  const counts: Record<string, number> = {};
  const failedTests = new Set<string>();
  let coverage: ParsedTestResults['coverage'] = null;
  for (const raw of output.split('\n')) {
    const line = raw.replace(/\r$/, '');
    const m = SUMMARY.exec(line);
    if (m) {
      counts[m[1] === 'skip' ? 'skipped' : m[1]] = Number(m[2]);
      continue;
    }
    const nf = NOT_OK.exec(line) ?? SPEC_FAIL.exec(line);
    if (nf && !/^failing tests:?$/i.test(nf[1])) failedTests.add(nf[1].replace(/\s+#.*$/, '').slice(0, 300));
    if (opts.coverageEnabled) {
      const c = COVERAGE_ALL.exec(line);
      if (c) coverage = { lines: Number(c[1]), branches: Number(c[2]), functions: Number(c[3]) };
    }
  }
  if (counts.pass === undefined || counts.fail === undefined) return null;
  return {
    tests: counts.tests ?? counts.pass + counts.fail,
    passed: counts.pass,
    failed: counts.fail,
    skipped: counts.skipped ?? 0,
    durationMs: counts.duration_ms !== undefined ? Math.round(counts.duration_ms) : null,
    failedTests: [...failedTests].slice(0, 100),
    coverage: opts.coverageEnabled ? coverage : null,
  };
}
