import type { AnalysisResultOutput, ImprovementSet, InterviewEvaluationOutput, MaterialsReview, ProcessReview, QuestionSetOutput, TaskSuggestionSet } from '@epa/contracts';
import { AiProviderError, PROMPT_TEMPLATE_VERSION, buildAnalysisMessages, type AnalysisInput, type CodeAnalysisProvider, type ContextFile, type InterviewInput, type MaterialsInput, type ProcessInput, type QuestionInput, type TaskSuggestionInput } from '@epa/ai-provider';

export type MockMode = 'grounded' | 'down' | 'hallucinate';

function firstFunction(f: ContextFile): { name: string; line: number } {
  const lines = f.content.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const m = /function\s+([A-Za-z0-9_]+)/.exec(lines[i]);
    if (m) return { name: m[1], line: i + 1 };
  }
  return { name: 'module', line: 1 };
}

/**
 * Deterministic provider for tests. In `grounded` mode it only cites real files/lines from the
 * input; `hallucinate` additionally returns ungrounded items (Redis, missing files) that the
 * orchestrator must reject; `down` simulates an unavailable model.
 */
export class MockCodeAnalysisProvider implements CodeAnalysisProvider {
  readonly meta = { providerId: 'mock', modelId: 'mock-qwen3-coder-14b', templateVersion: PROMPT_TEMPLATE_VERSION };
  mode: MockMode = 'grounded';
  calls: { kind: string; input: unknown }[] = [];
  lastAnalysisMessages: ReturnType<typeof buildAnalysisMessages> | null = null;

  constructor(mode: MockMode = 'grounded') {
    this.mode = mode;
  }

  private guard(kind: string, input: unknown) {
    this.calls.push({ kind, input });
    if (this.mode === 'down') throw new AiProviderError('mock model unavailable', 'unavailable');
  }

  async analyzeCode(input: AnalysisInput): Promise<AnalysisResultOutput> {
    this.guard('analyze', input);
    this.lastAnalysisMessages = buildAnalysisMessages(input, 'testnonce');
    const src = input.files.filter((f) => f.path.startsWith('src/'));
    const target = src[0] ?? input.files[0];
    const fn = firstFunction(target);
    const findings: AnalysisResultOutput['findings'] = [
      {
        category: 'code_quality',
        severity: 'low',
        title: `Document ${fn.name}`,
        explanation: `${fn.name} in ${target.path} has no description of its contract.`,
        recommendation: 'Add a short JSDoc comment describing inputs and outputs.',
        evidence: { file: target.path, lineStart: fn.line, lineEnd: fn.line },
      },
    ];
    if (this.mode === 'hallucinate') {
      findings.push(
        {
          category: 'architecture',
          severity: 'high',
          title: 'Redis cache is misconfigured',
          explanation: 'The Redis client is created without a connection pool, which will exhaust sockets.',
          recommendation: 'Configure a Redis connection pool.',
          evidence: { file: target.path, lineStart: 1, lineEnd: 1 },
        },
        {
          category: 'security',
          severity: 'critical',
          title: 'Hardcoded key in config file',
          explanation: 'The config file contains a hardcoded signing key used everywhere.',
          recommendation: 'Move it to a secret store.',
          evidence: { file: 'src/config/keys.js', lineStart: 3, lineEnd: 4 },
        },
      );
    }
    const external = input.timeline.externalPastes ?? 0;
    return {
      summary: this.mode === 'hallucinate' ? 'Uses Redis for sessions.' : `Reviewed ${input.files.length} files.`,
      findings,
      strengths: [{ text: `Small focused module ${target.path}`, evidence: { file: target.path, lineStart: 1, lineEnd: Math.min(2, target.lineCount) } }],
      authorship: {
        label: external > 0 ? 'mostly_pasted' : 'insufficient_data',
        summary: external > 0 ? `External pastes: ${external}.` : 'Not enough editing to classify.',
      },
    };
  }

  async suggestTests(input: TaskSuggestionInput): Promise<TaskSuggestionSet> {
    this.guard('suggest', input);
    const target = input.files[0];
    return {
      summary: `Tests for ${target?.path ?? 'the task'}.`,
      tests: [
        {
          title: `Cover ${target?.path ?? 'the task'}`,
          goal: 'Check the main behaviour described in the task.',
          scenario: 'Run the program on the sample input and compare the expected counts.',
          evidence: { file: target?.path ?? 'ЗАДАНИЕ.md', lineStart: 1, lineEnd: 1 },
        },
      ],
    };
  }

  async reviewMaterials(input: MaterialsInput): Promise<MaterialsReview> {
    this.guard('materials', input);
    const target = input.files[0];
    return {
      summary: this.mode === 'hallucinate' ? 'Uses Redis for the assignment.' : `Проект «${input.title}» содержит ${input.files.length} файлов.`,
      description:
        this.mode === 'hallucinate'
          ? 'Store sessions in Redis and keep the current behaviour of the uploaded project.'
          : `Сделайте задание по файлу ${target?.path ?? 'ТЗ.md'}: сохраните текущее поведение и добавьте проверку.`,
    };
  }

  async suggestImprovements(input: MaterialsInput): Promise<ImprovementSet> {
    this.guard('improvements', input);
    return {
      summary: this.mode === 'hallucinate' ? 'Add Redis.' : 'Что уточнить в задании до старта кандидата.',
      items: [
        this.mode === 'hallucinate'
          ? { title: 'Add Redis', text: 'Cache the project results in Redis before the candidate starts.' }
          : { title: 'Уточнить критерий', text: 'Добавьте в ТЗ пример входа и ожидаемый результат.' },
      ],
    };
  }

  async assessProcess(input: ProcessInput): Promise<ProcessReview> {
    this.guard('process', input);
    const typed = Math.max(0, input.insertedChars - input.pastedChars);
    const label = input.insertedChars < 40 && input.externalPastes === 0 ? 'insufficient_data' : input.pastedChars > typed ? 'mostly_pasted' : input.pastedChars > 0 ? 'mixed' : 'mostly_typed';
    const aiSignal = input.insertedChars < 40 && input.externalPastes === 0 ? 'insufficient_data' : input.externalPastes > 0 || input.largeInsertionSignals > 0 ? 'possible_external' : 'no_sign';
    const modules = input.modules.map((m) => `${m.module}: ${m.activeMinutes} мин`).join(', ') || 'модулей нет';
    return { label, aiSignal, summary: `По телеметрии: набрано около ${typed}, вставлено ${input.pastedChars}, внешних вставок ${input.externalPastes}. Модули: ${modules}.` };
  }

  async generateQuestions(input: QuestionInput): Promise<QuestionSetOutput> {
    this.guard('questions', input);
    const src = input.files.filter((f) => f.path.startsWith('src/'));
    const questions: QuestionSetOutput['questions'] = src.slice(0, input.maxQuestions).map((f) => {
      const fn = firstFunction(f);
      return {
        text: `Walk me through ${fn.name} in ${f.path}: what happens on invalid input?`,
        rationale: 'Checks understanding of own code.',
        evidence: { file: f.path, lineStart: fn.line, lineEnd: Math.min(fn.line + 2, f.lineCount) },
      };
    });
    if (this.mode === 'hallucinate') {
      questions.push({ text: 'How do you invalidate the Redis session cache on logout?', rationale: 'caching', evidence: { file: src[0].path, lineStart: 1, lineEnd: 1 } });
    }
    return { questions };
  }

  async evaluateInterview(input: InterviewInput): Promise<InterviewEvaluationOutput> {
    this.guard('evaluate', input);
    const words = input.answer.trim().split(/\s+/).length;
    const score = Math.min(95, 40 + words * 3);
    return {
      understanding: score >= 80 ? 'strong' : score >= 60 ? 'good' : 'partial',
      score,
      rationale: `Answer has ${words} words and refers to ${input.question.evidence.file}.`,
      followUp: input.allowFollowUp
        ? {
            text: `You said "${input.answer.slice(0, 40)}". Which line in ${input.codeExcerpt.path} enforces that?`,
            rationale: 'Follow-up tied to the answer.',
            evidence: { file: input.codeExcerpt.path, lineStart: 1, lineEnd: Math.min(3, input.codeExcerpt.lineCount) },
          }
        : null,
    };
  }
}
