import type { TelemetryEventInput } from '@epa/contracts';
import type { TelemetryTransport, TransportResult } from './agent.js';

/** Sends batches to the ingestion API with a session-scoped agent credential. */
export class HttpTransport implements TelemetryTransport {
  constructor(
    private readonly baseUrl: string,
    private readonly agentToken: string,
    private readonly fetchImpl: typeof fetch = fetch,
    private readonly timeoutMs = 10_000,
  ) {}

  async send(batch: { sessionId: string; events: TelemetryEventInput[] }): Promise<TransportResult> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/agent/events:batch`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${this.agentToken}` },
      body: JSON.stringify(batch),
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    const body = (await res.json().catch(() => ({}))) as any;
    if (res.status === 200 || (res.status === 409 && body?.gap)) return body as TransportResult;
    if (res.status >= 500 || res.status === 429) throw new Error(`ingestion unavailable (${res.status})`);
    throw new Error(`ingestion rejected batch (${res.status}): ${body?.error?.message ?? 'unknown'}`);
  }
}

/** Wraps a transport and can simulate a network outage (tests and chaos drills). */
export class FlakyTransport implements TelemetryTransport {
  offline = false;
  attempts = 0;
  constructor(private readonly inner: TelemetryTransport) {}
  async send(batch: { sessionId: string; events: TelemetryEventInput[] }): Promise<TransportResult> {
    this.attempts++;
    if (this.offline) throw new Error('network unreachable');
    return this.inner.send(batch);
  }
}
