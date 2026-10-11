export type EpaPractice = {
  id: string
  title: string
  deadline?: string
  status?: string
  sourcePracticeId?: string | null
  candidateId?: string | null
  candidateEmail?: string | null
}

const DEFAULT_RULES = 'Работайте в VS Code с расширением EPA. Телеметрия ограничена открытой папкой задания.'

export async function loginEpa(name: string, role: 'employer' | 'candidate') {
  const session = await $fetch<{ token: string; role: string }>('/v1/auth/login', {
    method: 'POST',
    body: { name, role },
  })
  if (import.meta.client) {
    sessionStorage.setItem('epa.token', session.token)
    sessionStorage.setItem('epa.role', session.role)
    sessionStorage.setItem('epa.displayName', name)
  }
  return session
}

export async function listEmployerPractices(name: string) {
  const session = await loginEpa(name, 'employer')
  const page = await $fetch<{ items?: EpaPractice[] }>('/v1/practices?limit=50', {
    headers: { Authorization: `Bearer ${session.token}` },
  })
  return (page.items ?? []).filter(item => !item.sourcePracticeId && !item.candidateId)
}

export async function createEmployerPractice(
  name: string,
  input: { title: string; deadline: string; description?: string; rules?: string },
) {
  const session = await loginEpa(name, 'employer')
  return $fetch<EpaPractice>('/v1/practices', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${session.token}`,
      'Idempotency-Key': crypto.randomUUID(),
    },
    body: {
      title: input.title,
      deadline: input.deadline,
      description: input.description ?? '',
      rules: input.rules ?? DEFAULT_RULES,
    },
  })
}

export function safeReturnPath(value: unknown) {
  if (typeof value !== 'string') return ''
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('\\') || value.includes('\n') || value.includes('\r')) return ''
  return value.slice(0, 512)
}

export function withQuery(path: string, key: string, value: string) {
  const url = new URL(path, 'https://fsp.local')
  url.searchParams.set(key, value)
  return `${url.pathname}${url.search}${url.hash}`
}

export function readPracticeHash(hash = '') {
  const match = hash.match(/practice=([^&]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export function localDeadline(plusDays = 7) {
  const date = new Date(Date.now() + plusDays * 86400000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function localToIso(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) throw new Error('Укажите дедлайн')
  return date.toISOString()
}
