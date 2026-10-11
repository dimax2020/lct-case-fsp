import { DomainError } from './errors.js';

export const DIMENSIONS = [
  'code_quality',
  'architecture',
  'tech_knowledge',
  'security',
  'debugging',
  'response_to_review',
  'explanation',
  'adaptability',
] as const;
export type Dimension = (typeof DIMENSIONS)[number];

export const RUBRIC_VERSION = 'rubric-v1';

/**
 * Aggregation scheme rubric-v1 (documented in docs/architecture/assessment.md):
 * overall = round( sum(w_d * s_d) / sum(w_d) ) over dimensions that have a score.
 * Dimensions without evidence are excluded and listed as `missing`; their weight is
 * not redistributed implicitly but reported via `coverage`.
 */
export const RUBRIC_WEIGHTS: Readonly<Record<Dimension, number>> = {
  code_quality: 15,
  architecture: 15,
  tech_knowledge: 10,
  security: 10,
  debugging: 10,
  response_to_review: 15,
  explanation: 15,
  adaptability: 10,
};

export interface EvidenceRef {
  kind: 'test_run' | 'submission' | 'commit' | 'snapshot' | 'finding' | 'review_comment' | 'interview_answer' | 'requirement_change' | 'timeline_event';
  id: string;
  file?: string;
  lineStart?: number;
  lineEnd?: number;
}

export interface DimensionScore {
  dimension: Dimension;
  score: number | null;
  rationale: string;
  evidence: EvidenceRef[];
  aiDerived: boolean;
}

export interface AggregatedScore {
  rubricVersion: string;
  overall: number | null;
  coverage: number;
  missing: Dimension[];
  formula: string;
  weights: Record<Dimension, number>;
}

export function assertValidDimensionScore(d: DimensionScore): void {
  if (!DIMENSIONS.includes(d.dimension)) {
    throw new DomainError('VALIDATION', `unknown dimension ${d.dimension}`);
  }
  if (d.score !== null) {
    if (!Number.isFinite(d.score) || d.score < 0 || d.score > 100) {
      throw new DomainError('VALIDATION', `score for ${d.dimension} must be within 0..100`);
    }
    if (!Number.isInteger(d.score)) throw new DomainError('VALIDATION', 'scores must be integers');
  }
  if (d.rationale.trim().length > 0 && d.score !== null && d.evidence.length === 0) {
    throw new DomainError('VALIDATION', `score rationale for ${d.dimension} requires evidence references`);
  }
}

export function aggregate(scores: DimensionScore[], rubricVersion = RUBRIC_VERSION): AggregatedScore {
  if (rubricVersion !== RUBRIC_VERSION) {
    throw new DomainError('VALIDATION', `unsupported rubric version ${rubricVersion}`);
  }
  const byDim = new Map<Dimension, DimensionScore>();
  for (const s of scores) {
    assertValidDimensionScore(s);
    if (byDim.has(s.dimension)) throw new DomainError('VALIDATION', `duplicate dimension ${s.dimension}`);
    byDim.set(s.dimension, s);
  }
  let weighted = 0;
  let weightSum = 0;
  const missing: Dimension[] = [];
  const totalWeight = DIMENSIONS.reduce((acc, d) => acc + RUBRIC_WEIGHTS[d], 0);
  for (const d of DIMENSIONS) {
    const s = byDim.get(d);
    if (!s || s.score === null) {
      missing.push(d);
      continue;
    }
    weighted += RUBRIC_WEIGHTS[d] * s.score;
    weightSum += RUBRIC_WEIGHTS[d];
  }
  return {
    rubricVersion,
    overall: weightSum === 0 ? null : Math.round(weighted / weightSum),
    coverage: Math.round((weightSum / totalWeight) * 100) / 100,
    missing,
    formula: 'round(sum(weight_d * score_d) / sum(weight_d)) over scored dimensions',
    weights: { ...RUBRIC_WEIGHTS },
  };
}

export const clampScore = (n: number): number => Math.max(0, Math.min(100, Math.round(n)));
