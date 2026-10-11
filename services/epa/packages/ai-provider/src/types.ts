import type { AnalysisResultOutput, ImprovementSet, InterviewEvaluationOutput, MaterialsReview, ProcessReview, QuestionSetOutput, TaskSuggestionSet } from '@epa/contracts';

export const PROMPT_TEMPLATE_VERSION = 'prompt-v1';
export const AI_POLICY_VERSION = 'ai-policy-v1';

export interface ContextFile {
  path: string;
  content: string;
  lineCount: number;
  sha256: string;
}

export interface AnalysisInput {
  files: ContextFile[];
  tests: { status: string; passed: number; failed: number; failedTests: string[] } | null;
  timeline: {
    eventCounts: Record<string, number>;
    largeInsertionSignals: number;
    commits: number;
    pastedChars?: number;
    copiedChars?: number;
    externalPastes?: number;
    workspacePastes?: number;
    insertedChars?: number;
  };
  reviewComments: { filePath: string; lineStart: number; lineEnd: number; body: string; status: string }[];
  requirementChanges: { text: string; acceptanceCriteria: string[] }[];
  taskDescription: string;
  /** Smaller local model. The default 30B model drops the connection on a full submission. */
  model?: string;
}

export interface QuestionInput {
  files: ContextFile[];
  findings: AnalysisResultOutput['findings'];
  requirementChanges: { text: string; acceptanceCriteria: string[] }[];
  maxQuestions: number;
  pasteFiles?: string[];
  model?: string;
}

export interface TaskSuggestionInput {
  files: ContextFile[];
  taskDescription: string;
  brief: string;
}

export interface MaterialsInput {
  title: string;
  files: ContextFile[];
  brief: string;
  notes: string;
  /** Model used only for the employer setup review. */
  model: string;
}

export interface ProcessInput {
  taskDescription: string;
  pastedChars: number;
  copiedChars: number;
  externalPastes: number;
  workspacePastes: number;
  insertedChars: number;
  largeInsertionSignals: number;
  commits: number;
  modules: { module: string; activeMinutes: number; insertedChars: number; pastedChars: number; externalPastes: number; largeInsertions: number }[];
}

export interface InterviewInput {
  question: { text: string; evidence: { file: string; lineStart: number; lineEnd: number } };
  answer: string;
  codeExcerpt: ContextFile;
  depth: number;
  allowFollowUp: boolean;
}

export interface ProviderMeta {
  providerId: string;
  modelId: string;
  templateVersion: string;
}

/** Domain-level AI port. The orchestrator, UI and assessment never depend on a vendor SDK. */
export interface CodeAnalysisProvider {
  readonly meta: ProviderMeta;
  analyzeCode(input: AnalysisInput, onText?: (text: string) => void): Promise<AnalysisResultOutput>;
  generateQuestions(input: QuestionInput, onText?: (text: string) => void): Promise<QuestionSetOutput>;
  evaluateInterview(input: InterviewInput): Promise<InterviewEvaluationOutput>;
  suggestTests(input: TaskSuggestionInput, onText?: (text: string) => void): Promise<TaskSuggestionSet>;
  assessProcess(input: ProcessInput, onText?: (text: string) => void): Promise<ProcessReview>;
  reviewMaterials(input: MaterialsInput, onText?: (text: string) => void): Promise<MaterialsReview>;
  suggestImprovements(input: MaterialsInput, onText?: (text: string) => void): Promise<ImprovementSet>;
}

export class AiProviderError extends Error {
  constructor(
    message: string,
    readonly kind: 'timeout' | 'unavailable' | 'invalid_output' | 'http_error',
  ) {
    super(message);
    this.name = 'AiProviderError';
  }
}
