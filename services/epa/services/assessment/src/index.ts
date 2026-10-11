import { authorize, requireKind, type Principal } from '@epa/authz';
import {
  DIMENSIONS,
  DomainError,
  RUBRIC_VERSION,
  aggregate,
  assertValidDimensionScore,
  clampScore,
  notFound,
  type Dimension,
  type DimensionScore,
  type EvidenceRef,
} from '@epa/domain';
import { newId, type Ctx } from '@epa/platform';
import { scopeOf, type PracticeService } from '@epa/practice';
import type { TimelineService } from '@epa/timeline';
import type { GitService } from '@epa/git';

const SEVERITY_PENALTY: Record<string, number> = { info: 0, low: 5, medium: 10, high: 20, critical: 30 };

export interface Facts {
  analysisId: string | null;
  submissions: { id: string; version: number; requirement_change_id: string | null; snapshot_id: string }[];
  runs: { id: string; submission_id: string; status: string; summary: any }[];
  findings: { analysisId: string; index: number; category: string; severity: string; title: string; evidence: any }[];
  comments: { id: string; status: string; submission_id: string }[];
  changes: { id: string; revised_submission_id: string | null }[];
  answers: { id: string; question_id: string; submission_id: string; evaluation: any }[];
}

const passRate = (s: any) => (s && s.tests > 0 ? s.passed / s.tests : s && s.passed + s.failed > 0 ? s.passed / (s.passed + s.failed) : 0);

/**
 * rubric-v1 dimension formulas (see docs/architecture/assessment.md). Every non-null score carries
 * evidence references; dimensions without facts stay null ("insufficient evidence") instead of 0.
 */
export function scoreDimensions(f: Facts): DimensionScore[] {
  const latestRunBySubmission = new Map<string, Facts['runs'][number]>();
  for (const r of f.runs) latestRunBySubmission.set(r.submission_id, r);
  const finalSubmission = f.submissions[f.submissions.length - 1];
  const finalRun = finalSubmission ? latestRunBySubmission.get(finalSubmission.id) : undefined;
  const finalRunDone = finalRun && ['PASSED', 'FAILED', 'TIMED_OUT'].includes(finalRun.status);
  const runRef = (r?: { id: string }): EvidenceRef[] => (r ? [{ kind: 'test_run', id: r.id }] : []);
  const findingRefs = (cats: string[]) =>
    f.findings.filter((x) => cats.includes(x.category)).map<EvidenceRef>((x) => ({ kind: 'finding', id: `${x.analysisId}#${x.index}`, file: x.evidence.file, lineStart: x.evidence.lineStart, lineEnd: x.evidence.lineEnd }));
  const penalty = (cats: string[]) => f.findings.filter((x) => cats.includes(x.category)).reduce((n, x) => n + (SEVERITY_PENALTY[x.severity] ?? 0), 0);
  const out: DimensionScore[] = [];

  // code_quality / architecture / security: 100 minus severity penalties of evidence-backed findings
  // of the final submission's successful AI analysis. Without an analysis the dimension stays null.
  const findingDim = (dimension: Dimension, cats: string[]) => {
    const refs = findingRefs(cats);
    if (!finalSubmission || !f.analysisId) return out.push({ dimension, score: null, rationale: '', evidence: [], aiDerived: false });
    const p = penalty(cats);
    out.push({
      dimension,
      score: clampScore(100 - p),
      rationale: refs.length ? `100 minus severity penalties of ${refs.length} evidence-backed finding(s) (${p} points).` : 'The AI analysis of the final submission reported no evidence-backed findings in this category.',
      evidence: refs.length ? refs : [{ kind: 'submission', id: finalSubmission.id }],
      aiDerived: true,
    });
  };
  findingDim('code_quality', ['code_quality']);
  findingDim('architecture', ['architecture']);
  findingDim('security', ['security']);

  // tech_knowledge: 60% final test pass rate + 40% (100 - tech_knowledge finding penalties)
  if (finalRunDone) {
    const p = penalty(['tech_knowledge']);
    out.push({
      dimension: 'tech_knowledge',
      score: clampScore(60 * passRate(finalRun!.summary) + 0.4 * (100 - p)),
      rationale: `Final sandbox run: ${finalRun!.summary.passed}/${finalRun!.summary.tests} tests passed; tech-knowledge finding penalties ${p}.`,
      evidence: [...runRef(finalRun), ...findingRefs(['tech_knowledge'])],
      aiDerived: findingRefs(['tech_knowledge']).length > 0,
    });
  } else out.push({ dimension: 'tech_knowledge', score: null, rationale: '', evidence: [], aiDerived: false });

  // debugging: 50% final pass rate + 50% (100 - debugging/performance penalties); +improvement bonus across versions
  if (finalRunDone) {
    const first = latestRunBySubmission.get(f.submissions[0].id);
    const improvement = first && first !== finalRun ? Math.max(0, passRate(finalRun!.summary) - passRate(first.summary)) : 0;
    const p = penalty(['debugging', 'performance']);
    out.push({
      dimension: 'debugging',
      score: clampScore(50 * passRate(finalRun!.summary) + 0.5 * (100 - p) + 20 * improvement),
      rationale: `Final pass rate ${(passRate(finalRun!.summary) * 100).toFixed(0)}%, improvement across versions ${(improvement * 100).toFixed(0)} pp, debugging/performance penalties ${p}.`,
      evidence: [...runRef(first), ...(first !== finalRun ? runRef(finalRun) : []), ...findingRefs(['debugging', 'performance'])],
      aiDerived: findingRefs(['debugging', 'performance']).length > 0,
    });
  } else out.push({ dimension: 'debugging', score: null, rationale: '', evidence: [], aiDerived: false });

  // response_to_review: 60% resolved comment ratio + 40% revised submission test outcome
  if (f.comments.length > 0) {
    const resolved = f.comments.filter((c) => c.status === 'RESOLVED').length;
    const firstCommented = f.submissions.find((s) => f.comments.some((c) => c.submission_id === s.id));
    const revised = firstCommented ? f.submissions.find((s) => s.version > firstCommented.version) : undefined;
    const revisedRun = revised ? latestRunBySubmission.get(revised.id) : undefined;
    out.push({
      dimension: 'response_to_review',
      score: clampScore(60 * (resolved / f.comments.length) + (revisedRun ? 40 * passRate(revisedRun.summary) : 0)),
      rationale: `${resolved}/${f.comments.length} review comments resolved; ${revised ? `revised submission v${revised.version}` : 'no revised submission'}${revisedRun ? ` with ${revisedRun.summary?.passed ?? 0} passing tests` : ''}.`,
      evidence: [...f.comments.map<EvidenceRef>((c) => ({ kind: 'review_comment', id: c.id })), ...(revised ? [{ kind: 'submission' as const, id: revised.id }] : []), ...runRef(revisedRun)],
      aiDerived: false,
    });
  } else out.push({ dimension: 'response_to_review', score: null, rationale: '', evidence: [], aiDerived: false });

  // explanation: mean AI evaluation score of interview answers
  const evaluated = f.answers.filter((a) => a.evaluation && typeof a.evaluation.score === 'number');
  if (evaluated.length) {
    const mean = evaluated.reduce((n, a) => n + a.evaluation.score, 0) / evaluated.length;
    out.push({
      dimension: 'explanation',
      score: clampScore(mean),
      rationale: `Mean evaluation of ${evaluated.length} code-defense answer(s).`,
      evidence: evaluated.map((a) => ({ kind: 'interview_answer', id: a.id })),
      aiDerived: true,
    });
  } else out.push({ dimension: 'explanation', score: null, rationale: '', evidence: [], aiDerived: false });

  // adaptability: 70% pass rate of the revised submission for the requirement change + 30% answers on that version
  const change = f.changes.find((c) => c.revised_submission_id);
  const changeRun = change ? latestRunBySubmission.get(change.revised_submission_id!) : undefined;
  if (change && changeRun && ['PASSED', 'FAILED', 'TIMED_OUT'].includes(changeRun.status)) {
    const onRevised = evaluated.filter((a) => a.submission_id === change.revised_submission_id);
    const expl = onRevised.length ? onRevised.reduce((n, a) => n + a.evaluation.score, 0) / onRevised.length / 100 : passRate(changeRun.summary);
    out.push({
      dimension: 'adaptability',
      score: clampScore(70 * passRate(changeRun.summary) + 30 * expl),
      rationale: `After the requirement change: ${changeRun.summary.passed}/${changeRun.summary.tests} tests passed${onRevised.length ? `, ${onRevised.length} explanation(s) evaluated` : ''}.`,
      evidence: [{ kind: 'requirement_change', id: change.id }, { kind: 'submission', id: change.revised_submission_id! }, ...runRef(changeRun), ...onRevised.map<EvidenceRef>((a) => ({ kind: 'interview_answer', id: a.id }))],
      aiDerived: onRevised.length > 0,
    });
  } else out.push({ dimension: 'adaptability', score: null, rationale: '', evidence: [], aiDerived: false });

  const ordered = DIMENSIONS.map((d) => out.find((o) => o.dimension === d)!);
  ordered.forEach(assertValidDimensionScore);
  return ordered;
}

export class AssessmentService {
  constructor(
    private readonly ctx: Ctx,
    private readonly practices: PracticeService,
    private readonly timeline: TimelineService,
    private readonly git: GitService,
  ) {}

  private async facts(practiceId: string): Promise<Facts> {
    const db = this.ctx.db;
    const submissions = await db.query<any>('SELECT id, version, requirement_change_id, snapshot_id FROM submissions WHERE practice_id = $1 ORDER BY version', [practiceId]);
    const runs = await db.query<any>(`SELECT id, submission_id, status, summary FROM test_runs WHERE practice_id = $1 AND origin = 'sandbox' ORDER BY created_at`, [practiceId]);
    const finalId = submissions[submissions.length - 1]?.id;
    const analysis = finalId
      ? await db.one<any>(`SELECT id, output FROM ai_analyses WHERE submission_id = $1 AND status = 'SUCCEEDED' ORDER BY created_at DESC LIMIT 1`, [finalId])
      : null;
    const findings = (analysis?.output?.findings ?? []).map((x: any, index: number) => ({ analysisId: analysis.id, index, ...x }));
    const comments = await db.query<any>('SELECT id, status, submission_id FROM review_comments WHERE practice_id = $1', [practiceId]);
    const changes = await db.query<any>('SELECT id, revised_submission_id FROM requirement_changes WHERE practice_id = $1 ORDER BY created_at', [practiceId]);
    const answers = await db.query<any>(
      `SELECT a.id, a.question_id, q.submission_id, a.evaluation FROM interview_answers a JOIN interview_questions q ON q.id = a.question_id WHERE q.practice_id = $1`,
      [practiceId],
    );
    return { analysisId: analysis?.id ?? null, submissions, runs, findings, comments, changes, answers };
  }

  /** Generates a recommendation draft. Same facts + rubric version always yield the same scores. */
  async generateDraft(principal: Principal | null, practiceId: string) {
    const emp = requireKind(principal, 'employer');
    const practice = await this.practices.authorized(emp, 'practice:review', practiceId);
    const facts = await this.facts(practice.id);
    if (facts.submissions.length === 0) throw new DomainError('CONFLICT', 'no submissions to assess');
    const dimensions = scoreDimensions(facts);
    const agg = aggregate(dimensions, RUBRIC_VERSION);
    const id = newId('asm');
    await this.ctx.db.tx(async (tx) => {
      await tx.query(
        `INSERT INTO assessments (id, practice_id, rubric_version, dimensions, aggregation, overall_score, status, input_refs, created_at)
         VALUES ($1,$2,$3,$4,$5,$6,'DRAFT',$7,$8)`,
        [id, practice.id, RUBRIC_VERSION, JSON.stringify(dimensions), JSON.stringify(agg), agg.overall, JSON.stringify({ submissions: facts.submissions.map((s) => s.id), testRuns: facts.runs.map((r) => r.id) }), this.ctx.clock.now()],
      );
      await this.ctx.audit.append(tx, { actorKind: emp.kind, actorId: emp.id, action: 'assessment.drafted', entityType: 'assessment', entityId: id, organisationId: practice.organisation_id, practiceId, detail: { overall: agg.overall } });
    });
    return this.get(id);
  }

  async get(id: string) {
    const a = await this.ctx.db.one<any>('SELECT * FROM assessments WHERE id = $1', [id]);
    if (!a) throw notFound('assessment');
    return a;
  }

  async approve(principal: Principal | null, assessmentId: string) {
    const emp = requireKind(principal, 'employer');
    const a = await this.get(assessmentId);
    const practice = await this.practices.authorized(emp, 'practice:review', a.practice_id);
    if (a.status === 'APPROVED') return a;
    await this.ctx.db.tx(async (tx) => {
      await tx.query(`UPDATE assessments SET status = 'APPROVED', approved_by = $2, approved_at = $3 WHERE id = $1`, [assessmentId, emp.id, this.ctx.clock.now()]);
      await this.ctx.audit.append(tx, { actorKind: emp.kind, actorId: emp.id, action: 'assessment.approved', entityType: 'assessment', entityId: assessmentId, organisationId: practice.organisation_id, practiceId: practice.id });
    });
    return this.get(assessmentId);
  }

  /** Final profile. Access is audited; telemetry beyond the safe Timeline metadata is never included. */
  async report(principal: Principal | null, practiceId: string) {
    const practice = await this.practices.load(practiceId);
    authorize(principal, 'practice:report', scopeOf(practice));
    if (practice.purged_at) throw new DomainError('GONE', 'practice artifacts were purged by retention policy');
    const db = this.ctx.db;
    const [submissions, runs, commits, assessment, analysis, changes, comments, counts, interruptions, signals] = await Promise.all([
      db.query<any>('SELECT * FROM submissions WHERE practice_id = $1 ORDER BY version', [practiceId]),
      db.query<any>(`SELECT id, submission_id, status, summary, created_at, finished_at FROM test_runs WHERE practice_id = $1 AND origin = 'sandbox' ORDER BY created_at`, [practiceId]),
      db.query<any>('SELECT sha, message, author, changed_files, snapshot_id, committed_at FROM git_commits WHERE practice_id = $1 ORDER BY committed_at', [practiceId]),
      db.one<any>('SELECT * FROM assessments WHERE practice_id = $1 ORDER BY created_at DESC LIMIT 1', [practiceId]),
      db.one<any>(`SELECT * FROM ai_analyses WHERE practice_id = $1 AND status = 'SUCCEEDED' AND submission_id IS NOT NULL ORDER BY created_at DESC LIMIT 1`, [practiceId]),
      db.query<any>('SELECT * FROM requirement_changes WHERE practice_id = $1 ORDER BY created_at', [practiceId]),
      db.query<any>('SELECT id, status, file_path, line_start, line_end FROM review_comments WHERE practice_id = $1', [practiceId]),
      this.timeline.countsByType(practiceId),
      this.timeline.interruptions(practiceId),
      db.query<any>(`SELECT id, occurred_at, payload FROM telemetry_events WHERE practice_id = $1 AND type = 'large_insertion_signal' ORDER BY occurred_at`, [practiceId]),
    ]);
    const lastAnalysisFailed = await db.one<any>(`SELECT status, error FROM ai_analyses WHERE practice_id = $1 AND submission_id IS NOT NULL ORDER BY created_at DESC LIMIT 1`, [practiceId]);
    await this.ctx.audit.append(db, { actorKind: principal!.kind, actorId: principal!.id, action: 'report.viewed', entityType: 'practice', entityId: practiceId, organisationId: practice.organisation_id, practiceId });
    const findings = analysis?.output?.findings ?? [];
    return {
      practice: { id: practice.id, title: practice.title, status: practice.status, taskVersion: practice.task_version, deadline: practice.deadline },
      rubricVersion: assessment?.rubric_version ?? RUBRIC_VERSION,
      assessment: assessment
        ? {
            id: assessment.id,
            status: assessment.status,
            label: assessment.status === 'APPROVED' ? 'Approved by employer' : 'Recommendation — not a decision until the employer approves it',
            overall: assessment.overall_score,
            aggregation: assessment.aggregation,
            dimensions: assessment.dimensions,
          }
        : null,
      submissions: submissions.map((s) => ({ id: s.id, version: s.version, snapshotId: s.snapshot_id, commitSha: s.commit_sha, baselineSubmissionId: s.baseline_submission_id, requirementChangeId: s.requirement_change_id, submittedAt: s.submitted_at })),
      testResults: runs.map((r) => ({ id: r.id, submissionId: r.submission_id, status: r.status, summary: r.summary, finishedAt: r.finished_at })),
      commits: commits.map((c) => ({ sha: c.sha, message: c.message, author: c.author, changedFiles: c.changed_files, snapshotId: c.snapshot_id, committedAt: c.committed_at })),
      gitHistory: await this.git.log(practiceId, 100).catch(() => []),
      timeline: { eventCounts: counts, interruptions },
      ai: analysis
        ? { analysisId: analysis.id, model: { providerId: analysis.provider_id, modelId: analysis.model_id, templateVersion: analysis.template_version }, summary: analysis.output.summary, findings, label: 'AI-derived recommendations' }
        : { analysisId: null, status: lastAnalysisFailed?.status ?? 'NOT_STARTED', error: lastAnalysisFailed?.error ?? null, label: 'AI analysis is not available for this practice' },
      strengths: analysis?.output?.strengths ?? [],
      growthAreas: findings.filter((x: any) => ['medium', 'high', 'critical'].includes(x.severity)).map((x: any) => ({ title: x.title, recommendation: x.recommendation, evidence: x.evidence })),
      requirementChanges: changes.map((c) => ({ id: c.id, text: c.text, acceptanceCriteria: c.acceptance_criteria, baselineSubmissionId: c.baseline_submission_id, revisedSubmissionId: c.revised_submission_id })),
      review: { comments: comments.length, resolved: comments.filter((c) => c.status === 'RESOLVED').length },
      telemetrySignals: {
        note: 'Signals indicate where additional review may be useful. They are not evidence of misconduct.',
        largeInsertions: signals.map((s) => ({ eventId: s.id, at: s.occurred_at, file: s.payload.file, insertedChars: s.payload.insertedChars, threshold: s.payload.threshold })),
        interruptions: interruptions.length,
      },
    };
  }
}
