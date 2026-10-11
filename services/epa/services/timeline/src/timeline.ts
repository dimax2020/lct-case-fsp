import { DomainError } from '@epa/domain';
import type { Ctx } from '@epa/platform';
import { chainHash } from '@epa/telemetry';

export interface TimelineItem {
  id: string;
  sessionId: string;
  sessionKind: 'workspace' | 'platform';
  client: string;
  sequence: number;
  type: string;
  occurredAt: string;
  receivedAt: string;
  deliveryDelayMs: number;
  summary: string;
  refs: { file?: string; snapshotId?: string; commitSha?: string; testRunId?: string; submissionId?: string; requirementChangeId?: string; relatedSequence?: number };
  payload: Record<string, unknown>;
}

export interface Interruption {
  sessionId: string;
  from: string;
  to: string;
  kind: 'delayed_delivery' | 'sequence_gap' | 'connection_lost';
  note: string;
}

/** Events delivered later than this are treated as buffered during a connectivity interruption. */
export const DELAYED_DELIVERY_MS = 30_000;

const CLIENT_RU: Record<string, string> = {
  vscode: 'VS Code',
  gateway: 'браузер',
  sidecar: 'агент workspace',
  platform: 'платформа',
};

const REASON_RU: Record<string, string> = {
  extension_connected: 'расширение подключено',
  user_closed: 'кандидат отключился',
  replaced: 'выдана новая ссылка',
  connection_lost: 'пропала связь',
  interval: 'по таймеру',
  significant_save: 'крупное сохранение',
  pre_submit: 'перед отправкой',
  git_commit: 'коммит',
  manual: 'вручную',
  initial: 'начальный снимок',
  pre_sandbox: 'перед проверкой',
  post_sandbox: 'после проверки',
  checkpoint: 'контрольная точка',
  patch: 'отличие от прошлого снимка',
  full: 'полный снимок',
};

const TEST_STATUS_RU: Record<string, string> = {
  passed: 'пройдены',
  failed: 'есть ошибки',
  error: 'сбой запуска',
  timeout: 'превышено время',
  skipped: 'пропущены',
};

function ru(map: Record<string, string>, value: unknown): string {
  const key = String(value ?? '');
  return map[key] ?? key;
}

export function describeEvent(type: string, p: any): string {
  switch (type) {
    case 'session_started': return `Сессия началась (${ru(CLIENT_RU, p.client)}${p.reason ? `, ${ru(REASON_RU, p.reason)}` : ''})`;
    case 'session_ended': return `Сессия завершена: ${ru(REASON_RU, p.reason)}`;
    case 'file_changed': return `Правка ${p.path}: +${p.insertedChars}/−${p.deletedChars} символов, +${p.insertedLines}/−${p.deletedLines} строк`;
    case 'file_saved': return `Сохранён ${p.path} (${p.bytes} байт)`;
    case 'file_created': return `Создан ${p.path}`;
    case 'file_deleted': return `Удалён ${p.path}`;
    case 'test_started': return `Запущены тесты: ${p.command}`;
    case 'test_finished': return `Тесты ${ru(TEST_STATUS_RU, p.status)}: успешно ${p.passed}, с ошибкой ${p.failed}, ${p.durationMs} мс`;
    case 'terminal_command': return `Команда \`${p.command}\` → код ${p.exitCode ?? (p.timedOut ? 'таймаут' : '?')} (${p.durationMs} мс)`;
    case 'git_commit': return `Коммит ${String(p.sha).slice(0, 8)}: ${p.message} (файлов: ${p.changedFiles?.length ?? 0})`;
    case 'snapshot_created': return `Снимок: ${ru(REASON_RU, p.reason)} (${ru(REASON_RU, p.kind)})`;
    case 'large_insertion_signal': return `Крупная вставка в ${p.file}: ${p.insertedChars} символов при пороге ${p.threshold}. Это сигнал для дополнительной проверки, а не вывод о нарушении.`;
    case 'code_copied': return `Скопировано из ${p.file}: ${p.chars} символов, ${p.lines} строк. Только внутри папки задания.`;
    case 'code_pasted': return `Вставка в ${p.file}: ${p.chars} символов, ${p.lines} строк. Источник: ${p.origin === 'workspace' ? 'эта же папка' : p.origin === 'external' ? 'вне папки задания' : 'не определён'}. Сигнал для проверки, не вывод.`;
    case 'submit_created': return `Решение сдано, версия ${p.version}`;
    case 'review_requested': return `Запрошены исправления (открытых комментариев: ${p.openComments})`;
    case 'requirement_changed': return 'Изменено условие задания';
    default: return type;
  }
}

function refsOf(type: string, p: any): TimelineItem['refs'] {
  return {
    file: p.path ?? p.file,
    snapshotId: p.snapshotId,
    commitSha: p.sha,
    testRunId: type.startsWith('test_') ? p.runId : undefined,
    submissionId: p.submissionId,
    requirementChangeId: p.requirementChangeId,
    relatedSequence: p.relatedSequence ?? undefined,
  };
}

export class TimelineService {
  constructor(private readonly ctx: Ctx) {}

  async list(practiceId: string, cursor: string | undefined, limit: number): Promise<{ items: TimelineItem[]; nextCursor: string | null }> {
    const params: unknown[] = [practiceId];
    let where = 'e.practice_id = $1';
    if (cursor) {
      let c: { t: string; s: string; q: number };
      try {
        c = JSON.parse(Buffer.from(cursor, 'base64url').toString('utf8'));
      } catch {
        throw new DomainError('VALIDATION', 'invalid cursor');
      }
      params.push(new Date(c.t), c.s, c.q);
      where += ' AND (e.occurred_at, e.session_id, e.sequence) > ($2, $3, $4)';
    }
    params.push(limit + 1);
    const rows = await this.ctx.db.query<any>(
      `SELECT e.*, s.kind AS session_kind, s.client AS session_client FROM telemetry_events e JOIN dev_sessions s ON s.id = e.session_id
       WHERE ${where} ORDER BY e.occurred_at, e.session_id, e.sequence LIMIT $${params.length}`,
      params,
    );
    const more = rows.length > limit;
    const page = rows.slice(0, limit);
    const items = page.map((r) => this.toItem(r));
    const last = page[page.length - 1];
    return {
      items,
      nextCursor: more && last ? Buffer.from(JSON.stringify({ t: new Date(last.occurred_at).toISOString(), s: last.session_id, q: last.sequence })).toString('base64url') : null,
    };
  }

  private toItem(r: any): TimelineItem {
    const occurred = new Date(r.occurred_at);
    const received = new Date(r.received_at);
    return {
      id: r.id,
      sessionId: r.session_id,
      sessionKind: r.session_kind,
      client: r.session_client,
      sequence: r.sequence,
      type: r.type,
      occurredAt: occurred.toISOString(),
      receivedAt: received.toISOString(),
      deliveryDelayMs: Math.max(0, received.getTime() - occurred.getTime()),
      summary: describeEvent(r.type, r.payload),
      refs: refsOf(r.type, r.payload),
      payload: r.payload,
    };
  }

  /** Periods without reliable data. Rendered as missing data, never as an accusation. */
  async interruptions(practiceId: string): Promise<Interruption[]> {
    const out: Interruption[] = [];
    const delayed = await this.ctx.db.query<any>(
      `SELECT session_id, occurred_at, received_at FROM telemetry_events
       WHERE practice_id = $1 AND received_at - occurred_at > ($2 || ' milliseconds')::interval ORDER BY session_id, occurred_at`,
      [practiceId, String(DELAYED_DELIVERY_MS)],
    );
    let cur: Interruption | null = null;
    for (const r of delayed) {
      const from = new Date(r.occurred_at).toISOString();
      const to = new Date(r.received_at).toISOString();
      if (cur && cur.sessionId === r.session_id && from <= cur.to) {
        if (to > cur.to) cur.to = to;
        continue;
      }
      if (cur) out.push(cur);
      cur = { sessionId: r.session_id, from, to, kind: 'delayed_delivery', note: 'Телеметрия пришла с задержкой: связь прерывалась, и агент отправил события позже. За этот промежуток данные могут быть неполными.' };
    }
    if (cur) out.push(cur);
    const diags = await this.ctx.db.query<any>(`SELECT * FROM telemetry_diagnostics WHERE practice_id = $1 AND kind = 'sequence_gap' ORDER BY created_at`, [practiceId]);
    for (const d of diags) {
      const t = new Date(d.created_at).toISOString();
      out.push({ sessionId: d.session_id, from: t, to: t, kind: 'sequence_gap', note: `События ${d.detail.expected}–${d.detail.received - 1} в этот момент не дошли.` });
    }
    const lost = await this.ctx.db.query<any>(`SELECT id, ended_at FROM dev_sessions WHERE practice_id = $1 AND end_reason = 'connection_lost'`, [practiceId]);
    for (const s of lost) {
      const t = new Date(s.ended_at).toISOString();
      out.push({ sessionId: s.id, from: t, to: t, kind: 'connection_lost', note: 'Сессия потеряла связь. После этого момента событий этой сессии нет.' });
    }
    return out.sort((a, b) => a.from.localeCompare(b.from));
  }

  /** Recomputes each session's hash chain; detects silent edits/removals of stored events. */
  async verifyIntegrity(practiceId: string): Promise<{ ok: boolean; brokenSessions: string[] }> {
    const rows = await this.ctx.db.query<any>(
      'SELECT session_id, sequence, content_hash, integrity_hash FROM telemetry_events WHERE practice_id = $1 ORDER BY session_id, sequence',
      [practiceId],
    );
    const broken = new Set<string>();
    let prevSession = '';
    let prevHash: string | null = null;
    let expectedSeq = 1;
    for (const r of rows) {
      if (r.session_id !== prevSession) {
        prevSession = r.session_id;
        prevHash = null;
        expectedSeq = 1;
      }
      if (r.sequence !== expectedSeq || chainHash(prevHash, r.content_hash) !== r.integrity_hash) broken.add(r.session_id);
      prevHash = r.integrity_hash;
      expectedSeq = r.sequence + 1;
    }
    return { ok: broken.size === 0, brokenSessions: [...broken] };
  }

  async countsByType(practiceId: string): Promise<Record<string, number>> {
    const rows = await this.ctx.db.query<{ type: string; n: number }>('SELECT type, count(*)::int AS n FROM telemetry_events WHERE practice_id = $1 GROUP BY type', [practiceId]);
    return Object.fromEntries(rows.map((r) => [r.type, r.n]));
  }
}
