import path from 'node:path';
import { randomBytes } from 'node:crypto';

export interface PlatformConfig {
  env: 'development' | 'test' | 'production';
  port: number;
  publicUrl: string;
  dataDir: string;
  databaseUrl: string;
  signingSecret: string;
  rdeDriver: 'docker' | 'local';
  sandboxDriver: 'docker' | 'local';
  runtimeImage: string;
  ollamaUrl: string;
  ollamaModel: string;
  setupModel: string;
  aiTimeoutMs: number;
  defaultRetentionDays: number;
  embeddedWorker: boolean;
  templatesDir: string;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env, overrides: Partial<PlatformConfig> = {}): PlatformConfig {
  const mode = (env.NODE_ENV as PlatformConfig['env']) ?? 'development';
  const dataDir = path.resolve(env.EPA_DATA_DIR ?? 'data');
  let signingSecret = env.EPA_SIGNING_SECRET ?? '';
  if (!signingSecret) {
    if (mode === 'production') throw new Error('EPA_SIGNING_SECRET is required in production');
    signingSecret = randomBytes(32).toString('hex');
  }
  const defaultDriver: PlatformConfig['rdeDriver'] = mode === 'production' ? 'docker' : 'local';
  const rdeDriver = (env.EPA_RDE_DRIVER as PlatformConfig['rdeDriver']) ?? defaultDriver;
  const sandboxDriver = (env.EPA_SANDBOX_DRIVER as PlatformConfig['sandboxDriver']) ?? defaultDriver;
  if (mode === 'production' && (rdeDriver === 'local' || sandboxDriver === 'local')) {
    throw new Error('local (non-isolated) drivers are forbidden in production');
  }
  return {
    env: mode,
    port: Number(env.PORT ?? 8080),
    publicUrl: env.EPA_PUBLIC_URL ?? `http://localhost:${env.PORT ?? 8080}`,
    dataDir,
    databaseUrl: env.DATABASE_URL ?? `pglite://${path.join(dataDir, 'db')}`,
    signingSecret,
    rdeDriver,
    sandboxDriver,
    runtimeImage: env.EPA_RUNTIME_IMAGE ?? 'node:20-alpine',
    ollamaUrl: env.OLLAMA_URL ?? 'http://127.0.0.1:11434',
    ollamaModel: env.OLLAMA_MODEL ?? 'qwen2.5-coder:0.5b',
    setupModel: env.OLLAMA_SETUP_MODEL ?? 'qwen2.5-coder:0.5b',
    aiTimeoutMs: Number(env.EPA_AI_TIMEOUT_MS ?? 600_000),
    defaultRetentionDays: Number(env.EPA_RETENTION_DAYS ?? 90),
    embeddedWorker: (env.EPA_EMBEDDED_WORKER ?? 'true') === 'true',
    templatesDir: path.resolve(env.EPA_TEMPLATES_DIR ?? 'packages/test-fixtures/templates'),
    ...overrides,
  };
}
