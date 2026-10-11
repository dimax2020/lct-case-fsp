import type { components } from '~/api/schema'

type Grade = components['schemas']['Grade']
type WorkFormat = components['schemas']['WorkFormat']
type Specialization = components['schemas']['Specialization']

export const SPEC_LABEL: Record<Specialization, string> = {
  backend: 'Backend',
  frontend: 'Frontend',
  data_ml: 'Data/ML',
  devops: 'DevOps',
}

export const GRADE_LABEL: Record<Grade, string> = {
  intern: 'Intern',
  junior: 'Junior',
  middle: 'Middle',
  senior: 'Senior',
  lead: 'Lead',
}

export const GRADES: Grade[] = ['intern', 'junior', 'middle', 'senior', 'lead']

export const FORMAT_LABEL: Record<WorkFormat, string> = {
  remote: 'Удалённо',
  hybrid: 'Гибрид',
  office: 'Офис',
}

export const FORMATS: WorkFormat[] = ['remote', 'hybrid', 'office']

export const STATUS_LABEL: Record<string, string> = {
  seeking: 'Ищу работу',
  open: 'Открыт к предложениям',
  paused: 'Поиск на паузе',
}

export const ROLE_LABEL: Record<string, string> = {
  owner: 'Сделал сам',
  contributor: 'В команде',
  participant: 'Участник',
}

export const VERDICT_LABEL: Record<string, string> = {
  OK: 'OK',
  WRONG_ANSWER: 'Неверный ответ',
  TIME_LIMIT: 'Превышено время',
  MEMORY_LIMIT: 'Превышена память',
  COMPILE_ERROR: 'Ошибка компиляции',
  RUNTIME_ERROR: 'Ошибка выполнения',
  PENDING: 'Проверяем',
}

export const SKILL_LABEL: Record<string, string> = {
  python: 'Python',
  go: 'Go',
  javascript: 'JavaScript',
  postgresql: 'PostgreSQL',
  kafka: 'Kafka',
  kubernetes: 'Kubernetes',
  react: 'React',
  docker: 'Docker',
  pytorch: 'PyTorch',
  vue: 'Vue',
}

export function skillLabel(id: string) {
  return SKILL_LABEL[id] ?? id
}

export function categoryLabel(spec?: string | null, grade?: string | null) {
  const s = spec ? (SPEC_LABEL[spec as Specialization] ?? spec) : 'Специализация не выбрана'
  const g = grade ? (GRADE_LABEL[grade as Grade] ?? grade) : ''
  return g ? `${s} · ${g}` : s
}

export function rub(n: number) {
  return `${new Intl.NumberFormat('ru-RU').format(n)} ₽`
}

export function salaryRange(from: number, to: number) {
  return `${new Intl.NumberFormat('ru-RU').format(from)} – ${new Intl.NumberFormat('ru-RU').format(to)} ₽`
}

export function shortDate(iso?: string | null) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('ru-RU')
}

export function whenLabel(iso?: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const diff = Date.now() - d.getTime()
  if (diff < 36e5 * 20) return 'сегодня'
  if (diff < 864e5 * 2) return 'вчера'
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
}

export function scoreColor(n: number) {
  if (n >= 80) return 'var(--success)'
  if (n >= 50) return 'var(--warning)'
  return 'var(--danger)'
}

export function inviteTone(status: string): 'new' | 'review' | 'invite' | 'offer' | 'reject' | 'archived' {
  if (status === 'sent') return 'new'
  if (status === 'viewed') return 'review'
  if (status === 'accepted') return 'offer'
  if (status === 'declined') return 'reject'
  return 'archived'
}

export function inviteLabel(status: string) {
  if (status === 'sent') return 'Отправлено'
  if (status === 'viewed') return 'Просмотрено'
  if (status === 'accepted') return 'Принято'
  if (status === 'declined') return 'Отклонено'
  if (status === 'expired') return 'Истекло'
  if (status === 'revoked') return 'Отозвано'
  return status
}

export function parseMoney(raw: string | number) {
  const n = Number(String(raw).replace(/[^\d]/g, ''))
  return Number.isFinite(n) ? n : NaN
}

export function rememberNeed(id: string) {
  if (import.meta.client) sessionStorage.setItem('fsp-need-id', id)
}

export function rememberedNeed() {
  if (!import.meta.client) return ''
  return sessionStorage.getItem('fsp-need-id') ?? ''
}

export function rememberAttempt(id: string) {
  if (import.meta.client) sessionStorage.setItem('fsp-attempt-id', id)
}

export function rememberedAttempt() {
  if (!import.meta.client) return ''
  return sessionStorage.getItem('fsp-attempt-id') ?? ''
}

export const candidateLinks = [
  { label: 'Профиль', href: '/candidate/profile' },
  { label: 'Тесты и грейд', href: '/candidate/grade' },
  { label: 'Приглашения', href: '/candidate/invites' },
  { label: 'Переписка', href: '/candidate/chat' },
  { label: 'Вакансии', href: '/candidate/vacancy' },
  { label: 'Тестовые задания', href: '/candidate/process' },
  { label: 'Настройки', href: '/candidate/settings' },
]

export const employerLinks = [
  { label: 'Подборка', href: '/employer/need' },
  { label: 'Банк кандидатов', href: '/employer/pool' },
  { label: 'Приглашения', href: '/employer/invites' },
  { label: 'Переписка', href: '/employer/chat' },
  { label: 'Вакансии', href: '/employer/vacancies' },
  { label: 'Тестовые задания', href: '/employer/process' },
  { label: 'Компания', href: '/employer/company' },
]

export function domainLabel(id: string, domains: { id: string; name: string }[] = []) {
  return domains.find(d => d.id === id)?.name ?? id
}

export function longDate(iso?: string | null) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
}
