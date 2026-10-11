import { afterEach, describe, expect, it } from 'vitest';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { FlakyTransport, WorkspaceAgent, type TelemetryTransport, type TransportResult } from '@epa/workspace-agent';

/** In-memory server that mimics ingestion dedup semantics by (session, sequence). */
class FakeServer implements TelemetryTransport {
  stored = new Map<number, string>();
  last = 0;
  async send(batch: any): Promise<TransportResult> {
    let accepted = 0;
    let duplicates = 0;
    for (const e of batch.events) {
      if (e.sequence <= this.last) {
        duplicates++;
        continue;
      }
      if (e.sequence > this.last + 1) return { accepted, duplicates, nextExpectedSequence: this.last + 1, gap: { expected: this.last + 1, received: e.sequence } };
      this.stored.set(e.sequence, e.type);
      this.last = e.sequence;
      accepted++;
    }
    return { accepted, duplicates, nextExpectedSequence: this.last + 1, gap: null };
  }
}

const dirs: string[] = [];
const tmp = async () => {
  const d = await mkdtemp(path.join(os.tmpdir(), 'epa-agent-'));
  dirs.push(d);
  return d;
};
afterEach(async () => {
  for (const d of dirs.splice(0)) await rm(d, { recursive: true, force: true });
});

describe('workspace agent', () => {
  it('assigns gap-free sequences and emits change/save/signal events for a large paste', async () => {
    const server = new FakeServer();
    const agent = await WorkspaceAgent.open({ sessionId: 'ses_1', outboxDir: await tmp(), transport: server, autoRetry: false, largeInsertionThreshold: 100 });
    await agent.sessionStarted();
    const r = await agent.fileWritten({ path: 'src/a.js', before: null, after: 'x'.repeat(150), pastedChars: 150 });
    await agent.flush();
    expect(r.signal).toMatchObject({ file: 'src/a.js', insertedChars: 150, interpretation: 'signal_for_additional_review_not_a_verdict' });
    expect([...server.stored.values()]).toEqual(['session_started', 'file_created', 'file_changed', 'file_saved', 'code_pasted', 'large_insertion_signal']);
    expect([...server.stored.keys()]).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it('buffers during an outage and delivers each event exactly once after recovery', async () => {
    const server = new FakeServer();
    const flaky = new FlakyTransport(server);
    const dir = await tmp();
    const agent = await WorkspaceAgent.open({ sessionId: 'ses_2', outboxDir: dir, transport: flaky, autoRetry: false });
    flaky.offline = true;
    await agent.terminalCommand({ command: 'npm test', exitCode: 0, durationMs: 10, timedOut: false });
    await agent.fileDeleted('old.js');
    await agent.flush();
    expect(agent.pendingCount).toBe(2);
    expect(server.stored.size).toBe(0);

    // Agent restarts: the durable outbox survives.
    const restarted = await WorkspaceAgent.open({ sessionId: 'ses_2', outboxDir: dir, transport: flaky, autoRetry: false });
    expect(restarted.pendingCount).toBe(2);
    flaky.offline = false;
    await restarted.flush();
    await restarted.flush();
    expect(restarted.pendingCount).toBe(0);
    expect([...server.stored.entries()]).toEqual([[1, 'terminal_command'], [2, 'file_deleted']]);
    await restarted.testStarted('tr_1', 'npm test');
    await restarted.flush();
    expect(server.stored.get(3)).toBe('test_started');
  });

  it('redacts secrets in commands and rejects unsafe paths', async () => {
    const sent: any[] = [];
    const agent = await WorkspaceAgent.open({
      sessionId: 'ses_3',
      outboxDir: await tmp(),
      autoRetry: false,
      transport: { send: async (b) => (sent.push(...b.events), { accepted: b.events.length, duplicates: 0, nextExpectedSequence: b.events.at(-1)!.sequence + 1, gap: null }) },
    });
    await agent.terminalCommand({ command: 'API_TOKEN=supersecret npm test', exitCode: 0, durationMs: 1, timedOut: false });
    await agent.flush();
    expect(JSON.stringify(sent)).not.toContain('supersecret');
    await expect(agent.fileDeleted('../../etc/passwd')).rejects.toThrow();
  });
});
