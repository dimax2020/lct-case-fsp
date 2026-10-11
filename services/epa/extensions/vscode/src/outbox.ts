import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';

export interface AgentEvent {
  sequence: number;
  type: string;
  occurredAt: string;
  payloadVersion: 1;
  payload: Record<string, unknown>;
}

interface OutboxState {
  sessionId: string;
  nextSequence: number;
  pending: AgentEvent[];
}

export interface TransportResult {
  accepted: number;
  duplicates: number;
  nextExpectedSequence: number;
  gap: { expected: number; received: number } | null;
}

export class EventOutbox {
  private state: OutboxState;
  private flushing: Promise<void> | null = null;
  private failures = 0;
  private timer: NodeJS.Timeout | null = null;
  lastError: string | null = null;

  private constructor(
    private readonly file: string,
    private readonly send: (batch: { sessionId: string; events: AgentEvent[] }) => Promise<TransportResult>,
    state: OutboxState,
  ) {
    this.state = state;
  }

  static async open(dir: string, sessionId: string, send: EventOutbox['send']): Promise<EventOutbox> {
    await mkdir(dir, { recursive: true });
    const file = path.join(dir, 'outbox.json');
    let state: OutboxState = { sessionId, nextSequence: 1, pending: [] };
    try {
      const parsed = JSON.parse(await readFile(file, 'utf8')) as OutboxState;
      if (parsed.sessionId === sessionId) state = parsed;
    } catch {
      /* first session in this profile */
    }
    return new EventOutbox(file, send, state);
  }

  get pendingCount(): number {
    return this.state.pending.length;
  }

  get sessionId(): string {
    return this.state.sessionId;
  }

  private persistChain: Promise<void> = Promise.resolve();

  private persist(): Promise<void> {
    const snapshot = JSON.stringify(this.state);
    this.persistChain = this.persistChain.then(async () => {
      const tmp = `${this.file}.tmp`;
      await writeFile(tmp, snapshot);
      await rename(tmp, this.file);
    });
    return this.persistChain;
  }

  async record(type: string, payload: Record<string, unknown>, occurredAt = new Date()): Promise<number> {
    const sequence = this.state.nextSequence++;
    this.state.pending.push({ sequence, type, occurredAt: occurredAt.toISOString(), payloadVersion: 1, payload });
    await this.persist();
    void this.flush().catch(() => undefined);
    return sequence;
  }

  async flush(): Promise<void> {
    if (this.flushing) return this.flushing;
    this.flushing = this.drain().finally(() => {
      this.flushing = null;
    });
    return this.flushing;
  }

  private async drain(): Promise<void> {
    while (this.state.pending.length > 0) {
      const batch = this.state.pending.slice(0, 100);
      let res: TransportResult;
      try {
        res = await this.send({ sessionId: this.state.sessionId, events: batch });
      } catch (e) {
        this.failures++;
        this.lastError = e instanceof Error ? e.message : String(e);
        this.schedule();
        return;
      }
      this.failures = 0;
      this.lastError = null;
      this.state.pending = this.state.pending.filter((ev) => ev.sequence >= res.nextExpectedSequence);
      await this.persist();
      if (res.gap) {
        this.lastError = `сервер ждёт событие ${res.nextExpectedSequence}`;
        return;
      }
    }
  }

  private schedule(): void {
    if (this.timer) return;
    const delay = Math.min(30_000, 500 * 2 ** Math.min(this.failures, 6));
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.flush();
    }, delay);
    this.timer.unref?.();
  }

  close(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }
}

export async function postJson(
  url: string,
  token: string,
  body: unknown,
  timeoutMs = 15_000,
  headers: Record<string, string> = {},
): Promise<{ status: number; body: any }> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}`, ...headers },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  const parsed = await res.json().catch(() => ({}));
  return { status: res.status, body: parsed };
}
