import type { EvidenceRefOutput } from '@epa/contracts';
import type { ContextFile } from './types.js';

/** Technologies the model must not mention unless they appear in the candidate's code. */
const TECH_TERMS: Record<string, RegExp> = {
  Redis: /\bredis\b/i,
  Kafka: /\bkafka\b/i,
  RabbitMQ: /\brabbit\s?mq\b|\bamqp\b/i,
  PostgreSQL: /\bpostgres(?:ql)?\b|\bpg\b/i,
  MySQL: /\bmysql\b/i,
  MongoDB: /\bmongo(?:db|ose)?\b/i,
  Elasticsearch: /\belastic(?:search)?\b/i,
  GraphQL: /\bgraphql\b/i,
  Kubernetes: /\bkubernetes\b|\bk8s\b/i,
  Docker: /\bdocker\b/i,
  React: /\breact\b/i,
  Express: /\bexpress\b/i,
  JWT: /\bjwt\b|\bjsonwebtoken\b/i,
  bcrypt: /\bbcrypt\b/i,
  Memcached: /\bmemcache[d]?\b/i,
  gRPC: /\bgrpc\b/i,
};

export type RejectionReason = 'unknown_file' | 'line_out_of_range' | 'quote_mismatch' | 'ungrounded_technology' | 'schema';

export interface Rejection {
  item: unknown;
  reason: RejectionReason;
  detail: string;
}

export function validateEvidence(e: EvidenceRefOutput, files: Map<string, ContextFile>): Rejection | null {
  const f = files.get(e.file);
  if (!f) return { item: e, reason: 'unknown_file', detail: `file ${e.file} is not in the analysed context` };
  if (e.lineStart > e.lineEnd || e.lineEnd > f.lineCount) {
    return { item: e, reason: 'line_out_of_range', detail: `${e.file}:${e.lineStart}-${e.lineEnd} exceeds ${f.lineCount} lines` };
  }
  if (e.quote && e.quote.trim()) {
    const excerpt = f.content.split('\n').slice(e.lineStart - 1, e.lineEnd).join('\n');
    const norm = (s: string) => s.replace(/\s+/g, ' ').trim();
    if (!norm(excerpt).includes(norm(e.quote))) return { item: e, reason: 'quote_mismatch', detail: 'quoted text not found in cited lines' };
  }
  return null;
}

/** Rejects text that names a technology absent from the analysed code (e.g. "Redis" in a project without Redis). */
export function validateGrounding(text: string, files: ContextFile[]): Rejection | null {
  const corpus = files.map((f) => `${f.path}\n${f.content}`).join('\n');
  for (const [name, re] of Object.entries(TECH_TERMS)) {
    if (re.test(text) && !re.test(corpus)) return { item: text, reason: 'ungrounded_technology', detail: `mentions ${name}, which does not appear in the code` };
  }
  return null;
}

export function filterGrounded<T extends { evidence: EvidenceRefOutput }>(
  items: T[],
  files: ContextFile[],
  textOf: (t: T) => string,
): { accepted: T[]; rejected: Rejection[] } {
  const byPath = new Map(files.map((f) => [f.path, f]));
  const accepted: T[] = [];
  const rejected: Rejection[] = [];
  for (const item of items) {
    const r = validateEvidence(item.evidence, byPath) ?? validateGrounding(textOf(item), files);
    if (r) rejected.push({ ...r, item });
    else accepted.push(item);
  }
  return { accepted, rejected };
}
