import { redactSecrets } from '@epa/telemetry';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';
const LEVELS: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 };

export interface Logger {
  debug(msg: string, fields?: Record<string, unknown>): void;
  info(msg: string, fields?: Record<string, unknown>): void;
  warn(msg: string, fields?: Record<string, unknown>): void;
  error(msg: string, fields?: Record<string, unknown>): void;
  child(fields: Record<string, unknown>): Logger;
}

const SENSITIVE_KEYS = /token|secret|password|authorization|cookie|content|body/i;

function scrub(value: unknown, depth = 0): unknown {
  if (depth > 4) return '[depth]';
  if (typeof value === 'string') return redactSecrets(value).slice(0, 2000);
  if (Array.isArray(value)) return value.slice(0, 50).map((v) => scrub(v, depth + 1));
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, SENSITIVE_KEYS.test(k) ? '[omitted]' : scrub(v, depth + 1)]),
    );
  }
  return value;
}

/** Structured JSON logger. Sensitive keys are dropped and string values are secret-redacted. */
export function createLogger(opts: { level?: LogLevel; sink?: (line: string) => void; base?: Record<string, unknown> } = {}): Logger {
  const min = LEVELS[opts.level ?? 'info'];
  const sink = opts.sink ?? ((line: string) => process.stdout.write(line + '\n'));
  const base = opts.base ?? {};
  const emit = (level: LogLevel, msg: string, fields?: Record<string, unknown>) => {
    if (LEVELS[level] < min) return;
    sink(JSON.stringify({ ts: new Date().toISOString(), level, msg: redactSecrets(msg), ...(scrub({ ...base, ...fields }) as object) }));
  };
  return {
    debug: (m, f) => emit('debug', m, f),
    info: (m, f) => emit('info', m, f),
    warn: (m, f) => emit('warn', m, f),
    error: (m, f) => emit('error', m, f),
    child: (fields) => createLogger({ ...opts, base: { ...base, ...fields } }),
  };
}

export const silentLogger: Logger = createLogger({ sink: () => undefined });

type Labels = Record<string, string>;
const key = (name: string, labels: Labels = {}) =>
  `${name}{${Object.entries(labels).sort().map(([k, v]) => `${k}="${v.replace(/"/g, '')}"`).join(',')}}`;

export class Metrics {
  private counters = new Map<string, number>();
  private gauges = new Map<string, number>();
  private hist = new Map<string, { count: number; sum: number; buckets: number[] }>();
  private static BUCKETS = [5, 25, 100, 250, 1000, 5000, 30000];

  inc(name: string, labels?: Labels, by = 1): void {
    const k = key(name, labels);
    this.counters.set(k, (this.counters.get(k) ?? 0) + by);
  }

  gauge(name: string, value: number, labels?: Labels): void {
    this.gauges.set(key(name, labels), value);
  }

  observe(name: string, value: number, labels?: Labels): void {
    const k = key(name, labels);
    const h = this.hist.get(k) ?? { count: 0, sum: 0, buckets: Metrics.BUCKETS.map(() => 0) };
    h.count++;
    h.sum += value;
    Metrics.BUCKETS.forEach((b, i) => {
      if (value <= b) h.buckets[i]++;
    });
    this.hist.set(k, h);
  }

  counter(name: string, labels?: Labels): number {
    return this.counters.get(key(name, labels)) ?? 0;
  }

  render(): string {
    const lines: string[] = [];
    for (const [k, v] of this.counters) lines.push(`${k} ${v}`);
    for (const [k, v] of this.gauges) lines.push(`${k} ${v}`);
    for (const [k, h] of this.hist) {
      const [name, labels] = k.split('{');
      const lbl = labels.slice(0, -1);
      Metrics.BUCKETS.forEach((b, i) => lines.push(`${name}_bucket{${lbl}${lbl ? ',' : ''}le="${b}"} ${h.buckets[i]}`));
      lines.push(`${name}_count{${lbl}} ${h.count}`, `${name}_sum{${lbl}} ${h.sum}`);
    }
    return lines.join('\n') + '\n';
  }
}
