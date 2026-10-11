import type { H3Event } from 'h3'
import { businessRole, jwtPayload, readAccessToken, readIdToken } from './access-token'

export async function publicSession(event: H3Event) {
  const access = await readAccessToken(event)
  const id = await readIdToken(event)
  const token = access || id
  if (!token) return { authenticated: false as const }
  const payload = jwtPayload(id || access || '')
  const email = typeof payload.email === 'string' ? payload.email : null
  const preferred = typeof payload.preferred_username === 'string' ? payload.preferred_username : null
  const name = typeof payload.name === 'string' ? payload.name : preferred
  const exp = jwtPayload(access || id || '').exp
  return {
    authenticated: true as const,
    role: (access && businessRole(access)) || (id && businessRole(id)) || null,
    email,
    name,
    provider: 'keycloak' as const,
    expireAt: typeof exp === 'number' ? exp : null,
  }
}
