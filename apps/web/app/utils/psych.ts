// Типы и подписи теста рабочего стиля. Ответы API описаны в contracts/openapi.yaml (тег psych).

export type DiscScale = 'D' | 'I' | 'S' | 'C'
export type PsychScale = 'leadership' | 'teamwork' | 'stress' | 'diligence'
export type PsychLevel = 'low' | 'mid' | 'high'
export type Letter = 'а' | 'б' | 'в' | 'г'

export interface PsychItem { key: Letter; text: string }
export interface PsychTest {
  version: string
  title: string
  subtitle: string
  instruction: string
  parts: { id: number; title: string; meta: string; hint: string }[]
  blocks: { id: number; items: PsychItem[] }[]
  statements: { id: number; text: string }[]
  likert: { value: number; label: string }[]
  cases: { id: number; text: string; options: PsychItem[] }[]
}

export interface PsychAnswers {
  disc: Record<string, { most?: Letter; least?: Letter }>
  statements: Record<string, number>
  cases: Record<string, Letter>
}

export interface PsychProgress {
  blocks_done: number
  blocks_total: number
  statements_done: number
  statements_total: number
  cases_done: number
  cases_total: number
}

export interface PsychAttempt {
  id: string
  version: string
  answers: PsychAnswers
  progress: PsychProgress
  started_at: string
  finished_at?: string | null
}

export interface DiscRow { scale: DiscScale; sum: number; pct: number; color: string; color_name: string; title: string; text: string }
export interface ScaleRow {
  scale: PsychScale
  title: string
  pct: number
  level: PsychLevel
  level_title: string
  level_text: string
  statements?: number
  situations?: number
  raw?: number
  min?: number
  max?: number
}
export interface FitRow {
  id: string
  title: string
  disc: string
  weights: Record<PsychScale, number>
  index: number
  level: PsychLevel
  level_title: string
}
export interface PsychResult {
  version: string
  disc: DiscRow[]
  disc_profile: { balanced: boolean; primary: DiscScale[]; secondary: DiscScale[]; label: string }
  scales: ScaleRow[]
  fits: FitRow[]
  // Только в ответе для работодателя:
  social_desirability?: { sum: number; pct: number; flag: boolean }
  flags?: { id: string; text: string }[]
  skipped?: { disc: number; statements: number; cases: number; total: number }
  duration_seconds?: number | null
  reliable?: boolean
}

export interface PsychState {
  attempt: PsychAttempt | null
  result: PsychResult | null
  finished_at: string | null
  can_start: boolean
  next_attempt_at: string | null
  share_with_employers: boolean
  limitations: string[]
}

export interface PsychEmployerView {
  available: boolean
  reason: string | null
  finished_at: string | null
  result: PsychResult | null
  limitations: string[]
}

export const DISC_COLOR: Record<DiscScale, string> = {
  D: 'var(--disc-red)',
  I: 'var(--disc-yellow)',
  S: 'var(--disc-green)',
  C: 'var(--disc-blue)',
}

export function levelColor(level: PsychLevel) {
  if (level === 'high') return 'var(--success)'
  if (level === 'mid') return 'var(--warning)'
  return 'var(--danger)'
}

export function emptyAnswers(): PsychAnswers {
  return { disc: {}, statements: {}, cases: {} }
}

export function minutesSince(iso?: string | null) {
  if (!iso) return 0
  const start = new Date(iso).getTime()
  if (Number.isNaN(start)) return 0
  return Math.max(0, Math.floor((Date.now() - start) / 60000))
}
