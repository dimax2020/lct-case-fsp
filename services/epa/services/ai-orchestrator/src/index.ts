import { authorize, type Principal } from '@epa/authz';
import type { AnalysisResultOutput, ImprovementSet, MaterialsReview, TaskSuggestionSet } from '@epa/contracts';
import { DomainError, notFound } from '@epa/domain';
import { newId, PermanentJobError, type Ctx, type JobRow, type Queryable } from '@epa/platform';
import {
  AI_POLICY_VERSION,
  AiProviderError,
  filterGrounded,
  validateEvidence,
  validateGrounding,
  type CodeAnalysisProvider,
  type ContextFile,
  type Rejection,
} from '@epa/ai-provider';
import { isSecretFile, redactSecrets, sha256Hex } from '@epa/telemetry';
import type { MaterialsInput, ProcessInput } from '@epa/ai-provider';
import { scopeOf, type PracticeService, type SubmissionService } from '@epa/practice';
import type { SnapshotService } from '@epa/snapshots';
import { pickSetupPaths } from './setup-context.js';

const MAX_FILE_BYTES = 64 * 1024;
const MAX_CONTEXT_BYTES = 200 * 1024;
const MAX_FOLLOW_UP_DEPTH = 2;
const TEXT_EXT = /\.(js|mjs|cjs|ts|tsx|jsx|json|md|txt|py|go|rs|java|kt|rb|php|cs|c|h|cpp|hpp|sql|yaml|yml|toml|sh|css|html)$/i;

function moduleName(path: string): string {
  const parts = path.split('/').filter(Boolean);
  if (parts.length <= 1) return '(корень)';
  if (parts[0] === 'src' && parts.length >= 3) return `${parts[0]}/${parts[1]}`;
  return parts.slice(0, -1).join('/');
}

function activeMinutes(times: number[]): number {
  const sorted = [...times].sort((a, b) => a - b);
  let ms = 0;
  for (let i = 1; i < sorted.length; i++) {
    const gap = sorted[i]! - sorted[i - 1]!;
    if (gap >= 1000 && gap <= 3 * 60_000) ms += gap;
  }
  return Math.round(ms / 6000) / 10;
}

export interface ProjectReader {
  listTree(practiceId: string): Promise<{ path: string; size: number }[]>;
  readBlob(practiceId: string, filePath: string): Promise<{ content: string; binary: boolean }>;
}

export interface ActivityFacts {
  pastedChars: number;
  copiedChars: number;
  externalPastes: number;
  workspacePastes: number;
  insertedChars: number;
  largeInsertionSignals: number;
  commits: number;
  pasteFiles: string[];
}

export interface AnalysisRow {
  id: string;
  practice_id: string;
  submission_id: string | null;
  kind: 'submission' | 'task' | 'process' | 'materials' | 'improvements';
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'RETRYING' | 'FAILED';
  provider_id: string;
  model_id: string;
  template_version: string;
  policy_version: string;
  input_hashes: Record<string, string> | null;
  output: (AnalysisResultOutput & { aiDerived: true }) | null;
  rejected: Rejection[];
  error: string | null;
  attempts: number;
  created_at: Date;
  finished_at: Date | null;
  progress?: number;
}

export class AiOrchestrator {
  constructor(
    private readonly ctx: Ctx,
    private readonly provider: CodeAnalysisProvider,
    private readonly practices: PracticeService,
    private readonly submissions: SubmissionService,
    private readonly snapshots: SnapshotService,
    private readonly project?: ProjectReader,
    private readonly setupModel = 'qwen2.5-coder:0.5b',
  ) {}

  private readonly progressMarks = new Map<string, { value: number; at: number }>();

  /**
   * Builds the only context the model sees: text files of the selected submission snapshot,
   * excluding secret files, with secrets redacted and size limits applied.
   */
  async buildContext(snapshotId: string): Promise<ContextFile[]> {
    const tree = await this.snapshots.reconstruct(snapshotId);
    const files: ContextFile[] = [];
    let total = 0;
    for (const [path, data] of [...tree.entries()].sort(([a], [b]) => a.localeCompare(b))) {
      if (isSecretFile(path) || !TEXT_EXT.test(path) || data.length > MAX_FILE_BYTES || data.includes(0)) continue;
      if (path === 'package-lock.json') continue;
      if (total + data.length > MAX_CONTEXT_BYTES) break;
      const content = redactSecrets(data.toString('utf8'));
      files.push({ path, content, lineCount: content.split('\n').length, sha256: sha256Hex(data) });
      total += data.length;
    }
    return files;
  }

  /** The model only needs the files that explain the submission, not the whole tree. */
  private async submissionFiles(snapshotId: string): Promise<ContextFile[]> {
    const all = await this.buildContext(snapshotId);
    const picked = new Set(pickSetupPaths(all.map((f) => f.path), 12));
    const chosen = (picked.size ? all.filter((f) => picked.has(f.path)) : all).slice(0, 12);
    const files: ContextFile[] = [];
    let total = 0;
    for (const file of chosen) {
      const content = file.content.slice(0, 6_000);
      if (total + content.length > 32_000) break;
      files.push({ ...file, content, lineCount: content.split('\n').length });
      total += content.length;
    }
    return files;
  }

  async enqueue(q: Queryable, input: { practiceId: string; submissionId: string }): Promise<string> {
    const id = newId('ai');
    await q.query(
      `INSERT INTO ai_analyses (id, practice_id, submission_id, kind, status, provider_id, model_id, template_version, policy_version, created_at)
       VALUES ($1,$2,$3,'submission','QUEUED',$4,$5,$6,$7,$8)`,
      [id, input.practiceId, input.submissionId, this.provider.meta.providerId, this.provider.meta.modelId, this.provider.meta.templateVersion, AI_POLICY_VERSION, this.ctx.clock.now()],
    );
    await this.ctx.jobs.enqueue('ai.analyze', { analysisId: id }, { dedupeKey: `ai:${id}`, maxAttempts: 3 }, q);
    return id;
  }

  async requestAnalysis(principal: Principal | null, submissionId: string) {
    const { submission } = await this.submissions.authorizedSubmission(principal, 'practice:review', submissionId);
    return this.ctx.db.tx((tx) => this.enqueue(tx, { practiceId: submission.practice_id, submissionId }));
  }

  /** Job handler. Provider outages retry with backoff; the final failure is stored and shown honestly. */
  async handleAnalyze(job: JobRow): Promise<void> {
    const a = await this.ctx.db.one<AnalysisRow>('SELECT * FROM ai_analyses WHERE id = $1', [job.payload.analysisId]);
    if (!a || a.status === 'SUCCEEDED' || a.status === 'FAILED') return;
    await this.ctx.db.query(`UPDATE ai_analyses SET status = 'RUNNING', attempts = attempts + 1 WHERE id = $1`, [a.id]);
    try {
      if (!a.submission_id) throw new PermanentJobError('submission analysis has no submission');
      const submission = await this.submissions.get(a.submission_id);
      const practice = await this.practices.load(a.practice_id);
      await this.markProgress(a.id, 2);
      const files = await this.submissionFiles(submission.snapshot_id);
      if (files.length === 0) throw new PermanentJobError('no analysable source files in submission');
      await this.markProgress(a.id, 40);
      const testRun = await this.ctx.db.one<any>(`SELECT summary FROM test_runs WHERE submission_id = $1 AND origin = 'sandbox' ORDER BY created_at DESC LIMIT 1`, [submission.id]);
      const activity = await this.activity(practice.id);
      const counts = await this.ctx.db.query<{ type: string; n: number }>('SELECT type, count(*)::int AS n FROM telemetry_events WHERE practice_id = $1 GROUP BY type', [practice.id]);
      const eventCounts = Object.fromEntries(counts.map((c) => [c.type, c.n]));
      const comments = await this.ctx.db.query<any>('SELECT file_path, line_start, line_end, body, status FROM review_comments WHERE practice_id = $1', [practice.id]);
      const changes = await this.ctx.db.query<any>('SELECT text, acceptance_criteria FROM requirement_changes WHERE practice_id = $1', [practice.id]);
      const requirementChanges = changes.map((c) => ({ text: c.text, acceptanceCriteria: c.acceptance_criteria }));
      const inputHashes = { ...Object.fromEntries(files.map((f) => [f.path, f.sha256])), '@snapshot': submission.snapshot_id };

      const raw = await this.provider.analyzeCode({
        files,
        tests: testRun?.summary ? { status: testRun.summary.status, passed: testRun.summary.passed, failed: testRun.summary.failed, failedTests: testRun.summary.failedTests } : null,
        timeline: {
          eventCounts,
          largeInsertionSignals: activity.largeInsertionSignals,
          commits: activity.commits,
          pastedChars: activity.pastedChars,
          copiedChars: activity.copiedChars,
          externalPastes: activity.externalPastes,
          workspacePastes: activity.workspacePastes,
          insertedChars: activity.insertedChars,
        },
        reviewComments: comments.map((c) => ({ filePath: c.file_path, lineStart: c.line_start, lineEnd: c.line_end, body: c.body, status: c.status })),
        requirementChanges,
        taskDescription: practice.description,
        model: this.setupModel,
      }, this.writingProgress(a.id));
      const findings = filterGrounded(raw.findings, files, (f) => `${f.title} ${f.explanation} ${f.recommendation}`);
      const strengths = filterGrounded(raw.strengths, files, (s) => s.text);
      const summaryRejection = validateGrounding(raw.summary, files);

      const authorship = raw.authorship && !validateGrounding(raw.authorship.summary, files) ? raw.authorship : null;
      await this.markProgress(a.id, 90);
      const qs = await this.provider.generateQuestions({ files, findings: findings.accepted, requirementChanges, maxQuestions: 5, pasteFiles: activity.pasteFiles, model: this.setupModel });
      const questions = filterGrounded(qs.questions, files, (q) => `${q.text} ${q.rationale}`);

      const output = {
        summary: summaryRejection ? 'Описание скрыто: модель сослалась на то, чего нет в сданном коде.' : raw.summary,
        findings: findings.accepted,
        strengths: strengths.accepted,
        authorship,
        activity,
        aiDerived: true as const,
      };
      const rejected = [...findings.rejected, ...strengths.rejected, ...questions.rejected, ...(summaryRejection ? [summaryRejection] : [])];
      const meta = { ...this.provider.meta, policyVersion: AI_POLICY_VERSION, analysisId: a.id, at: this.ctx.clock.now().toISOString() };
      await this.ctx.db.tx(async (tx) => {
        await tx.query(
          `UPDATE ai_analyses SET status = 'SUCCEEDED', output = $2, rejected = $3, input_hashes = $4, error = NULL, finished_at = $5, progress = 100 WHERE id = $1`,
          [a.id, JSON.stringify(output), JSON.stringify(rejected), JSON.stringify(inputHashes), this.ctx.clock.now()],
        );
        for (const q of questions.accepted) {
          await tx.query(
            `INSERT INTO interview_questions (id, practice_id, submission_id, analysis_id, depth, text, rationale, evidence, ai_meta, created_at)
             VALUES ($1,$2,$3,$4,0,$5,$6,$7,$8,$9)`,
            [newId('q'), practice.id, submission.id, a.id, q.text, q.rationale, JSON.stringify(q.evidence), JSON.stringify(meta), this.ctx.clock.now()],
          );
        }
      });
      this.ctx.metrics.inc('ai_analyses_total', { outcome: 'succeeded' });
    } catch (e) {
      const message = e instanceof AiProviderError ? `${e.kind}: ${e.message}` : e instanceof Error ? e.message : String(e);
      const final = e instanceof PermanentJobError || job.attempts >= job.max_attempts;
      await this.ctx.db.query(`UPDATE ai_analyses SET status = $2::text, error = $3, finished_at = CASE WHEN $2::text = 'FAILED' THEN $4::timestamptz ELSE NULL END WHERE id = $1`, [
        a.id,
        final ? 'FAILED' : 'RETRYING',
        message.slice(0, 500),
        this.ctx.clock.now(),
      ]);
      this.ctx.metrics.inc('ai_analyses_total', { outcome: final ? 'failed' : 'retrying' });
      throw e;
    }
  }

  async answer(principal: Principal | null, questionId: string, text: string) {
    if (typeof questionId !== 'string' || questionId.length > 100) throw notFound('question');
    const q = await this.ctx.db.one<any>('SELECT * FROM interview_questions WHERE id = $1', [questionId]);
    if (!q) throw notFound('question');
    const practice = await this.practices.load(q.practice_id);
    authorize(principal, 'interview:answer', scopeOf(practice));
    if (practice.status === 'COMPLETED' || practice.status === 'EXPIRED') throw new DomainError('CONFLICT', 'interview is closed');
    const id = newId('ans');
    await this.ctx.db.tx(async (tx) => {
      const existing = await tx.one('SELECT id FROM interview_answers WHERE question_id = $1', [questionId]);
      if (existing) throw new DomainError('CONFLICT', 'question already answered');
      const now = this.ctx.clock.now();
      const opened = q.shown_at ? new Date(q.shown_at).getTime() : now.getTime();
      const durationMs = Math.max(0, now.getTime() - opened);
      await tx.query(`INSERT INTO interview_answers (id, question_id, candidate_id, text, duration_ms, created_at) VALUES ($1,$2,$3,$4,$5,$6)`, [id, questionId, principal!.id, text, durationMs, now]);
      await this.ctx.jobs.enqueue('ai.evaluate_answer', { answerId: id }, { dedupeKey: `eval:${id}`, maxAttempts: 3 }, tx);
    });
    return { answerId: id };
  }

  async handleEvaluate(job: JobRow): Promise<void> {
    const ans = await this.ctx.db.one<any>('SELECT * FROM interview_answers WHERE id = $1', [job.payload.answerId]);
    if (!ans || ans.evaluation_status === 'DONE') return;
    const q = await this.ctx.db.one<any>('SELECT * FROM interview_questions WHERE id = $1', [ans.question_id]);
    const submission = await this.submissions.get(q.submission_id);
    const files = await this.buildContext(submission.snapshot_id);
    const file = files.find((f) => f.path === q.evidence.file);
    try {
      if (!file) throw new PermanentJobError('cited file is no longer in context');
      const allowFollowUp = q.depth < MAX_FOLLOW_UP_DEPTH;
      const ev = await this.provider.evaluateInterview({ question: { text: q.text, evidence: q.evidence }, answer: ans.text, codeExcerpt: file, depth: q.depth, allowFollowUp });
      let followUpId: string | null = null;
      let followUpRejected: Rejection | null = null;
      if (ev.followUp && allowFollowUp) {
        followUpRejected = validateEvidence(ev.followUp.evidence, new Map(files.map((f) => [f.path, f]))) ?? validateGrounding(ev.followUp.text, files);
        if (!followUpRejected) followUpId = newId('q');
      }
      const meta = { ...this.provider.meta, policyVersion: AI_POLICY_VERSION, at: this.ctx.clock.now().toISOString() };
      await this.ctx.db.tx(async (tx) => {
        await tx.query(`UPDATE interview_answers SET evaluation = $2, evaluation_status = 'DONE', ai_meta = $3 WHERE id = $1`, [
          ans.id,
          JSON.stringify({ understanding: ev.understanding, score: ev.score, rationale: ev.rationale, aiDerived: true, followUpRejected }),
          JSON.stringify(meta),
        ]);
        if (followUpId) {
          await tx.query(
            `INSERT INTO interview_questions (id, practice_id, submission_id, analysis_id, parent_question_id, depth, text, rationale, evidence, ai_meta, created_at)
             VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
            [followUpId, q.practice_id, q.submission_id, q.analysis_id, q.id, q.depth + 1, ev.followUp!.text, ev.followUp!.rationale, JSON.stringify(ev.followUp!.evidence), JSON.stringify(meta), this.ctx.clock.now()],
          );
        }
      });
    } catch (e) {
      const final = e instanceof PermanentJobError || job.attempts >= job.max_attempts;
      await this.ctx.db.query(`UPDATE interview_answers SET evaluation_status = $2 WHERE id = $1`, [ans.id, final ? 'FAILED' : 'RETRYING']);
      throw e;
    }
  }

  async listForPractice(principal: Principal | null, practiceId: string) {
    const practice = await this.practices.load(practiceId);
    authorize(principal, 'practice:timeline', scopeOf(practice));
    const isCandidate = principal!.kind === 'candidate';
    const analyses = await this.ctx.db.query<AnalysisRow>('SELECT * FROM ai_analyses WHERE practice_id = $1 ORDER BY created_at', [practiceId]);
    const activity = isCandidate ? null : await this.activity(practiceId);
    const code = analyses.filter((a) => (a.kind ?? 'submission') === 'submission');
    const tasks = analyses.filter((a) => a.kind === 'task');
    const process = analyses.filter((a) => a.kind === 'process');
    const materials = analyses.filter((a) => a.kind === 'materials');
    const improvements = analyses.filter((a) => a.kind === 'improvements');
    if (isCandidate) {
      await this.ctx.db.query(
        `UPDATE interview_questions SET shown_at = $2 WHERE practice_id = $1 AND shown_at IS NULL AND NOT EXISTS (SELECT 1 FROM interview_answers a WHERE a.question_id = interview_questions.id)`,
        [practiceId, this.ctx.clock.now()],
      );
    }
    const questions = await this.ctx.db.query<any>(
      `SELECT q.*, a.id AS answer_id, a.text AS answer_text, a.evaluation, a.evaluation_status, a.created_at AS answered_at, a.duration_ms
       FROM interview_questions q LEFT JOIN interview_answers a ON a.question_id = q.id WHERE q.practice_id = $1 ORDER BY q.created_at`,
      [practiceId],
    );
    return {
      // Candidates see questions only; findings and evaluations are employer-facing recommendations.
      activity,
      taskSuggestions: tasks.map((a) => this.presentAnalysis(a, isCandidate)),
      processReviews: isCandidate ? [] : process.map((a) => this.presentAnalysis(a, false)),
      materialsReviews: isCandidate ? [] : materials.map((a) => this.presentAnalysis(a, false)),
      improvements: isCandidate ? [] : improvements.map((a) => this.presentAnalysis(a, false)),
      analyses: isCandidate
        ? code.map((a) => ({ id: a.id, submissionId: a.submission_id, status: a.status }))
        : code.map((a) => ({
            id: a.id,
            submissionId: a.submission_id,
            status: a.status,
            provider: { providerId: a.provider_id, modelId: a.model_id, templateVersion: a.template_version, policyVersion: a.policy_version },
            output: a.output,
            rejectedCount: a.rejected.length,
            rejected: a.rejected,
            error: a.error,
            inputHashes: a.input_hashes,
            createdAt: a.created_at,
            finishedAt: a.finished_at,
            label: 'AI-derived recommendation for the employer; not a decision.',
          })),
      questions: questions.map((q) => ({
        id: q.id,
        submissionId: q.submission_id,
        parentQuestionId: q.parent_question_id,
        depth: q.depth,
        text: q.text,
        evidence: q.evidence,
        rationale: isCandidate ? undefined : q.rationale,
        shownAt: q.shown_at,
        answer: q.answer_id
          ? { id: q.answer_id, text: q.answer_text, evaluationStatus: q.evaluation_status, evaluation: isCandidate ? undefined : q.evaluation, answeredAt: q.answered_at, durationMs: q.duration_ms == null ? null : Number(q.duration_ms) }
          : null,
      })),
    };
  }

  async enqueueTaskSuggestion(practiceId: string): Promise<string> {
    return this.enqueueKind(practiceId, 'task', 'ai.suggest_tests');
  }

  async enqueueProcessReview(practiceId: string): Promise<string> {
    return this.enqueueKind(practiceId, 'process', 'ai.assess_process');
  }

  async enqueueMaterialsReview(practiceId: string): Promise<string> {
    return this.enqueueKind(practiceId, 'materials', 'ai.review_materials', this.setupModel);
  }

  async enqueueImprovements(practiceId: string): Promise<string> {
    return this.enqueueKind(practiceId, 'improvements', 'ai.suggest_improvements', this.setupModel);
  }

  async handleSuggest(job: JobRow): Promise<void> {
    const a = await this.requireOpen(job);
    if (!a) return;
    try {
      const practice = await this.practices.load(a.practice_id);
      await this.markProgress(a.id, 2);
      const files = await this.projectFiles(practice.id, practice.description, practice.brief, (done, total) => {
        void this.markProgress(a.id, total ? Math.round((38 * done) / total) : 2);
      });
      if (files.length === 0) throw new PermanentJobError('нет файлов проекта и текста задания');
      await this.markProgress(a.id, 40);
      const raw = await this.provider.suggestTests({ files, taskDescription: practice.description, brief: practice.brief ?? '' }, this.writingProgress(a.id));
      const tests = filterGrounded(raw.tests, files, (t) => `${t.title} ${t.goal} ${t.scenario}`);
      const summaryRejection = validateGrounding(raw.summary, files);
      const output: TaskSuggestionSet = {
        summary: summaryRejection ? 'Описание скрыто: модель сослалась на то, чего нет в проекте.' : raw.summary,
        tests: tests.accepted,
      };
      await this.finish(a.id, output, [...tests.rejected, ...(summaryRejection ? [summaryRejection] : [])], files);
    } catch (e) {
      await this.failAnalysis(a.id, job, e);
      throw e;
    }
  }

  async handleProcess(job: JobRow): Promise<void> {
    const a = await this.requireOpen(job);
    if (!a) return;
    try {
      const practice = await this.practices.load(a.practice_id);
      await this.markProgress(a.id, 2);
      const activity = await this.activity(practice.id);
      const modules = await this.moduleWork(practice.id);
      await this.markProgress(a.id, 40);
      const input: ProcessInput = {
        taskDescription: practice.description,
        pastedChars: activity.pastedChars,
        copiedChars: activity.copiedChars,
        externalPastes: activity.externalPastes,
        workspacePastes: activity.workspacePastes,
        insertedChars: activity.insertedChars,
        largeInsertionSignals: activity.largeInsertionSignals,
        commits: activity.commits,
        modules,
      };
      const review = await this.provider.assessProcess(input, this.writingProgress(a.id));
      await this.finish(a.id, { ...review, activity, modules, aiDerived: true }, [], []);
    } catch (e) {
      await this.failAnalysis(a.id, job, e);
      throw e;
    }
  }

  async handleMaterials(job: JobRow): Promise<void> {
    const a = await this.requireOpen(job);
    if (!a) return;
    try {
      const practice = await this.practices.load(a.practice_id);
      await this.markProgress(a.id, 2);
      const files = await this.withBrief(practice, await this.setupContext(practice.id, (done, total) => {
        void this.markProgress(a.id, total ? Math.round((38 * done) / total) : 2);
      }));
      if (files.length === 0) throw new PermanentJobError('нет файлов проекта и текста задания');
      await this.markProgress(a.id, 40);
      const raw = await this.provider.reviewMaterials(this.materialsInput(practice, files), this.writingProgress(a.id));
      const summaryRejection = validateGrounding(raw.summary, files);
      const descriptionRejection = validateGrounding(raw.description, files);
      const output: MaterialsReview = {
        summary: summaryRejection ? 'Краткий разбор скрыт: модель сослалась на то, чего нет в проекте.' : raw.summary,
        description: descriptionRejection ? 'Описание скрыто: модель сослалась на то, чего нет в проекте. Напишите его сами.' : raw.description,
      };
      await this.finish(a.id, output, [summaryRejection, descriptionRejection].filter((r): r is Rejection => !!r), files);
    } catch (e) {
      await this.failAnalysis(a.id, job, e);
      throw e;
    }
  }

  async handleImprovements(job: JobRow): Promise<void> {
    const a = await this.requireOpen(job);
    if (!a) return;
    try {
      const practice = await this.practices.load(a.practice_id);
      await this.markProgress(a.id, 2);
      const files = await this.withBrief(practice, await this.setupContext(practice.id, (done, total) => {
        void this.markProgress(a.id, total ? Math.round((38 * done) / total) : 2);
      }));
      if (files.length === 0) throw new PermanentJobError('нет файлов проекта и текста задания');
      await this.markProgress(a.id, 40);
      const raw = await this.provider.suggestImprovements(this.materialsInput(practice, files), this.writingProgress(a.id));
      const items = raw.items.filter((item) => !validateGrounding(`${item.title} ${item.text}`, files));
      const rejected = raw.items.filter((item) => validateGrounding(`${item.title} ${item.text}`, files)).map((item) => ({
        item,
        reason: 'ungrounded_technology' as const,
        detail: 'recommendation mentions a technology absent from the project',
      }));
      const summaryRejection = validateGrounding(raw.summary, files);
      const output: ImprovementSet = {
        summary: summaryRejection ? 'Рекомендации скрыты частично: модель сослалась на то, чего нет в проекте.' : raw.summary,
        items: items.length ? items : [{ title: 'Нет привязанных правок', text: 'Модель не предложила правок, которые можно подтвердить файлами проекта. Добавьте свои текстом.' }],
      };
      await this.finish(a.id, output, [...rejected, ...(summaryRejection ? [summaryRejection] : [])], files);
    } catch (e) {
      await this.failAnalysis(a.id, job, e);
      throw e;
    }
  }

  private materialsInput(practice: { title: string; brief: string | null; employer_notes: string | null; description: string }, files: ContextFile[]): MaterialsInput {
    return {
      title: practice.title,
      files,
      brief: practice.brief ?? '',
      notes: '',
      model: this.setupModel,
    };
  }

  private async enqueueKind(
    practiceId: string,
    kind: 'task' | 'process' | 'materials' | 'improvements',
    jobKind: 'ai.suggest_tests' | 'ai.assess_process' | 'ai.review_materials' | 'ai.suggest_improvements',
    modelId = this.provider.meta.modelId,
  ): Promise<string> {
    const id = newId('ai');
    await this.ctx.db.tx(async (tx) => {
      await tx.query(
        `INSERT INTO ai_analyses (id, practice_id, submission_id, kind, status, provider_id, model_id, template_version, policy_version, created_at)
         VALUES ($1,$2,NULL,$3,'QUEUED',$4,$5,$6,$7,$8)`,
        [id, practiceId, kind, this.provider.meta.providerId, modelId, this.provider.meta.templateVersion, AI_POLICY_VERSION, this.ctx.clock.now()],
      );
      await this.ctx.jobs.enqueue(jobKind, { analysisId: id }, { dedupeKey: `${kind}:${id}`, maxAttempts: 2 }, tx);
    });
    return id;
  }

  private async requireOpen(job: JobRow): Promise<AnalysisRow | null> {
    const a = await this.ctx.db.one<AnalysisRow>('SELECT * FROM ai_analyses WHERE id = $1', [job.payload.analysisId]);
    if (!a || a.status === 'SUCCEEDED' || a.status === 'FAILED') return null;
    await this.ctx.db.query(`UPDATE ai_analyses SET status = 'RUNNING', attempts = attempts + 1 WHERE id = $1`, [a.id]);
    return a;
  }

  private async finish(id: string, output: unknown, rejected: Rejection[], files: { path: string; sha256: string }[]): Promise<void> {
    const inputHashes = Object.fromEntries(files.map((f) => [f.path, f.sha256]));
    await this.ctx.db.query(
      `UPDATE ai_analyses SET status = 'SUCCEEDED', output = $2, rejected = $3, input_hashes = $4, error = NULL, finished_at = $5, progress = 100 WHERE id = $1`,
      [id, JSON.stringify(output), JSON.stringify(rejected), JSON.stringify(inputHashes), this.ctx.clock.now()],
    );
    this.ctx.metrics.inc('ai_analyses_total', { outcome: 'succeeded' });
  }

  private async failAnalysis(id: string, job: JobRow, e: unknown): Promise<void> {
    const message = e instanceof AiProviderError ? `${e.kind}: ${e.message}` : e instanceof Error ? e.message : String(e);
    const final = e instanceof PermanentJobError || job.attempts >= job.max_attempts;
    await this.ctx.db.query(`UPDATE ai_analyses SET status = $2::text, error = $3, finished_at = CASE WHEN $2::text = 'FAILED' THEN $4::timestamptz ELSE NULL END WHERE id = $1`, [
      id,
      final ? 'FAILED' : 'RETRYING',
      message.slice(0, 500),
      this.ctx.clock.now(),
    ]);
    this.ctx.metrics.inc('ai_analyses_total', { outcome: final ? 'failed' : 'retrying' });
  }

  private presentAnalysis(a: AnalysisRow, hideDetail: boolean) {
    if (hideDetail) {
      const output = a.output as { summary?: string; tests?: unknown[] } | null;
      return { id: a.id, status: a.status, summary: output?.summary ?? null, tests: output?.tests ?? [] };
    }
    return {
      id: a.id,
      status: a.status,
      provider: { providerId: a.provider_id, modelId: a.model_id },
      output: a.output,
      error: a.error,
      createdAt: a.created_at,
      finishedAt: a.finished_at,
      progress: a.status === 'SUCCEEDED' ? 100 : Number(a.progress ?? 0),
      label: 'Рекомендация локальной модели, не решение работодателя.',
    };
  }

  /** Climbs toward 96 while text arrives, instead of pinning at 95 after the first thousand characters. */
  private writingProgress(id: string): (text: string) => void {
    return (text) => {
      const gain = Math.round(56 * (1 - Math.exp(-text.length / 2800)));
      void this.markProgress(id, 40 + gain);
    };
  }

  private async markProgress(id: string, progress: number): Promise<void> {
    const value = Math.max(0, Math.min(99, Math.round(progress)));
    const prev = this.progressMarks.get(id);
    const now = Date.now();
    if (prev && value <= prev.value) return;
    if (prev && now - prev.at < 350 && value - prev.value < 20 && value < 95) return;
    this.progressMarks.set(id, { value, at: now });
    await this.ctx.db.query('UPDATE ai_analyses SET progress = $2 WHERE id = $1', [id, value]);
  }

  /** Reads the files that explain the project, not lockfiles or the whole tree. */
  private async setupContext(practiceId: string, onFile?: (done: number, total: number) => void): Promise<ContextFile[]> {
    if (!this.project) return [];
    let tree: { path: string; size: number }[] = [];
    try {
      tree = await this.project.listTree(practiceId);
    } catch {
      return [];
    }
    const picked = pickSetupPaths(tree.filter((item) => TEXT_EXT.test(item.path) && !isSecretFile(item.path)).map((item) => item.path));
    const files: ContextFile[] = [];
    let total = 0;
    onFile?.(0, picked.length);
    for (let i = 0; i < picked.length; i++) {
      const path = picked[i]!;
      const blob = await this.project.readBlob(practiceId, path);
      onFile?.(i + 1, picked.length);
      if (blob.binary || !blob.content) continue;
      const content = redactSecrets(blob.content).slice(0, 6_000);
      if (total + content.length > 32_000) break;
      files.push({ path, content, lineCount: content.split('\n').length, sha256: sha256Hex(content) });
      total += content.length;
    }
    return files;
  }

  /** Keeps the uploaded specification in the model context together with the source files. */
  private withBrief(practice: { brief: string | null; description: string }, files: ContextFile[]): ContextFile[] {
    const spec = (practice.brief || '').trim();
    const fallback = spec ? '' : (practice.description || '').trim();
    const text = spec || (files.length === 0 ? fallback : '');
    if (!text) return files;
    const content = text.slice(0, 8_000);
    const specFile: ContextFile = {
      path: spec ? 'ТЗ.md' : 'ЗАДАНИЕ.md',
      content,
      lineCount: content.split('\n').length,
      sha256: sha256Hex(content),
    };
    const kept: ContextFile[] = [specFile];
    let total = content.length;
    for (const file of files) {
      if (file.path === specFile.path) continue;
      if (total + file.content.length > 32_000) break;
      kept.push(file);
      total += file.content.length;
    }
    return kept;
  }

  private async activity(practiceId: string): Promise<ActivityFacts> {
    const rows = await this.ctx.db.query<{ type: string; payload: any }>(
      `SELECT type, payload FROM telemetry_events WHERE practice_id = $1 AND type IN ('code_pasted','code_copied','file_changed','large_insertion_signal','git_commit')`,
      [practiceId],
    );
    const facts: ActivityFacts = { pastedChars: 0, copiedChars: 0, externalPastes: 0, workspacePastes: 0, insertedChars: 0, largeInsertionSignals: 0, commits: 0, pasteFiles: [] };
    const files = new Set<string>();
    for (const row of rows) {
      const p = row.payload ?? {};
      if (row.type === 'code_pasted') {
        facts.pastedChars += Number(p.chars) || 0;
        if (p.origin === 'workspace') facts.workspacePastes += 1;
        else if (p.origin === 'external') facts.externalPastes += 1;
        if (typeof p.file === 'string') files.add(p.file);
      } else if (row.type === 'code_copied') facts.copiedChars += Number(p.chars) || 0;
      else if (row.type === 'file_changed') facts.insertedChars += Number(p.insertedChars) || 0;
      else if (row.type === 'large_insertion_signal') facts.largeInsertionSignals += 1;
      else if (row.type === 'git_commit') facts.commits += 1;
    }
    facts.pasteFiles = [...files];
    return facts;
  }

  /** Active minutes are gaps between edits in one module, ignoring pauses longer than three minutes. */
  private async moduleWork(practiceId: string): Promise<ProcessInput['modules']> {
    const rows = await this.ctx.db.query<{ type: string; occurred_at: Date; payload: any }>(
      `SELECT type, occurred_at, payload FROM telemetry_events
       WHERE practice_id = $1 AND type IN ('file_changed','file_saved','code_pasted','large_insertion_signal')
       ORDER BY occurred_at`,
      [practiceId],
    );
    const byModule = new Map<string, { times: number[]; insertedChars: number; pastedChars: number; externalPastes: number; largeInsertions: number }>();
    for (const row of rows) {
      const payload = row.payload ?? {};
      const path = typeof payload.path === 'string' ? payload.path : typeof payload.file === 'string' ? payload.file : '';
      if (!path) continue;
      const name = moduleName(path);
      const bucket = byModule.get(name) ?? { times: [], insertedChars: 0, pastedChars: 0, externalPastes: 0, largeInsertions: 0 };
      bucket.times.push(new Date(row.occurred_at).getTime());
      if (row.type === 'file_changed') bucket.insertedChars += Number(payload.insertedChars) || 0;
      if (row.type === 'code_pasted') {
        bucket.pastedChars += Number(payload.chars) || 0;
        if (payload.origin === 'external') bucket.externalPastes += 1;
      }
      if (row.type === 'large_insertion_signal') bucket.largeInsertions += 1;
      byModule.set(name, bucket);
    }
    return [...byModule.entries()]
      .map(([module, bucket]) => ({
        module,
        activeMinutes: activeMinutes(bucket.times),
        insertedChars: bucket.insertedChars,
        pastedChars: bucket.pastedChars,
        externalPastes: bucket.externalPastes,
        largeInsertions: bucket.largeInsertions,
      }))
      .sort((a, b) => b.activeMinutes - a.activeMinutes || b.insertedChars - a.insertedChars)
      .slice(0, 12);
  }

  private async projectFiles(practiceId: string, description: string, brief: string | null, onFile?: (done: number, total: number) => void) {
    const files: { path: string; content: string; lineCount: number; sha256: string }[] = [];
    let total = 0;
    if (this.project) {
      try {
        const tree = (await this.project.listTree(practiceId)).filter((item) => !isSecretFile(item.path) && TEXT_EXT.test(item.path) && item.path !== 'package-lock.json' && item.size <= MAX_FILE_BYTES);
        for (let i = 0; i < tree.length; i++) {
          onFile?.(i + 1, tree.length);
          const item = tree[i]!;
          const blob = await this.project.readBlob(practiceId, item.path);
          if (blob.binary || !blob.content) continue;
          if (total + blob.content.length > MAX_CONTEXT_BYTES) break;
          const content = redactSecrets(blob.content);
          files.push({ path: item.path, content, lineCount: content.split('\n').length, sha256: sha256Hex(content) });
          total += content.length;
        }
      } catch {
        /* repository is not ready yet */
      }
    }
    const add = (path: string, text: string) => {
      if (!text.trim() || files.some((f) => f.path === path)) return;
      const content = text.slice(0, MAX_FILE_BYTES);
      files.push({ path, content, lineCount: content.split('\n').length, sha256: sha256Hex(content) });
    };
    if (brief) add('ТЗ.md', brief);
    if (files.length === 0) add('ЗАДАНИЕ.md', description);
    return files;
  }
}
