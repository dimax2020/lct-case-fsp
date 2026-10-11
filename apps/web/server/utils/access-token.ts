import { useStorage } from '#imports'
import { getCookie, type H3Event } from 'h3'
import { decryptToken } from 'nuxt-oidc-auth/runtime/server/utils/security.js'
import { getUserSessionId } from 'nuxt-oidc-auth/runtime/server/utils/session.js'

const SESSION_COOKIE = 'nuxt-oidc-auth'

interface EncryptedToken {
  encryptedToken: string
  iv: string
}

interface PersistentSession {
  accessToken?: EncryptedToken
  idToken?: EncryptedToken
}

export function jwtPayload(token: string): Record<string, unknown> {
  const part = token.split('.')[1]
  if (!part) return {}
  try {
    const parsed: unknown = JSON.parse(Buffer.from(part, 'base64url').toString('utf8'))
    return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : {}
  } catch {
    return {}
  }
}

export type BusinessRole = 'admin' | 'employer' | 'candidate'

const ROLE_PRIORITY: BusinessRole[] = ['admin', 'employer', 'candidate']

export function businessRole(token: string): BusinessRole | null {
  const realm = jwtPayload(token).realm_access
  if (!realm || typeof realm !== 'object') return null
  const roles = (realm as { roles?: unknown }).roles
  if (!Array.isArray(roles)) return null
  for (const role of ROLE_PRIORITY) {
    if (roles.includes(role)) return role
  }
  return null
}

export function tokenSubject(token: string): string | null {
  const sub = jwtPayload(token).sub
  return typeof sub === 'string' && sub.length > 0 && sub.length < 128 && !/\s/.test(sub) ? sub : null
}

async function readStoredToken(event: H3Event, field: 'accessToken' | 'idToken'): Promise<string | undefined> {
  if (!getCookie(event, SESSION_COOKIE)) return undefined
  const key = process.env.NUXT_OIDC_TOKEN_KEY
  if (!key) return undefined
  const sessionId = await getUserSessionId(event)
  const stored = await useStorage<PersistentSession>('oidc').getItem(sessionId)
  const encrypted = stored?.[field]
  if (!encrypted) return undefined
  try {
    return await decryptToken(encrypted, key)
  } catch {
    return undefined
  }
}

export async function readAccessToken(event: H3Event): Promise<string | undefined> {
  return readStoredToken(event, 'accessToken')
}

export async function readIdToken(event: H3Event): Promise<string | undefined> {
  return readStoredToken(event, 'idToken')
}
