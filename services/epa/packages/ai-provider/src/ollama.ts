import { z, type ZodType } from 'zod';
import { analysisResult, improvementSet, interviewEvaluation, materialsReview, processReview, questionSet, taskSuggestionSet } from '@epa/contracts';
import { buildAnalysisMessages, buildImprovementMessages, buildInterviewMessages, buildMaterialsMessages, buildProcessMessages, buildQuestionMessages, buildTaskSuggestionMessages, type ChatMessage } from './prompts.js';
import { AiProviderError, PROMPT_TEMPLATE_VERSION, type AnalysisInput, type CodeAnalysisProvider, type InterviewInput, type MaterialsInput, type ProcessInput, type QuestionInput, type TaskSuggestionInput } from './types.js';

export interface OllamaOptions {
  baseUrl: string;
  model?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

function ollamaDown(e: { message?: string; cause?: { code?: string; name?: string } } | null | undefined): string {
  const code = e?.cause?.code || e?.cause?.name || '';
  const detail = [e?.message, code].filter(Boolean).join(' ');
  return `Не удалось связаться с Ollama${detail ? `: ${detail}` : ''}. Проверьте, что Ollama запущена, и повторите анализ.`;
}

function isTimeout(e: { name?: string; message?: string } | null | undefined): boolean {
  return e?.name === 'TimeoutError' || e?.name === 'AbortError' || /aborted due to timeout/i.test(String(e?.message ?? ''));
}

/** Smaller windows answer faster. The cap still fits the numbered project files. */
function contextWindow(messages: ChatMessage[]): number {
  const chars = messages.reduce((n, message) => n + message.content.length, 0);
  const tokens = Math.ceil(chars / 3) + 2_048;
  return Math.min(32_768, Math.max(4_096, Math.ceil(tokens / 1_024) * 1_024));
}
const FALLBACK_MODELS = [
  'qwen2.5-coder:0.5b',
  'qwen2.5-coder:3b',
  'qwen3-coder',
  'qwen3-coder:30b',
  'qwen3-coder:14b',
  'qwen2.5-coder:14b',
  'qwen2.5-coder',
  'qwen2.5:14b',
  'qwen3.5:9b',
  'qwen3.5:4b',
  'qwen2.5:7b',
];

/** Picks the configured model if installed, otherwise the closest coding-capable fallback. */
export function pickOllamaModel(wanted: string, installed: string[]): string | null {
  const names = installed.filter((n) => !/embed/i.test(n));
  const match = (want: string) => names.find((n) => n === want || n.startsWith(`${want}:`));
  return match(wanted) ?? FALLBACK_MODELS.map(match).find((n): n is string => !!n) ?? names[0] ?? null;
}

/**
 * Local Ollama adapter. Default model is qwen2.5-coder:0.5b; if it is not pulled, the adapter
 * falls back to an installed Qwen model so analysis still runs.
 */
export class OllamaQwen3Coder14BProvider implements CodeAnalysisProvider {
  readonly meta: { providerId: string; modelId: string; templateVersion: string };
  private readonly fetchImpl: typeof fetch;

  constructor(private readonly opts: OllamaOptions) {
    this.meta = { providerId: 'ollama', modelId: opts.model ?? 'qwen2.5-coder:0.5b', templateVersion: PROMPT_TEMPLATE_VERSION };
    this.fetchImpl = opts.fetchImpl ?? fetch;
  }

  private base() {
    return this.opts.baseUrl.replace(/\/$/, '');
  }

  private async installedModels(): Promise<string[]> {
    try {
      const res = await this.fetchImpl(`${this.base()}/api/tags`, { signal: AbortSignal.timeout(5_000) });
      if (!res.ok) return [];
      const body = (await res.json()) as { models?: { name?: string }[] };
      return (body.models ?? []).map((m) => m.name).filter((n): n is string => typeof n === 'string');
    } catch {
      return [];
    }
  }

  /** A second call if the setup model answered in English. File paths may stay in Latin. */
  private async chatInRussian<T>(messages: ChatMessage[], schema: ZodType<T>, model?: string, onText?: (text: string) => void, predict?: number): Promise<T> {
    const first = await this.chat(messages, schema, false, model, onText, predict);
    if (isRussianText(first)) return first;
    return this.chat(
      [
        ...messages,
        {
          role: 'user',
          content:
            'Предыдущий ответ был не на русском. Повтори тот же JSON. Поля summary, description, title и text напиши только по-русски. Латиница допустима для путей и имён из проекта.',
        },
      ],
      schema,
      false,
      model,
      onText,
      predict,
    );
  }

  private async chat<T>(messages: ChatMessage[], schema: ZodType<T>, retried = false, modelOverride?: string, onText?: (text: string) => void, predict?: number): Promise<T> {
    const model = modelOverride || this.meta.modelId;
    const idleMs = this.opts.timeoutMs ?? 180_000;
    const totalMs = Math.max(idleMs * 3, 900_000);
    const ctrl = new AbortController();
    const started = Date.now();
    const abort = () => {
      if (!ctrl.signal.aborted) ctrl.abort(new DOMException('The operation was aborted due to timeout', 'TimeoutError'));
    };
    let idle = setTimeout(abort, idleMs);
    const touch = () => {
      if (Date.now() - started >= totalMs) {
        abort();
        return;
      }
      clearTimeout(idle);
      idle = setTimeout(abort, idleMs);
    };
    const stop = () => clearTimeout(idle);
    const timedOut = new AiProviderError('Модель не успела ответить. Нажмите «Повторить разбор».', 'timeout');
    try {
      let res: Response;
      try {
        res = await this.fetchImpl(`${this.base()}/api/chat`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            model,
            messages,
            stream: Boolean(onText),
            format: z.toJSONSchema(schema),
            options: { temperature: 0, num_ctx: contextWindow(messages), ...(predict ? { num_predict: predict } : {}) },
          }),
          signal: ctrl.signal,
        });
      } catch (e: any) {
        if (isTimeout(e)) throw timedOut;
        throw new AiProviderError(ollamaDown(e), 'unavailable');
      }
      if (!res.ok) {
        const detail = (await res.text().catch(() => '')).slice(0, 300);
        if (res.status === 404 && !retried) {
          const installed = await this.installedModels();
          const next = pickOllamaModel(model, installed);
          if (next && next !== model) {
            if (!modelOverride) this.meta.modelId = next;
            return this.chat(messages, schema, true, next, onText, predict);
          }
          const have = installed.length ? installed.join(', ') : 'none';
          throw new AiProviderError(
            `Ollama model '${model}' is not installed (HTTP 404). Installed: ${have}. Pull it with: ollama pull ${model} — or set OLLAMA_MODEL to one of the installed names.`,
            'http_error',
          );
        }
        throw new AiProviderError(`ollama returned HTTP ${res.status}${detail ? `: ${detail}` : ''}`, 'http_error');
      }
      let content: string | undefined;
      try {
        content = onText
          ? await readOllamaStream(res, (text) => {
              touch();
              onText(text);
            })
          : ((await res.json().catch(() => null)) as { message?: { content?: string } } | null)?.message?.content;
      } catch (e: any) {
        if (e instanceof AiProviderError) throw e;
        if (isTimeout(e) || ctrl.signal.aborted) throw timedOut;
        throw new AiProviderError(ollamaDown(e), 'unavailable');
      }
      if (typeof content !== 'string') throw new AiProviderError('ollama response missing message content', 'invalid_output');
      let parsed: unknown;
      try {
        parsed = parseModelJson(content);
      } catch {
        throw new AiProviderError('model output is not valid JSON', 'invalid_output');
      }
      const fitted = acceptModelJson(schema, parsed);
      if (!fitted.ok) throw new AiProviderError(`model output violates schema: ${fitted.message}`, 'invalid_output');
      return fitted.data;
    } finally {
      stop();
    }
  }

  analyzeCode(input: AnalysisInput, onText?: (text: string) => void) {
    const messages = buildAnalysisMessages(input);
    const ask = (predict: number, extra?: ChatMessage) => this.chat(extra ? [...messages, extra] : messages, analysisResult, false, input.model, onText, predict);
    return ask(3072).catch((e) => {
      if (!(e instanceof AiProviderError) || e.kind !== 'invalid_output') throw e;
      return ask(1536, { role: 'user', content: 'Предыдущий ответ оборвался. Верни короткий JSON: summary на русском, findings и strengths можно пустыми массивами, authorship с label и summary.' });
    });
  }

  generateQuestions(input: QuestionInput, onText?: (text: string) => void) {
    const messages = buildQuestionMessages(input);
    const ask = (predict: number, extra?: ChatMessage) => this.chat(extra ? [...messages, extra] : messages, questionSet, false, input.model, onText, predict);
    return ask(1536).catch((e) => {
      if (!(e instanceof AiProviderError) || e.kind !== 'invalid_output') throw e;
      return ask(1024, { role: 'user', content: 'Предыдущий ответ оборвался. Верни JSON с одним-тремя questions. text и rationale по-русски, evidence из сданных файлов.' });
    });
  }

  evaluateInterview(input: InterviewInput) {
    return this.chat(buildInterviewMessages(input), interviewEvaluation);
  }

  suggestTests(input: TaskSuggestionInput, onText?: (text: string) => void) {
    return this.chat(buildTaskSuggestionMessages(input), taskSuggestionSet, false, undefined, onText, 2048);
  }

  assessProcess(input: ProcessInput, onText?: (text: string) => void) {
    return this.chat(buildProcessMessages(input), processReview, false, undefined, onText, 2048);
  }

  async reviewMaterials(input: MaterialsInput, onText?: (text: string) => void) {
    const messages = buildMaterialsMessages(input);
    try {
      return await this.chatInRussian(messages, materialsReview, input.model, onText, 2048);
    } catch (e) {
      if (!(e instanceof AiProviderError) || e.kind !== 'invalid_output') throw e;
      return this.chatInRussian(
        [...messages, { role: 'user', content: 'Предыдущий ответ оборвался. Верни один короткий JSON без текста вокруг: summary — 4 предложения, description — 2 предложения.' }],
        materialsReview,
        input.model,
        onText,
        1024,
      );
    }
  }

  async suggestImprovements(input: MaterialsInput, onText?: (text: string) => void) {
    const messages = buildImprovementMessages(input);
    try {
      return await this.chatInRussian(messages, improvementSet, input.model, onText, 2048);
    } catch (e) {
      if (!(e instanceof AiProviderError) || e.kind !== 'invalid_output') throw e;
      return this.chatInRussian(
        [...messages, { role: 'user', content: 'Предыдущий ответ оборвался. Верни короткий JSON: summary и от одного до трёх items с title и text.' }],
        improvementSet,
        input.model,
        onText,
        1024,
      );
    }
  }
}

type LooseIssue = { path?: PropertyKey[]; keys?: unknown; message?: string };

function unrecognizedKeys(issue: LooseIssue): string[] {
  if (Array.isArray(issue.keys)) return issue.keys.filter((key): key is string => typeof key === 'string');
  const match = /Unrecognized key(?:s)?: ["']([^"']+)["']/.exec(issue.message ?? '');
  return match?.[1] ? [match[1]] : [];
}

function stripKeys(root: unknown, path: PropertyKey[] | undefined, keys: string[]): boolean {
  let node: unknown = root;
  for (const seg of path ?? []) {
    if (node == null || typeof node !== 'object') return false;
    node = (node as Record<PropertyKey, unknown>)[seg];
  }
  if (!node || typeof node !== 'object' || Array.isArray(node)) return false;
  const rec = node as Record<string, unknown>;
  let changed = false;
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(rec, key)) {
      delete rec[key];
      changed = true;
    }
  }
  return changed;
}

/** DeepSeek sometimes echoes a JSON Schema or adds a type field next to the real object. */
function unwrapSchemaEcho(value: unknown): unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
  const obj = value as Record<string, unknown>;
  const props = obj.properties;
  if (!props || typeof props !== 'object' || Array.isArray(props)) return value;
  if (!('type' in obj) && !('required' in obj)) return value;
  const inner = props as Record<string, unknown>;
  if ('summary' in inner || 'description' in inner || 'items' in inner || 'questions' in inner || 'findings' in inner) return props;
  return value;
}

/** Drops unknown keys the model added, then validates. Strict schemas stay strict for real fields. */
export function acceptModelJson<T>(schema: ZodType<T>, parsed: unknown): { ok: true; data: T } | { ok: false; message: string } {
  let value = unwrapSchemaEcho(parsed);
  let message = 'model output violates schema';
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const result = schema.safeParse(value);
    if (result.success) return { ok: true, data: result.data };
    message = result.error.issues[0]?.message ?? message;
    if (value == null || typeof value !== 'object') break;
    const clone = structuredClone(value);
    let changed = false;
    for (const issue of result.error.issues as LooseIssue[]) {
      const keys = unrecognizedKeys(issue);
      if (keys.length && stripKeys(clone, issue.path, keys)) changed = true;
    }
    if (!changed) break;
    value = unwrapSchemaEcho(clone);
  }
  return { ok: false, message };
}

/** Pulls a JSON object out of a model reply, including fenced or cut-off text. */
export function parseModelJson(text: string): unknown {
  const start = text.indexOf('{');
  if (start < 0) throw new Error('no object');
  const slice = text.slice(start);
  const end = slice.lastIndexOf('}');
  if (end > 0) {
    try {
      return JSON.parse(slice.slice(0, end + 1));
    } catch {
      /* the closing brace may belong to a nested fragment of a cut-off object */
    }
  }
  return JSON.parse(repairTruncatedJson(slice));
}

function repairTruncatedJson(input: string): string {
  let s = input.trim().replace(/,\s*$/, '');
  let inStr = false;
  let esc = false;
  for (const ch of s) {
    if (inStr) {
      if (esc) esc = false;
      else if (ch === '\\') esc = true;
      else if (ch === '"') inStr = false;
    } else if (ch === '"') inStr = true;
  }
  if (inStr) s += '"';
  s = s.replace(/,\s*$/, '');
  const braces = (s.match(/\{/g)?.length ?? 0) - (s.match(/\}/g)?.length ?? 0);
  const brackets = (s.match(/\[/g)?.length ?? 0) - (s.match(/\]/g)?.length ?? 0);
  if (brackets > 0) s += ']'.repeat(brackets);
  if (braces > 0) s += '}'.repeat(braces);
  return s;
}

async function readOllamaStream(res: Response, onText: (text: string) => void): Promise<string> {
  const reader = res.body?.getReader();
  if (!reader) throw new AiProviderError('ollama response missing message content', 'invalid_output');
  const decoder = new TextDecoder();
  let pending = '';
  let content = '';
  const take = (line: string): boolean => {
    if (!line.trim()) return false;
    const msg = JSON.parse(line) as { message?: { content?: string } };
    if (typeof msg.message?.content === 'string' && msg.message.content) {
      content += msg.message.content;
      onText(content);
      if (finishedJson(content)) return true;
    }
    return false;
  };
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    pending += decoder.decode(value, { stream: true });
    const lines = pending.split('\n');
    pending = lines.pop() ?? '';
    let finished = false;
    for (const line of lines) {
      if (take(line)) {
        finished = true;
        break;
      }
    }
    if (finished) {
      await reader.cancel().catch(() => undefined);
      return content;
    }
  }
  if (pending.trim()) take(pending);
  return content;
}

function finishedJson(text: string): boolean {
  const start = text.indexOf('{');
  if (start < 0) return false;
  try {
    const value = JSON.parse(text.slice(start)) as unknown;
    return Boolean(value && typeof value === 'object' && !Array.isArray(value));
  } catch {
    return false;
  }
}

function collectText(value: unknown): string[] {
  if (typeof value === 'string') return [value];
  if (Array.isArray(value)) return value.flatMap(collectText);
  if (value && typeof value === 'object') return Object.values(value).flatMap(collectText);
  return [];
}

/** True when each sentence-sized field contains a Russian sentence. Paths may stay in Latin. */
function isRussianText(value: unknown): boolean {
  return collectText(value).every((text) => {
    const cyr = text.match(/\p{Script=Cyrillic}/gu)?.length ?? 0;
    const lat = text.match(/\p{Script=Latin}/gu)?.length ?? 0;
    if (cyr + lat < 12) return true;
    return cyr >= 12;
  });
}
