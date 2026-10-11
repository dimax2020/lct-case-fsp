export type EpaPractice = {
  id: string
  title: string
  sourcePracticeId?: string | null
  candidateId?: string | null
}

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

export function safeReturnPath(value: unknown) {
  if (typeof value !== 'string') return ''
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('\\') || value.includes('\n') || value.includes('\r')) return ''
  return value.slice(0, 512)
}
