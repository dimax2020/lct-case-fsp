import path from 'node:path';
import { mkdir } from 'node:fs/promises';
import {
  AuditLog,
  FsObjectStore,
  JobQueue,
  Metrics,
  ObjectAccessSigner,
  RateLimiter,
  Worker,
  createDb,
  createLogger,
  migrate,
  systemClock,
  type Clock,
  type Ctx,
  type Db,
  type JobHandler,
  type JobKind,
  type Logger,
  type PlatformConfig,
} from '@epa/platform';
import type { CodeAnalysisProvider } from '@epa/ai-provider';
import { AiSettingsStore } from './ai-settings.js';
import { AuthService, PracticeService, SubmissionService, TemplateCatalog } from '@epa/practice';
import { DockerRdeDriver, LocalRdeDriver, WorkspaceService, type RdeDriver } from '@epa/rde';
import { GitService } from '@epa/git';
import { SnapshotService } from '@epa/snapshots';
import { PlatformEvents, TelemetryIngestion, TimelineService } from '@epa/timeline';
import { DockerSandboxDriver, LocalSandboxDriver, SandboxOrchestrator, type SandboxDriver } from '@epa/sandbox';
import { ReviewService } from '@epa/review';
import { AiOrchestrator } from '@epa/ai-orchestrator';
import { AssessmentService } from '@epa/assessment';
import { RetentionService } from '@epa/retention';
import { DEFAULT_SANDBOX_POLICY, type SandboxPolicy } from '@epa/domain';

export interface PlatformOptions {
  config: PlatformConfig;
  clock?: Clock;
  logger?: Logger;
  db?: Db;
  aiProvider?: CodeAnalysisProvider;
  rdeDriver?: RdeDriver;
  sandboxDriver?: SandboxDriver;
  sandboxPolicy?: SandboxPolicy;
}

export type Platform = Awaited<ReturnType<typeof buildPlatform>>;

export async function buildPlatform(opts: PlatformOptions) {
  const { config } = opts;
  const clock = opts.clock ?? systemClock;
  const log = opts.logger ?? createLogger({ level: config.env === 'test' ? 'error' : 'info' });
  const metrics = new Metrics();
  await mkdir(config.dataDir, { recursive: true });
  const db = opts.db ?? (await createDb(config.databaseUrl));
  await migrate(db);
  const jobs = new JobQueue(db, clock, log, metrics);
  const ctx: Ctx = {
    db,
    clock,
    audit: new AuditLog(clock),
    jobs,
    objects: new FsObjectStore(path.join(config.dataDir, 'objects')),
    signer: new ObjectAccessSigner(config.signingSecret, clock, 60),
    log,
    metrics,
    config,
  };

  const rdeDriver = opts.rdeDriver ?? (config.rdeDriver === 'docker' ? new DockerRdeDriver(config.runtimeImage) : new LocalRdeDriver());
  const sandboxDriver = opts.sandboxDriver ?? (config.sandboxDriver === 'docker' ? new DockerSandboxDriver(config.runtimeImage) : new LocalSandboxDriver());
  if (config.env === 'production' && (!rdeDriver.isolated || !sandboxDriver.isolated)) throw new Error('non-isolated drivers are not allowed in production');
  if (!rdeDriver.isolated || !sandboxDriver.isolated) log.warn('running with NON-ISOLATED local drivers (development only)');
  const aiSettings = new AiSettingsStore(path.join(config.dataDir, 'ai-settings.json'), {
    ollamaUrl: config.ollamaUrl,
    ollamaModel: config.ollamaModel,
    timeoutMs: config.aiTimeoutMs,
  });
  await aiSettings.load();
  const aiProvider = opts.aiProvider ?? aiSettings.provider();

  const templates = new TemplateCatalog(config.templatesDir);
  const auth = new AuthService(ctx);
  const practices = new PracticeService(ctx, auth, templates);
  const git = new GitService(path.join(config.dataDir, 'git'));
  const snapshots = new SnapshotService(ctx);
  const ingestion = new TelemetryIngestion(ctx);
  const events = new PlatformEvents(ctx);
  const timeline = new TimelineService(ctx);
  const workspaces = new WorkspaceService(ctx, rdeDriver, git, snapshots, ingestion, auth, practices, templates);
  const sandbox = new SandboxOrchestrator(ctx, sandboxDriver, snapshots, events, opts.sandboxPolicy ?? DEFAULT_SANDBOX_POLICY);
  let ai: AiOrchestrator;
  const submissions = new SubmissionService(ctx, practices, events, {
    snapshotWorkspace: async (practiceId, workspaceId) => workspaces.snapshot(await practices.load(practiceId), workspaceId, 'pre_submit'),
    headSha: (workspaceId) => workspaces.headSha(workspaceId),
    enqueueSandbox: (q, input) => sandbox.enqueue(q, input),
    enqueueAnalysis: (q, input) => ai.enqueue(q, input),
  });
  ai = new AiOrchestrator(ctx, aiProvider, practices, submissions, snapshots, git, config.setupModel);
  const review = new ReviewService(ctx, practices, submissions, snapshots, events);
  const assessment = new AssessmentService(ctx, practices, timeline, git);
  const retention = new RetentionService(ctx, git);

  const handlers: Partial<Record<JobKind, JobHandler>> = {
    'workspace.provision': (job) => workspaces.provision(job),
    'workspace.teardown': (job) => workspaces.teardown(job.payload.practiceId, job.payload.reason),
    'sandbox.run': (job) => sandbox.handle(job),
    'ai.analyze': (job) => ai.handleAnalyze(job),
    'ai.suggest_tests': (job) => ai.handleSuggest(job),
    'ai.assess_process': (job) => ai.handleProcess(job),
    'ai.review_materials': (job) => ai.handleMaterials(job),
    'ai.suggest_improvements': (job) => ai.handleImprovements(job),
    'ai.evaluate_answer': (job) => ai.handleEvaluate(job),
    'practice.expire_sweep': async () => void (await practices.expireOverdue()),
    'snapshot.interval_sweep': async () => void (await workspaces.intervalSweep()),
    'retention.sweep': async () => void (await retention.sweep()),
  };
  const worker = new Worker(jobs, handlers, log, metrics);

  /** Enqueues periodic maintenance jobs (one per kind per minute bucket). */
  const scheduleMaintenance = async () => {
    const bucket = Math.floor(clock.now().getTime() / 60_000);
    await jobs.enqueue('practice.expire_sweep', {}, { dedupeKey: `expire:${bucket}`, maxAttempts: 1 });
    await jobs.enqueue('snapshot.interval_sweep', {}, { dedupeKey: `snapint:${bucket}`, maxAttempts: 1 });
    if (bucket % 60 === 0) await jobs.enqueue('retention.sweep', {}, { dedupeKey: `retention:${bucket}`, maxAttempts: 3 });
  };

  return {
    ctx,
    config,
    auth,
    templates,
    practices,
    submissions,
    git,
    snapshots,
    ingestion,
    events,
    timeline,
    workspaces,
    sandbox,
    review,
    ai,
    aiProvider,
    aiSettings,
    assessment,
    retention,
    worker,
    rdeDriver,
    sandboxDriver,
    scheduleMaintenance,
    limits: {
      redeem: new RateLimiter(10, 10 / 60, clock),
      api: new RateLimiter(600, 10, clock),
      ingest: new RateLimiter(120, 2, clock),
    },
    async close() {
      await worker.stop();
      await workspaces.shutdown();
      await db.close();
    },
  };
}
