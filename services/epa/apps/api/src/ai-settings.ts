import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { DeepSeekProvider, OllamaQwen3Coder14BProvider, type CodeAnalysisProvider } from '@epa/ai-provider';
import { DomainError } from '@epa/domain';

export const LOCAL_MODEL = 'qwen2.5-coder:0.5b';

export interface StoredAiSettings {
  provider: 'deepseek' | 'local';
  apiKey: string;
  deepseekModel: string;
  deepseekBaseUrl: string;
}

export interface PullState {
  running: boolean;
  percent: number | null;
  status: string;
  error: string;
  done: boolean;
}

class SwitchingAnalysisProvider implements CodeAnalysisProvider {
  constructor(private readonly current: () => CodeAnalysisProvider) {}
  get meta() {
    return this.current().meta;
  }
  analyzeCode(...args: Parameters<CodeAnalysisProvider['analyzeCode']>) {
    return this.current().analyzeCode(...args);
  }
  generateQuestions(...args: Parameters<CodeAnalysisProvider['generateQuestions']>) {
    return this.current().generateQuestions(...args);
  }
  evaluateInterview(...args: Parameters<CodeAnalysisProvider['evaluateInterview']>) {
    return this.current().evaluateInterview(...args);
  }
  suggestTests(...args: Parameters<CodeAnalysisProvider['suggestTests']>) {
    return this.current().suggestTests(...args);
  }
  assessProcess(...args: Parameters<CodeAnalysisProvider['assessProcess']>) {
    return this.current().assessProcess(...args);
  }
  reviewMaterials(...args: Parameters<CodeAnalysisProvider['reviewMaterials']>) {
    return this.current().reviewMaterials(...args);
  }
  suggestImprovements(...args: Parameters<CodeAnalysisProvider['suggestImprovements']>) {
    return this.current().suggestImprovements(...args);
  }
}

export class AiSettingsStore {
  readonly localModel = LOCAL_MODEL;
  pull: PullState = { running: false, percent: null, status: '', error: '', done: false };
  private settings: StoredAiSettings;
  private deepseek!: DeepSeekProvider;
  private ollama!: OllamaQwen3Coder14BProvider;
  private readonly switching = new SwitchingAnalysisProvider(() => this.active());
  private installedAt = 0;
  private installedValue = false;

  constructor(
    private readonly file: string,
    private readonly opts: { ollamaUrl: string; ollamaModel: string; timeoutMs: number },
  ) {
    this.settings = {
      provider: 'deepseek',
      apiKey: process.env.DEEPSEEK_API_KEY?.trim() ?? '',
      deepseekModel: process.env.DEEPSEEK_MODEL?.trim() || 'deepseek-chat',
      deepseekBaseUrl: process.env.DEEPSEEK_BASE_URL?.trim() || 'https://api.deepseek.com',
    };
  }

  provider(): CodeAnalysisProvider {
    return this.switching;
  }

  async load() {
    try {
      const raw = JSON.parse(await readFile(this.file, 'utf8')) as Partial<StoredAiSettings>;
      if (raw.provider === 'deepseek' || raw.provider === 'local') this.settings.provider = raw.provider;
      if (typeof raw.apiKey === 'string') this.settings.apiKey = raw.apiKey;
      if (typeof raw.deepseekModel === 'string' && raw.deepseekModel.startsWith('deepseek')) this.settings.deepseekModel = raw.deepseekModel;
      if (typeof raw.deepseekBaseUrl === 'string' && raw.deepseekBaseUrl.startsWith('http')) this.settings.deepseekBaseUrl = raw.deepseekBaseUrl;
    } catch {
      /* first run keeps the DeepSeek default */
    }
    this.deepseek = new DeepSeekProvider({
      baseUrl: this.settings.deepseekBaseUrl,
      model: this.settings.deepseekModel,
      apiKey: () => this.settings.apiKey,
      timeoutMs: this.opts.timeoutMs,
    });
    this.ollama = new OllamaQwen3Coder14BProvider({
      baseUrl: this.opts.ollamaUrl,
      model: this.opts.ollamaModel || LOCAL_MODEL,
      timeoutMs: this.opts.timeoutMs,
    });
  }

  async update(patch: { apiKey?: unknown; provider?: unknown }) {
    if (patch.provider === 'local') {
      if (!(await this.localInstalled())) throw new DomainError('VALIDATION', 'Сначала скачайте локальную модель');
      this.settings.provider = 'local';
    } else if (patch.provider === 'deepseek') {
      this.settings.provider = 'deepseek';
    } else if (patch.provider !== undefined) {
      throw new DomainError('VALIDATION', 'Неизвестный режим модели');
    }
    if (typeof patch.apiKey === 'string' && patch.apiKey.trim()) {
      this.settings.apiKey = patch.apiKey.trim();
      if (patch.provider !== 'local') this.settings.provider = 'deepseek';
    }
    await this.persist();
    return this.view();
  }

  startPull() {
    if (!this.pull.running) {
      this.pull = { running: true, percent: 0, status: 'Подключение к Ollama', error: '', done: false };
      void this.runPull();
    }
    return this.view();
  }

  async view() {
    const installed = await this.localInstalled();
    const key = this.settings.apiKey;
    return {
      provider: this.settings.provider,
      hasApiKey: key.length > 0,
      keyHint: key.length > 4 ? `••••${key.slice(-4)}` : key ? '••••' : '',
      model: this.settings.deepseekModel,
      localModel: this.localModel,
      localInstalled: installed,
      pull: this.pull,
    };
  }

  private active(): CodeAnalysisProvider {
    return this.settings.provider === 'local' ? this.ollama : this.deepseek;
  }

  private ollamaBase() {
    return (process.env.OLLAMA_URL ?? 'http://127.0.0.1:11434').replace(/\/$/, '');
  }

  private async localInstalled(): Promise<boolean> {
    if (Date.now() - this.installedAt < 5_000) return this.installedValue;
    try {
      const res = await fetch(`${this.ollamaBase()}/api/tags`, { signal: AbortSignal.timeout(1500) });
      if (!res.ok) this.installedValue = false;
      else {
        const body = (await res.json()) as { models?: { name?: string }[] };
        this.installedValue = (body.models ?? []).some((m) => {
          const name = m.name ?? '';
          return name === this.localModel || name.startsWith(`${this.localModel}:`);
        });
      }
    } catch {
      this.installedValue = false;
    }
    this.installedAt = Date.now();
    return this.installedValue;
  }

  private async persist() {
    await mkdir(path.dirname(this.file), { recursive: true });
    await writeFile(this.file, JSON.stringify({ ...this.settings }, null, 2));
  }

  private async runPull() {
    const model = this.localModel;
    try {
      const res = await fetch(`${this.ollamaBase()}/api/pull`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ name: model, stream: true }),
        signal: AbortSignal.timeout(30 * 60 * 1000),
      });
      if (!res.ok || !res.body) {
        this.pull = { running: false, percent: null, status: '', error: 'Ollama не ответила. Запустите Ollama и нажмите «Скачать» ещё раз.', done: false };
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let pending = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        pending += decoder.decode(value, { stream: true });
        const lines = pending.split('\n');
        pending = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.trim()) continue;
          const msg = JSON.parse(line) as { status?: string; error?: string; total?: number; completed?: number };
          if (msg.error) {
            this.pull = { running: false, percent: null, status: '', error: msg.error, done: false };
            return;
          }
          const percent = msg.total && msg.completed != null ? Math.min(99, Math.round((msg.completed / msg.total) * 100)) : this.pull.percent;
          this.pull = { running: true, percent, status: msg.status || 'Скачивание', error: '', done: false };
        }
      }
      this.installedAt = 0;
      this.pull = { running: false, percent: 100, status: 'Модель скачана', error: '', done: true };
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      const down = /ECONNREFUSED|fetch failed|ENOTFOUND|EHOSTUNREACH/i.test(message);
      this.pull = {
        running: false,
        percent: null,
        status: '',
        error: down ? 'Ollama не запущена. Установите её и нажмите «Скачать» ещё раз.' : message,
        done: false,
      };
    }
  }
}
