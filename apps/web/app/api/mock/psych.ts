// Мок-версия подсчёта теста рабочего стиля для режима без бэкенда (NUXT_PUBLIC_API_MOCKS=1).
// Повторяет services/api/app/psych/scoring.py; ключ выгружен скриптом services/api/scripts/export_psych_bank.py.
import bank from '~/api/mock/psych-bank.json'
import type { Letter, PsychAnswers, PsychResult, PsychScale } from '~/utils/psych'

type Key = typeof bank.key
const LETTERS: Letter[] = ['а', 'б', 'в', 'г']
const SCALES: PsychScale[] = ['leadership', 'teamwork', 'stress', 'diligence']
const DISC = ['D', 'I', 'S', 'C'] as const

export const PSYCH_PUBLIC = bank.public
export const PSYCH_LIMITATIONS: string[] = bank.key.limitations

const round = (value: number) => Math.floor(value + 0.5)
const level = (pct: number) => (pct <= 33 ? 'low' : pct <= 66 ? 'mid' : 'high') as 'low' | 'mid' | 'high'

export function cleanAnswers(raw: Partial<PsychAnswers> | undefined): PsychAnswers {
  const out: PsychAnswers = { disc: {}, statements: {}, cases: {} }
  for (let b = 1; b <= 12; b++) {
    const item = raw?.disc?.[String(b)]
    if (!item) continue
    const most = LETTERS.includes(item.most as Letter) ? item.most : undefined
    const least = LETTERS.includes(item.least as Letter) && item.least !== most ? item.least : undefined
    if (most || least) out.disc[String(b)] = { ...(most ? { most } : {}), ...(least ? { least } : {}) }
  }
  for (let n = 1; n <= 30; n++) {
    const v = raw?.statements?.[String(n)]
    if (typeof v === 'number' && Number.isInteger(v) && v >= 1 && v <= 5) out.statements[String(n)] = v
  }
  for (let n = 1; n <= 5; n++) {
    const v = raw?.cases?.[String(n)]
    if (v && LETTERS.includes(v)) out.cases[String(n)] = v
  }
  return out
}

export function progressOf(a: PsychAnswers) {
  return {
    blocks_done: Object.values(a.disc).filter(x => x.most && x.least).length,
    blocks_total: 12,
    statements_done: Object.keys(a.statements).length,
    statements_total: 30,
    cases_done: Object.keys(a.cases).length,
    cases_total: 5,
  }
}

function imputed(given: Record<string, number>, items: [number, boolean][]) {
  const pts = items.filter(([n]) => given[String(n)] != null).map(([n, rev]) => (rev ? 6 - given[String(n)]! : given[String(n)]!))
  if (!pts.length) return 3 * items.length
  const mean = pts.reduce((s, x) => s + x, 0) / pts.length
  return pts.reduce((s, x) => s + x, 0) + mean * (items.length - pts.length)
}

function bounds(key: Key, scale: PsychScale) {
  const st = key.statements[scale]
  const count = st.direct.length + st.reverse.length
  let lo = 0
  let hi = 0
  for (const c of key.cases) {
    c.scales.forEach((name, slot) => {
      if (name !== scale) return
      const vals = c.points.map(p => p[slot]!)
      lo += Math.min(...vals)
      hi += Math.max(...vals)
    })
  }
  return [count + lo, count * 5 + hi] as const
}

const num = (v: number) => Math.floor(v * 10 + 0.5) / 10

export function scoreMock(raw: PsychAnswers, durationSeconds: number): PsychResult {
  const key = bank.key
  const a = cleanAnswers(raw)
  const sums: Record<string, number> = { D: 0, I: 0, S: 0, C: 0 }
  let discSkipped = 0
  key.disc.forEach((block, i) => {
    const item = a.disc[String(i + 1)]
    if (!item?.most || !item.least) { discSkipped++; return }
    sums[block[LETTERS.indexOf(item.most)]!]! += 1
    sums[block[LETTERS.indexOf(item.least)]!]! -= 1
  })
  const info = key.disc_info as Record<string, { color: string; color_name: string; title: string; text: string }>
  const disc = DISC.map(scale => ({ scale, sum: sums[scale]!, pct: round((sums[scale]! + 12) / 24 * 100), ...info[scale]! }))

  const ordered = [...DISC].sort((x, y) => sums[y]! - sums[x]! || DISC.indexOf(x) - DISC.indexOf(y))
  let profile: PsychResult['disc_profile']
  if (DISC.every(s => sums[s]! >= -2 && sums[s]! <= 2)) {
    profile = { balanced: true, primary: [], secondary: [], label: 'Сбалансированный профиль' }
  } else {
    const top = sums[ordered[0]!]!
    const tied = ordered.filter(s => sums[s] === top)
    if (tied.length > 1) {
      const label = tied.map(s => info[s]!.color_name.toLowerCase()).join(' и ')
      profile = { balanced: false, primary: tied, secondary: [], label: label[0]!.toUpperCase() + label.slice(1) + ' (равнозначно)' }
    } else {
      const second = sums[ordered[1]!]!
      const secondary = second > 0 && top - second <= 3 ? ordered.slice(1).filter(s => sums[s] === second) : []
      const prefix: Record<string, string> = { D: 'Красно', I: 'Жёлто', S: 'Зелёно', C: 'Сине' }
      let label = secondary.length ? `${prefix[ordered[0]!]}-${info[secondary[0]!]!.color_name.toLowerCase()}` : info[ordered[0]!]!.color_name
      if (secondary.length > 1) label += ` / ${info[secondary[1]!]!.color_name.toLowerCase()}`
      profile = { balanced: false, primary: [ordered[0]!], secondary, label }
    }
  }

  const statementPart: Record<string, number> = {}
  for (const scale of SCALES) {
    const st = key.statements[scale]
    statementPart[scale] = imputed(a.statements, [...st.direct.map(n => [n, false] as [number, boolean]), ...st.reverse.map(n => [n, true] as [number, boolean])])
  }
  const social = imputed(a.statements, key.social_items.map(n => [n, false] as [number, boolean]))
  const casePart: Record<string, number> = { leadership: 0, teamwork: 0, stress: 0, diligence: 0 }
  let casesSkipped = 0
  key.cases.forEach((c, i) => {
    const letter = a.cases[String(i + 1)]
    const [first, second] = c.scales as [PsychScale, PsychScale]
    if (!letter) {
      casesSkipped++
      casePart[first]! += c.points.reduce((s, p) => s + p[0]!, 0) / c.points.length
      casePart[second]! += c.points.reduce((s, p) => s + p[1]!, 0) / c.points.length
      return
    }
    const p = c.points[LETTERS.indexOf(letter)]!
    casePart[first]! += p[0]!
    casePart[second]! += p[1]!
  })
  const levels = key.levels as Record<string, string[]>
  const percents: Record<string, number> = {}
  const scales = SCALES.map((scale) => {
    const rawScore = statementPart[scale]! + casePart[scale]!
    const [lo, hi] = bounds(key, scale)
    const pct = Math.max(0, Math.min(100, round((rawScore - lo) / (hi - lo) * 100)))
    percents[scale] = pct
    const lv = level(pct)
    return {
      scale, title: key.scale_info[scale].title, statements: num(statementPart[scale]!), situations: num(casePart[scale]!),
      raw: num(rawScore), min: lo, max: hi, pct, level: lv, level_title: levels[lv]![0]!, level_text: levels[lv]![1]!,
    }
  })
  const fits = key.fits.map((f) => {
    const weights = f.weights as Record<PsychScale, number>
    const index = round(SCALES.reduce((s, sc) => s + weights[sc] * percents[sc]!, 0) / 100)
    const lv = index >= 70 ? 'high' : index >= 50 ? 'mid' : 'low'
    return { id: f.id, title: f.title, disc: f.disc, weights, index, level: lv as 'low' | 'mid' | 'high', level_title: lv === 'high' ? 'Высокое' : lv === 'mid' ? 'Среднее' : 'Низкое' }
  })
  const flags: { id: string; text: string }[] = []
  if (social >= key.social_flag) flags.push({ id: 'social_desirability', text: `Социальная желательность ${num(social)} из 20: возможно приукрашивание, уточните результаты на интервью.` })
  let best = 0
  let run = 0
  let prev: number | null = null
  for (let n = 1; n <= 30; n++) {
    const v = a.statements[String(n)]
    if (v == null) { run = 0; prev = null; continue }
    run = v === prev ? run + 1 : 1
    prev = v
    best = Math.max(best, run)
  }
  if (best >= 10) flags.push({ id: 'straight_line', text: `${best} одинаковых ответов подряд в части 2.` })
  const minutes = durationSeconds / 60
  if (minutes < 8) flags.push({ id: 'too_fast', text: `Тест пройден за ${Math.max(1, round(minutes))} мин — быстрее 8 минут.` })
  else if (minutes > 40) flags.push({ id: 'too_slow', text: `Тест занял ${round(minutes)} мин — дольше 40 минут, вероятно с перерывами.` })
  const statementsSkipped = 30 - Object.keys(a.statements).length
  const total = discSkipped + statementsSkipped + casesSkipped
  if (total > 3) flags.push({ id: 'skips', text: `Пропущено пунктов: ${total}. Тест лучше пройти заново.` })
  return {
    version: bank.public.version,
    disc,
    disc_profile: profile,
    scales,
    fits,
    social_desirability: { sum: num(social), pct: Math.max(0, Math.min(100, round((social - 4) / 16 * 100))), flag: social >= key.social_flag },
    flags,
    skipped: { disc: discSkipped, statements: statementsSkipped, cases: casesSkipped, total },
    duration_seconds: Math.round(durationSeconds),
    reliable: flags.length === 0,
  }
}

export function candidateView(result: PsychResult): PsychResult {
  return {
    version: result.version,
    disc: result.disc,
    disc_profile: result.disc_profile,
    fits: result.fits,
    scales: result.scales.map(({ scale, title, pct, level, level_title, level_text }) => ({ scale, title, pct, level, level_title, level_text })),
  }
}
