import { z } from 'zod';
import { isSafeRelativePath } from '@epa/domain';

export const API_VERSION = 'v1';

const relPath = z.string().min(1).max(512).refine(isSafeRelativePath, { message: 'unsafe path' });
const futureIso = z.iso.datetime({ offset: true });

export const createPracticeReq = z.strictObject({
  title: z.string().min(3).max(200),
  description: z.string().max(20_000).default(''),
  rules: z.string().max(5000).default(''),
  template: z.string().regex(/^[a-z0-9-]{1,64}$/).default('blank'),
  deadline: futureIso,
  testCommand: z.array(z.string().min(1).max(200)).min(1).max(20).optional(),
  coverage: z.boolean().default(false),
  snapshotPolicy: z
    .strictObject({
      intervalSec: z.number().int().min(10).max(3600).optional(),
      significantSaveBytes: z.number().int().min(1).max(1_000_000).optional(),
      checkpointEvery: z.number().int().min(1).max(100).optional(),
    })
    .optional(),
  workspacePolicy: z
    .strictObject({
      cpus: z.number().optional(),
      memoryMb: z.number().int().optional(),
      sessionTtlMinutes: z.number().int().optional(),
      commandTimeoutSec: z.number().int().optional(),
    })
    .optional(),
});
export type CreatePracticeReq = z.infer<typeof createPracticeReq>;

export const createInviteReq = z.strictObject({
  candidateEmail: z.email().max(320).optional(),
  expiresInHours: z.number().int().min(1).max(24 * 30).default(72),
});

export const redeemInviteReq = z.strictObject({ token: z.string().min(20).max(200) });

export const briefReq = z.strictObject({
  text: z.string().min(1).max(100_000),
  name: z.string().trim().min(1).max(200).optional(),
  review: z.boolean().optional(),
});

export const materialsReq = z
  .strictObject({
    title: z.string().trim().min(3).max(200).optional(),
    description: z.string().max(20_000).optional(),
    notes: z.string().max(20_000).optional(),
  })
  .refine((v) => v.title !== undefined || v.description !== undefined || v.notes !== undefined, { message: 'нет полей' });

export const displayName = z.string().trim().min(1).max(80);

export const loginReq = z.strictObject({
  name: displayName,
  role: z.enum(['employer', 'candidate']),
});

export const extensionUsername = z.string().trim().min(3).max(40).regex(/^[A-Za-z0-9._-]+$/, { message: 'логин: латиница, цифры, точка, _ или -' });

export const registerReq = z.strictObject({
  token: z.string().min(20).max(200),
  name: displayName,
  username: extensionUsername,
  password: z.string().min(8).max(200),
});

export const extensionCredentialsReq = z.strictObject({
  username: extensionUsername,
  password: z.string().min(8).max(200),
});

export const extensionLoginReq = z.strictObject({
  username: extensionUsername,
  password: z.string().min(1).max(200),
});

export const vscodeSubmitReq = z.strictObject({
  snapshotId: z.string().min(1).max(100).regex(/^[A-Za-z0-9_:-]+$/),
});

export const acceptConsentReq = z.strictObject({ consentVersion: z.string().max(50), textHash: z.string().regex(/^[a-f0-9]{64}$/), accepted: z.literal(true) });

export const writeFileReq = z.strictObject({
  path: relPath,
  content: z.string().max(5 * 1024 * 1024),
  editorStats: z
    .strictObject({ pastedChars: z.number().int().min(0).max(10_000_000).default(0) })
    .optional(),
});

export const runCommandReq = z.strictObject({ command: z.string().min(1).max(2000) });
export const commitReq = z.strictObject({ message: z.string().min(1).max(2000) });

export const createCommentReq = z.strictObject({
  filePath: relPath,
  lineStart: z.number().int().min(1),
  lineEnd: z.number().int().min(1),
  body: z.string().min(1).max(5000),
});

export const requirementChangeReq = z.strictObject({
  text: z.string().min(1).max(10_000),
  reason: z.string().min(1).max(2000),
  acceptanceCriteria: z.array(z.string().min(1).max(500)).min(1).max(20),
  dueAt: futureIso,
});

export const interviewAnswerReq = z.strictObject({ text: z.string().min(1).max(10_000) });

export const paginationQuery = z.object({
  cursor: z.string().max(500).optional(),
  limit: z.coerce.number().int().min(1).max(200).default(50),
});

export const fileQuery = z.object({ path: relPath });
