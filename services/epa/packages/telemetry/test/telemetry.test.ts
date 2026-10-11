import { describe, expect, it } from 'vitest';
import {
  REDACTED,
  canonicalJson,
  chainHash,
  classifyLargeInsertion,
  computeEditStats,
  eventContentHash,
  isSecretFile,
  parseNodeTestOutput,
  redactSecrets,
  safeLog,
} from '@epa/telemetry';

describe('secret redaction', () => {
  it.each([
    ['export API_KEY=abc123def456', 'abc123def456'],
    ['curl -H "Authorization: Bearer eyJhbGciOi.eyJzdWIiOiIx.c2lnbmF0dXJl" https://x', 'eyJhbGciOi'],
    ['psql postgres://admin:hunter2@db:5432/app', 'hunter2'],
    ['node deploy.js --password s3cr3t!', 's3cr3t!'],
    ['AWS key AKIAABCDEFGHIJKLMNOP used', 'AKIAABCDEFGHIJKLMNOP'],
    ['token ghp_abcdefghijklmnopqrstuvwxyz0123456789', 'ghp_abcdefghij'],
    ['DB_PASSWORD="quoted value" npm test', 'quoted value'],
    ['-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIB\n-----END RSA PRIVATE KEY-----', 'MIIEpAIB'],
  ])('redacts %j', (input, secret) => {
    const out = redactSecrets(input);
    expect(out).not.toContain(secret);
    expect(out).toContain(REDACTED);
  });

  it('leaves ordinary commands intact', () => {
    expect(redactSecrets('npm test -- --grep session')).toBe('npm test -- --grep session');
    expect(redactSecrets('ls src/auth')).toBe('ls src/auth');
  });

  it('safeLog redacts then truncates with a marker', () => {
    const r = safeLog(`SECRET_TOKEN=abc ${'x'.repeat(5000)}`, 1000);
    expect(r.truncated).toBe(true);
    expect(Buffer.byteLength(r.text)).toBeLessThanOrEqual(1000);
    expect(r.text).toContain('[truncated');
    expect(r.text).not.toContain('abc ');
  });

  it('detects secret files', () => {
    expect(isSecretFile('.env')).toBe(true);
    expect(isSecretFile('config/.env.production')).toBe(true);
    expect(isSecretFile('keys/server.pem')).toBe(true);
    expect(isSecretFile('src/env.js')).toBe(false);
  });
});

describe('large insertion signal', () => {
  it('is emitted only at or above the threshold and is never a verdict', () => {
    expect(classifyLargeInsertion({ file: 'a.js', insertedChars: 799, threshold: 800 })).toBeNull();
    const s = classifyLargeInsertion({ file: 'a.js', insertedChars: 800, threshold: 800, relatedSequence: 7 });
    expect(s).toEqual({ file: 'a.js', insertedChars: 800, threshold: 800, relatedSequence: 7, interpretation: 'signal_for_additional_review_not_a_verdict' });
    expect(JSON.stringify(s)).not.toMatch(/cheat|fraud|violation/i);
  });
});

describe('edit stats and hashes', () => {
  it('computes aggregated diff metadata', () => {
    expect(computeEditStats('a\nb\nc', 'a\nB\nc')).toEqual({ insertedChars: 1, deletedChars: 1, insertedLines: 1, deletedLines: 1 });
    expect(computeEditStats('', 'hello')).toMatchObject({ insertedChars: 5, deletedChars: 0 });
  });

  it('canonical JSON is key-order independent', () => {
    expect(canonicalJson({ b: 1, a: [{ d: 1, c: 2 }] })).toBe(canonicalJson({ a: [{ c: 2, d: 1 }], b: 1 }));
  });

  it('content hash identifies retries; chain hash binds predecessor', () => {
    const e = { sessionId: 's', sequence: 1, type: 'file_saved', occurredAt: '2026-01-01T00:00:00.000Z', payloadVersion: 1, payload: { path: 'a', bytes: 1 } };
    expect(eventContentHash(e)).toBe(eventContentHash({ ...e, payload: { bytes: 1, path: 'a' } }));
    expect(eventContentHash(e)).not.toBe(eventContentHash({ ...e, sequence: 2 }));
    expect(chainHash(null, 'x')).not.toBe(chainHash('p', 'x'));
  });
});

describe('node:test output parser', () => {
  const tap = `TAP version 13\nok 1 - adds\nnot ok 2 - multiplication is broken\n  ---\n  ...\n1..2\n# tests 2\n# suites 0\n# pass 1\n# fail 1\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 41.2\n`;
  it('parses TAP summary and exact failing test names', () => {
    expect(parseNodeTestOutput(tap, { coverageEnabled: false })).toEqual({ tests: 2, passed: 1, failed: 1, skipped: 0, durationMs: 41, failedTests: ['multiplication is broken'], coverage: null });
  });
  it('parses spec reporter output', () => {
    const spec = `✔ adds (0.5ms)\n✖ broken (1.2ms)\nℹ tests 2\nℹ pass 1\nℹ fail 1\nℹ duration_ms 12\n`;
    expect(parseNodeTestOutput(spec, { coverageEnabled: false })).toMatchObject({ passed: 1, failed: 1, failedTests: ['broken'] });
  });
  it('reports coverage only when the task enables it', () => {
    const withCov = tap + '# all files            |  92.31 |    83.33 |  100.00 |\n';
    expect(parseNodeTestOutput(withCov, { coverageEnabled: false })!.coverage).toBeNull();
    expect(parseNodeTestOutput(withCov, { coverageEnabled: true })!.coverage).toEqual({ lines: 92.31, branches: 83.33, functions: 100 });
  });
  it('returns null for crashed/unparsable output', () => {
    expect(parseNodeTestOutput('Segmentation fault', { coverageEnabled: false })).toBeNull();
  });
});
