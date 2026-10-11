import type { ZodType } from 'zod';
import { analysisResult, improvementSet, interviewEvaluation, materialsReview, processReview, questionSet, taskSuggestionSet } from '@epa/contracts';
import { buildAnalysisMessages, buildImprovementMessages, buildInterviewMessages, buildMaterialsMessages, buildProcessMessages, buildQuestionMessages, buildTaskSuggestionMessages, type ChatMessage } from './prompts.js';
import { AiProviderError, PROMPT_TEMPLATE_VERSION, type AnalysisInput, type CodeAnalysisProvider, type InterviewInput, type MaterialsInput, type ProcessInput, type QuestionInput, type TaskSuggestionInput } from './types.js';
import { acceptModelJson, parseModelJson } from './ollama.js';

export interface DeepSeekOptions {
  baseUrl: string;
  apiKey: () => string;
  model?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

function deepseekDown(e: { message?: string } | null | undefined): string {
  const detail = e?.message ? `: ${e.message}` : '';
  return `Не удалось связаться с DeepSeek${detail}. Проверьте ключ и повторите разбор.`;
}

function isTimeout(e: { name?: string; message?: string } | null | undefined): boolean {
  return e?.name === 'TimeoutError' || e?.name === 'AbortError' || /aborted due to timeout/i.test(String(e?.message ?? ''));
}

function collectText(value: unknown): string[] {
  if (typeof value === 'string') return [value];
  if (Array.isArray(value)) return value.flatMap(collectText);
  if (value && typeof value === 'object') return Object.values(value).flatMap(collectText);
  return [];
}

function isRussianText(value: unknown): boolean {
  return collectText(value).every((text) => {
    const cyr = text.match(/\p{Script=Cyrillic}/gu)?.length ?? 0;
    const lat = text.match(/\p{Script=Latin}/gu)?.length ?? 0;
    if (cyr + lat < 12) return true;
    return cyr >= 12;
  });
}

/** OpenAI-compatible DeepSeek adapter. The employer setup model name is ignored unless it is a DeepSeek model. */
export class DeepSeekProvider implements CodeAnalysisProvider {
  readonly meta: { providerId: string; modelId: string; templateVersion: string };
  private readonly fetchImpl: typeof fetch;

  constructor(private readonly opts: DeepSeekOptions) {
    this.meta = { providerId: 'deepseek', modelId: opts.model ?? 'deepseek-chat', templateVersion: PROMPT_TEMPLATE_VERSION };
    this.fetchImpl = opts.fetchImpl ?? fetch;
  }

  private base() {
    return this.opts.baseUrl.replace(/\/$/, '').replace(/\/v1$/, '');
  }

  private modelName(override?: string) {
    const wanted = override || this.meta.modelId;
    return wanted.startsWith('deepseek') ? wanted : this.meta.modelId;
  }

  private async chatInRussian<T>(messages: ChatMessage[], schema: ZodType<T>, model?: string, onText?: (text: string) => void, predict?: number): Promise<T> {
    const first = await this.chat(messages, schema, model, onText, predict);
    if (isRussianText(first)) return first;
    return this.chat(
      [
        ...messages,
        {
          role: 'user',
          content: 'Предыдущий ответ был не на русском. Повтори тот же JSON. Поля summary, description, title и text напиши только по-русски. Латиница допустима для путей и имён из проекта.',
        },
      ],
      schema,
      model,
      onText,
      predict,
    );
  }

  private async chat<T>(messages: ChatMessage[], schema: ZodType<T>, modelOverride?: string, onText?: (text: string) => void, predict?: number): Promise<T> {
    const key = this.opts.apiKey().trim();
    if (!key) throw new AiProviderError('Укажите API-ключ DeepSeek в блоке «Модель разбора».', 'unavailable');
    const model = this.modelName(modelOverride);
    const timeoutMs = this.opts.timeoutMs ?? 180_000;
    const timedOut = new AiProviderError('DeepSeek не успел ответить. Нажмите «Повторить разбор».', 'timeout');
    let res: Response;
    try {
      res = await this.fetchImpl(`${this.base()}/chat/completions`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${key}` },
        body: JSON.stringify({
          model,
          messages,
          temperature: 0,
          response_format: { type: 'json_object' },
          ...(predict ? { max_tokens: predict } : {}),
        }),
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (e: any) {
      if (isTimeout(e)) throw timedOut;
      throw new AiProviderError(deepseekDown(e), 'unavailable');
    }
    if (!res.ok) {
      const detail = (await res.text().catch(() => '')).slice(0, 300);
      if (res.status === 401) throw new AiProviderError('DeepSeek отклонил API-ключ. Проверьте ключ и сохраните его снова.', 'http_error');
      if (res.status === 402) throw new AiProviderError('На ключе DeepSeek закончился баланс.', 'http_error');
      if (res.status === 429) throw new AiProviderError('DeepSeek ограничил частоту запросов. Повторите разбор чуть позже.', 'http_error');
      throw new AiProviderError(`DeepSeek вернул HTTP ${res.status}${detail ? `: ${detail}` : ''}`, 'http_error');
    }
    const body = (await res.json().catch(() => null)) as { choices?: { message?: { content?: string } }[] } | null;
    const content = body?.choices?.[0]?.message?.content;
    if (typeof content !== 'string') throw new AiProviderError('DeepSeek не вернул текст ответа', 'invalid_output');
    if (onText) onText(content);
    let parsed: unknown;
    try {
      parsed = parseModelJson(content);
    } catch {
      throw new AiProviderError('model output is not valid JSON', 'invalid_output');
    }
    const fitted = acceptModelJson(schema, parsed);
    if (!fitted.ok) throw new AiProviderError(`model output violates schema: ${fitted.message}`, 'invalid_output');
    return fitted.data;
  }

  analyzeCode(input: AnalysisInput, onText?: (text: string) => void) {
    const messages = buildAnalysisMessages(input);
    const ask = (predict: number, extra?: ChatMessage) => this.chat(extra ? [...messages, extra] : messages, analysisResult, input.model, onText, predict);
    return ask(3072).catch((e) => {
      if (!(e instanceof AiProviderError) || e.kind !== 'invalid_output') throw e;
      return ask(1536, { role: 'user', content: 'Предыдущий ответ оборвался. Верни короткий JSON: summary на русском, findings и strengths можно пустыми массивами, authorship с label и summary.' });
    });
  }

  generateQuestions(input: QuestionInput, onText?: (text: string) => void) {
    const messages = buildQuestionMessages(input);
    const ask = (predict: number, extra?: ChatMessage) => this.chat(extra ? [...messages, extra] : messages, questionSet, input.model, onText, predict);
    return ask(1536).catch((e) => {
      if (!(e instanceof AiProviderError) || e.kind !== 'invalid_output') throw e;
      return ask(1024, { role: 'user', content: 'Предыдущий ответ оборвался. Верни JSON с одним-тремя questions. text и rationale по-русски, evidence из сданных файлов.' });
    });
  }

  evaluateInterview(input: InterviewInput) {
    return this.chat(buildInterviewMessages(input), interviewEvaluation);
  }

  suggestTests(input: TaskSuggestionInput, onText?: (text: string) => void) {
    return this.chat(buildTaskSuggestionMessages(input), taskSuggestionSet, undefined, onText, 2048);
  }

  assessProcess(input: ProcessInput, onText?: (text: string) => void) {
    return this.chat(buildProcessMessages(input), processReview, undefined, onText, 2048);
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
