import type { components } from '~/api/schema'

type Grade = components['schemas']['Grade']
type Spec = components['schemas']['Specialization']
type Task = components['schemas']['TaskPublic']
type View = components['schemas']['AttemptView']
type Result = components['schemas']['AttemptResult']

export const CAT_FORMAT_LABEL: Record<string, string> = {
  MCQ: 'Один вариант',
  MSQ: 'Несколько вариантов',
  SHORT: 'Короткий ответ',
  CODE: 'Код',
  DEBUG: 'Отладка',
  REVIEW: 'Ревью',
  CASE: 'Кейс',
}

export const CAT_DECISION_LABEL: Record<string, string> = {
  passed: 'Грейд подтверждён',
  above: 'Уверенно выше заявленного',
  borderline: 'Пограничная зона',
  below: 'Ниже заявленного',
}

export type CatTask = Task & {
  title?: string | null
  format?: string | null
  time_minutes?: number | null
  tags?: string[]
  multiple?: boolean
  snippet?: string | null
  placeholder?: string | null
}

export type CatMode = 'choice' | 'short' | 'code' | 'text'

export const CAT_MIN_ITEMS = 8
export const CAT_MAX_ITEMS = 20

export function catMode(task: CatTask | null | undefined): CatMode {
  if (task?.options?.length) return 'choice'
  const format = catFormat(task)
  if (format === 'CODE' || (!task?.format && task?.kind === 'code')) return 'code'
  if (format === 'SHORT') return 'short'
  return 'text'
}

export type CatResult = Result & {
  theta?: number | null
  se?: number | null
  decision?: string | null
  measured_grade?: Grade | null
  percentile?: number | null
  message?: string | null
}

export type CatView = View & {
  engine?: string
  theta?: number | null
  se?: number | null
  decision?: string | null
  measured_grade?: Grade | null
  percentile?: number | null
  message?: string | null
  task?: CatTask | null
  result?: CatResult | null
  timer_enabled?: boolean
  time_limit_minutes?: number | null
}

export type Eligibility = {
  can_start: boolean
  reason?: string | null
  active_attempt_id?: string | null
  retry_at?: string | null
  grade_change_at?: string | null
  message?: string | null
}

export type Blueprint = {
  specialization: Spec | string
  grade?: string | null
  theory: number
  practice: number
  debug: number
  case: number
  skills: string[]
  sample: { id: string; title: string; format: string; tags: string[] }[]
  note?: string | null
}

export function catFormat(task: CatTask | null | undefined) {
  const raw = (task?.format || (task?.multiple ? 'MSQ' : task?.kind === 'mcq' ? 'MCQ' : 'SHORT')).toUpperCase()
  return raw
}

export function clock(seconds: number) {
  const safe = Math.max(0, seconds)
  const m = Math.floor(safe / 60)
  const s = safe % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
