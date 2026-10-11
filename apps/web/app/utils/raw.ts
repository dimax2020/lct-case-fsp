import { ApiError, errorMessage } from '~/utils/read'

export type QueryValue = string | number | boolean | null | undefined

function mocksEnabled() {
  if (import.meta.server) {
    const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    return env?.NUXT_PUBLIC_API_MOCKS === '1'
  }
  const pub = import.meta.env as unknown as Record<string, string | undefined>
  return pub.NUXT_PUBLIC_API_MOCKS === '1'
}

function origin() {
  return import.meta.client ? window.location.origin : ''
}

function withQuery(path: string, query?: Record<string, QueryValue>) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const qs = params.toString()
  return `${origin()}${path}${qs ? `?${qs}` : ''}`
}

function failure(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  const wrapped = error as { statusCode?: number; status?: number; data?: unknown; message?: string }
  const status = wrapped.statusCode ?? wrapped.status ?? 0
  const message = wrapped.data == null
    ? (wrapped.message || errorMessage(null, status))
    : errorMessage(wrapped.data, status)
  return new ApiError(status, message)
}

export async function apiFetch<T>(path: string, init: { method?: string; body?: unknown; query?: Record<string, QueryValue> } = {}): Promise<T> {
  const target = withQuery(path, init.query)
  const method = init.method ?? 'GET'
  if (mocksEnabled()) {
    const { mockFetch } = await import('~/api/mock/handle')
    const res = await mockFetch(new Request(target || path, {
      method,
      credentials: 'include',
      headers: init.body !== undefined ? { 'content-type': 'application/json' } : undefined,
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    }))
    const text = await res.text()
    let data: unknown = null
    if (text) {
      try {
        data = JSON.parse(text) as unknown
      } catch {
        data = { message: text }
      }
    }
    if (!res.ok) throw new ApiError(res.status, errorMessage(data, res.status))
    return data as T
  }
  try {
    return await $fetch<T>(target, {
      method: method as 'GET',
      credentials: 'include',
      body: init.body as Record<string, unknown> | undefined,
    })
  } catch (error) {
    throw failure(error)
  }
}

export async function apiBlob(path: string): Promise<Blob> {
  const target = `${origin()}${path}`
  if (mocksEnabled()) {
    const { mockFetch } = await import('~/api/mock/handle')
    const res = await mockFetch(new Request(target || path, { credentials: 'include' }))
    if (!res.ok) {
      const data = await res.json().catch(() => null)
      throw new ApiError(res.status, errorMessage(data, res.status))
    }
    return res.blob()
  }
  try {
    return await $fetch<Blob>(target, { credentials: 'include', responseType: 'blob' })
  } catch (error) {
    throw failure(error)
  }
}

export function asList<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === 'object' && Array.isArray((data as { items?: unknown }).items)) {
    return (data as { items: T[] }).items
  }
  return []
}
