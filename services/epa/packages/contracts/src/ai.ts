import { z } from 'zod';

export const AI_CONTRACT_VERSION = 'ai-output-v1';

const lineNo = z.number().int().min(1).max(1_000_000);

export const evidenceRef = z.strictObject({
  file: z.string().min(1).max(512),
  lineStart: lineNo,
  lineEnd: lineNo,
  quote: z.string().max(500).optional(),
});
export type EvidenceRefOutput = z.infer<typeof evidenceRef>;

export const FINDING_CATEGORIES = ['code_quality', 'architecture', 'security', 'debugging', 'performance', 'tech_knowledge'] as const;

export const finding = z.strictObject({
  category: z.enum(FINDING_CATEGORIES),
  severity: z.enum(['info', 'low', 'medium', 'high', 'critical']),
  title: z.string().min(3).max(200),
  explanation: z.string().min(10).max(2000),
  recommendation: z.string().min(5).max(2000),
  evidence: evidenceRef,
});
export type Finding = z.infer<typeof finding>;

export const authorshipSignal = z.strictObject({
  label: z.enum(['mostly_typed', 'mixed', 'mostly_pasted', 'insufficient_data']),
  summary: z.string().max(2000),
});
export type AuthorshipSignal = z.infer<typeof authorshipSignal>;

export const analysisResult = z.strictObject({
  summary: z.string().max(3000),
  findings: z.array(finding).max(30),
  strengths: z.array(z.strictObject({ text: z.string().max(500), evidence: evidenceRef })).max(10),
  authorship: authorshipSignal.optional(),
});
export type AnalysisResultOutput = z.infer<typeof analysisResult>;

export const interviewQuestionOut = z.strictObject({
  text: z.string().min(10).max(1000),
  rationale: z.string().max(1000),
  evidence: evidenceRef,
});
export const questionSet = z.strictObject({ questions: z.array(interviewQuestionOut).min(1).max(10) });
export type QuestionSetOutput = z.infer<typeof questionSet>;

export const taskSuggestion = z.strictObject({
  title: z.string().min(3).max(200),
  goal: z.string().min(10).max(2000),
  scenario: z.string().min(10).max(2000),
  evidence: evidenceRef,
});
export const taskSuggestionSet = z.strictObject({
  summary: z.string().max(3000),
  tests: z.array(taskSuggestion).min(1).max(8),
});
export type TaskSuggestionSet = z.infer<typeof taskSuggestionSet>;

export const processReview = z.strictObject({
  label: authorshipSignal.shape.label,
  aiSignal: z.enum(['no_sign', 'possible_external', 'insufficient_data']),
  summary: z.string().max(3000),
});
export type ProcessReview = z.infer<typeof processReview>;

export const materialsReview = z.strictObject({
  summary: z.string().max(3000).describe('Краткий разбор проекта и ТЗ на русском языке'),
  description: z.string().min(20).max(8000).describe('Описание задания для кандидата на русском языке'),
});
export type MaterialsReview = z.infer<typeof materialsReview>;

export const improvementSet = z.strictObject({
  summary: z.string().max(3000).describe('Краткое резюме рекомендаций на русском языке'),
  items: z
    .array(
      z.strictObject({
        title: z.string().min(3).max(200).describe('Заголовок рекомендации на русском языке'),
        text: z.string().min(10).max(2000).describe('Текст рекомендации на русском языке'),
      }),
    )
    .min(1)
    .max(8),
});
export type ImprovementSet = z.infer<typeof improvementSet>;

export const interviewEvaluation = z.strictObject({
  understanding: z.enum(['insufficient', 'partial', 'good', 'strong']),
  score: z.number().int().min(0).max(100),
  rationale: z.string().max(2000),
  followUp: interviewQuestionOut.nullable(),
});
export type InterviewEvaluationOutput = z.infer<typeof interviewEvaluation>;
