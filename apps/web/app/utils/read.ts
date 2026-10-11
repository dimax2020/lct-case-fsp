export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function errorMessage(error: unknown, status: number) {
  if (error && typeof error === 'object') {
    const body = error as {
      error?: { message?: string }
      message?: string
      detail?: { msg?: string }[]
    }
    if (body.error?.message) return body.error.message
    if (Array.isArray(body.detail) && body.detail.length) {
      return body.detail.map(d => d.msg).filter(Boolean).join('; ') || `Ошибка ${status}`
    }
    if (typeof body.message === 'string' && body.message) return body.message
  }
  if (status === 401) return 'Нужно войти'
  if (status === 403) return 'Недостаточно прав'
  if (status === 404) return 'Не найдено'
  if (status === 409) return 'Действие конфликтует с текущим статусом'
  return `Ошибка ${status}`
}

export async function read<T>(pending: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const res = await pending
  if (res.response.ok) return res.data as T
  throw new ApiError(res.response.status, errorMessage(res.error, res.response.status))
}

export function useApiMocks() {
  const state = useState('fsp-api-mocks', () => {
    if (import.meta.server) {
      const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
      return env?.NUXT_PUBLIC_API_MOCKS === '1'
    }
    const pub = import.meta.env as unknown as Record<string, string | undefined>
    return pub.NUXT_PUBLIC_API_MOCKS === '1'
  })
  return state.value
}
