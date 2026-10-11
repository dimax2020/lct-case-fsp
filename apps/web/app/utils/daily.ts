export type DailyStory = {
  id: string
  day: string
  skill_id: string
  skill_label: string
  prompt: string
  answer: string
  answered_at: string
  boost_until: string
}

export type DailyTask = {
  day: string
  prompt: string
  skill_id: string
  skill_label: string
  hint: string
  answered: boolean
  answer?: string | null
  boost_active: boolean
  boost_until?: string | null
  stories?: DailyStory[]
}

export function boostUntilLabel(iso?: string | null) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const shown = new Date(date.getTime() - 86400000)
  return shown.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })
}
