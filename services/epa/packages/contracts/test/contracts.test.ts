import { describe, expect, it } from 'vitest';
import { analysisResult, createPracticeReq, parseTelemetryPayload, telemetryBatch, telemetryPayloads } from '@epa/contracts';

const ev = (sequence: number, type: string, payload: unknown) => ({ sequence, type, occurredAt: '2026-01-01T00:00:00.000Z', payloadVersion: 1, payload });

describe('telemetry contract v1', () => {
  it('accepts a valid batch', () => {
    expect(() => telemetryBatch.parse({ sessionId: 'ses_1', events: [ev(1, 'file_created', { path: 'src/a.js' })] })).not.toThrow();
  });

  it('rejects unknown fields so agents cannot smuggle extra data', () => {
    expect(() => parseTelemetryPayload('file_saved', { path: 'a.js', contentHash: 'a'.repeat(64), bytes: 1, clipboard: 'x' })).toThrow();
    expect(() => telemetryBatch.parse({ sessionId: 'ses_1', events: [ev(1, 'file_created', {})], extra: 1 })).toThrow();
  });

  it('rejects unsafe paths in payloads', () => {
    for (const path of ['../x', '/etc/passwd', '.git/config', 'C:\\Users\\x']) {
      expect(() => parseTelemetryPayload('file_created', { path })).toThrow();
    }
  });

  it('rejects keystroke-like event types', () => {
    expect(() => telemetryBatch.parse({ sessionId: 'ses_1', events: [ev(1, 'keypress', { key: 'a' })] })).toThrow();
    expect(Object.keys(telemetryPayloads)).not.toContain('keypress');
    expect(Object.keys(telemetryPayloads)).not.toContain('clipboard');
  });

  it('enforces batch size and payload version', () => {
    const many = Array.from({ length: 501 }, (_, i) => ev(i + 1, 'file_created', { path: 'a.js' }));
    expect(() => telemetryBatch.parse({ sessionId: 's', events: many })).toThrow();
    expect(() => telemetryBatch.parse({ sessionId: 's', events: [{ ...ev(1, 'file_created', { path: 'a' }), payloadVersion: 2 }] })).toThrow();
  });

  it('large insertion payload must carry the non-verdict interpretation', () => {
    const base = { file: 'a.js', insertedChars: 900, threshold: 800, relatedSequence: 3 };
    expect(() => parseTelemetryPayload('large_insertion_signal', { ...base, interpretation: 'signal_for_additional_review_not_a_verdict' })).not.toThrow();
    expect(() => parseTelemetryPayload('large_insertion_signal', { ...base, interpretation: 'cheating' })).toThrow();
  });
});

describe('AI output contract', () => {
  it('requires evidence on every finding', () => {
    const f = { category: 'security', severity: 'high', title: 'Timing leak', explanation: 'Non constant-time compare.', recommendation: 'Use timingSafeEqual.' };
    expect(() => analysisResult.parse({ summary: '', findings: [f], strengths: [] })).toThrow();
    expect(() => analysisResult.parse({ summary: '', findings: [{ ...f, evidence: { file: 'a.js', lineStart: 1, lineEnd: 2 } }], strengths: [] })).not.toThrow();
  });
});

describe('API contract', () => {
  it('validates practice creation', () => {
    const ok = { title: 'Task', description: 'd', template: 'auth-service', deadline: '2030-01-01T00:00:00Z' };
    expect(() => createPracticeReq.parse(ok)).not.toThrow();
    expect(() => createPracticeReq.parse({ ...ok, template: '../etc' })).toThrow();
    expect(() => createPracticeReq.parse({ ...ok, workspacePolicy: { network: 'host' } })).toThrow();
  });
});
