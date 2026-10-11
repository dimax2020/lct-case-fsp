import { useRuntimeConfig } from '#imports'
import { createError } from 'h3'

type AssignableRole = 'candidate' | 'employer'

function config() {
  const runtime = useRuntimeConfig()
  return {
    base: String(runtime.keycloakInternalBase || '').replace(/\/$/, ''),
    realm: String(runtime.keycloakRealm || 'fsp'),
    clientId: String(runtime.keycloakClientId || 'career-web'),
    clientSecret: String(runtime.keycloakClientSecret || '')
  }
}

async function serviceAccountToken(): Promise<string> {
  const { base, realm, clientId, clientSecret } = config()
  const response = await fetch(`${base}/realms/${realm}/protocol/openid-connect/token`, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'client_credentials',
      client_id: clientId,
      client_secret: clientSecret
    }),
    signal: AbortSignal.timeout(10000)
  })
  if (!response.ok) {
    throw createError({ statusCode: 502, statusMessage: 'Keycloak не выдал токен сервиса' })
  }
  const body = await response.json() as { access_token?: unknown }
  if (typeof body.access_token !== 'string' || !body.access_token) {
    throw createError({ statusCode: 502, statusMessage: 'Keycloak не выдал токен сервиса' })
  }
  return body.access_token
}

export async function assignRealmRole(userId: string, role: AssignableRole): Promise<void> {
  const { base, realm } = config()
  const token = await serviceAccountToken()
  const headers = { authorization: `Bearer ${token}`, accept: 'application/json' }
  const roleResponse = await fetch(`${base}/admin/realms/${realm}/roles/${role}`, {
    headers,
    signal: AbortSignal.timeout(10000)
  })
  if (!roleResponse.ok) {
    throw createError({ statusCode: 502, statusMessage: 'Не удалось прочитать роль Keycloak' })
  }
  const roleBody = await roleResponse.json() as { id?: unknown, name?: unknown }
  if (typeof roleBody.id !== 'string' || typeof roleBody.name !== 'string') {
    throw createError({ statusCode: 502, statusMessage: 'Не удалось прочитать роль Keycloak' })
  }
  const mapResponse = await fetch(`${base}/admin/realms/${realm}/users/${encodeURIComponent(userId)}/role-mappings/realm`, {
    method: 'POST',
    headers: { ...headers, 'content-type': 'application/json' },
    body: JSON.stringify([{ id: roleBody.id, name: roleBody.name }]),
    signal: AbortSignal.timeout(10000)
  })
  if (!mapResponse.ok) {
    throw createError({ statusCode: 502, statusMessage: 'Не удалось назначить роль' })
  }
}
