import { describe, expect, it } from 'vitest';
import { DIMENSIONS, aggregate } from '@epa/domain';
import { scoreDimensions, type Facts } from '@epa/assessment';

const run = (id: string, submission_id: string, passed: number, failed: number) => ({ id, submission_id, status: failed ? 'FAILED' : 'PASSED', summary: { tests: passed + failed, passed, failed } });

const facts: Facts = {
  analysisId: 'ai_1',
  submissions: [
    { id: 'sub_1', version: 1, requirement_change_id: null, snapshot_id: 'snap_1' },
    { id: 'sub_2', version: 2, requirement_change_id: 'rc_1', snapshot_id: 'snap_2' },
  ],
  runs: [run('tr_1', 'sub_1', 3, 1), run('tr_2', 'sub_2', 4, 0)],
  findings: [
    { analysisId: 'ai_1', index: 0, category: 'security', severity: 'high', title: 't', evidence: { file: 'src/a.js', lineStart: 1, lineEnd: 2 } },
    { analysisId: 'ai_1', index: 1, category: 'code_quality', severity: 'low', title: 't', evidence: { file: 'src/a.js', lineStart: 3, lineEnd: 3 } },
  ],
  comments: [{ id: 'cmt_1', status: 'RESOLVED', submission_id: 'sub_1' }],
  changes: [{ id: 'rc_1', revised_submission_id: 'sub_2' }],
  answers: [{ id: 'ans_1', question_id: 'q_1', submission_id: 'sub_2', evaluation: { score: 80 } }],
};

describe('assessment scoring (rubric-v1)', () => {
  it('scores all eight dimensions within 0..100 with mandatory evidence', () => {
    const dims = scoreDimensions(facts);
    expect(dims.map((d) => d.dimension)).toEqual([...DIMENSIONS]);
    for (const d of dims) {
      expect(d.score).not.toBeNull();
      expect(d.score!).toBeGreaterThanOrEqual(0);
      expect(d.score!).toBeLessThanOrEqual(100);
      expect(d.evidence.length).toBeGreaterThan(0);
    }
    expect(dims.find((d) => d.dimension === 'security')!.score).toBe(80);
    expect(dims.find((d) => d.dimension === 'code_quality')!.score).toBe(95);
    expect(dims.find((d) => d.dimension === 'response_to_review')!.score).toBe(100);
    expect(dims.find((d) => d.dimension === 'explanation')).toMatchObject({ score: 80, aiDerived: true });
  });

  it('is deterministic for the same facts and rubric version', () => {
    expect(aggregate(scoreDimensions(facts))).toEqual(aggregate(scoreDimensions(structuredClone(facts))));
  });

  it('leaves dimensions null (not zero) without evidence', () => {
    const dims = scoreDimensions({ ...facts, analysisId: null, findings: [], comments: [], changes: [], answers: [] });
    for (const d of ['code_quality', 'architecture', 'security', 'response_to_review', 'explanation', 'adaptability']) {
      expect(dims.find((x) => x.dimension === d)!.score).toBeNull();
    }
    expect(dims.find((x) => x.dimension === 'tech_knowledge')!.score).not.toBeNull();
  });
});
