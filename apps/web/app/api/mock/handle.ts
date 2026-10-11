import type { components } from '~/api/schema'
import {
  IDS,
  type AttemptRec,
  type Db,
  type PoolPerson,
  correctOption,
  getDb,
  saveDb,
  taskById,
  taskOrder,
  uid,
} from '~/api/mock/db'
import { PSYCH_LIMITATIONS, PSYCH_PUBLIC, candidateView, cleanAnswers, progressOf, scoreMock } from '~/api/mock/psych'
import type { PsychAnswers, PsychResult } from '~/utils/psych'

type S = components['schemas']

const LADDER: S['Grade'][] = ['intern', 'junior', 'middle', 'senior', 'lead']

const SKILLS: S['SkillHit'][] = [
  { id: 'python', name: 'Python', synonyms: ['python', 'питон', 'py'], specializations: ['backend', 'data_ml'] },
  { id: 'go', name: 'Go', synonyms: ['go', 'golang', 'го'], specializations: ['backend', 'devops'] },
  { id: 'javascript', name: 'JavaScript', synonyms: ['javascript', 'js'], specializations: ['frontend'] },
  { id: 'postgresql', name: 'PostgreSQL', synonyms: ['postgresql', 'postgres', 'постгрес'], specializations: ['backend', 'data_ml'] },
  { id: 'kafka', name: 'Kafka', synonyms: ['kafka', 'кафка'], specializations: ['backend', 'data_ml'] },
  { id: 'kubernetes', name: 'Kubernetes', synonyms: ['kubernetes', 'k8s', 'кубер'], specializations: ['devops', 'backend'] },
  { id: 'react', name: 'React', synonyms: ['react', 'reactjs'], specializations: ['frontend'] },
  { id: 'docker', name: 'Docker', synonyms: ['docker', 'докер'], specializations: ['devops', 'backend'] },
  { id: 'pytorch', name: 'PyTorch', synonyms: ['pytorch', 'torch'], specializations: ['data_ml'] },
  { id: 'vue', name: 'Vue', synonyms: ['vue', 'vuejs'], specializations: ['frontend'] },
]

export async function mockFetch(input: Request) {
  const db = getDb()
  const url = new URL(input.url)
  const path = url.pathname.replace(/\/$/, '') || '/'
  const method = input.method.toUpperCase()
  const response = await route(db, method, path, url, input)
  saveDb()
  return response
}

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function fail(status: number, message: string, code = 'error') {
  return json({ error: { code, message } }, status)
}

async function readBody<T>(req: Request): Promise<T> {
  const text = await req.text()
  if (!text) return {} as T
  return JSON.parse(text) as T
}

function qstr(url: URL, name: string) {
  const value = url.searchParams.get(name)
  return value == null || value === '' ? null : value
}

function qbool(url: URL, name: string) {
  const value = url.searchParams.get(name)
  return value === 'true' || value === '1'
}

function qint(url: URL, name: string) {
  const value = url.searchParams.get(name)
  if (!value) return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function take(match: RegExpMatchArray, index = 1) {
  const value = match[index]
  return typeof value === 'string' ? value : ''
}

function role() {
  if (!import.meta.client) return 'candidate'
  return sessionStorage.getItem('fsp-mock-role') === 'employer' ? 'employer' : 'candidate'
}

function me(): S['Me'] {
  if (role() === 'employer') {
    return {
      sub: 'employer-demo', role: 'employer', email: 'employer@demo.fsp',
      user_id: IDS.userE, candidate_id: null, company_id: IDS.company,
    }
  }
  return {
    sub: 'candidate-demo', role: 'candidate', email: 'candidate@demo.fsp',
    user_id: IDS.userC, candidate_id: IDS.candidate, company_id: null,
  }
}

function eligibility(profile: S['CandidateProfile']) {
  profile.in_pool_eligible = (profile.min_salary ?? 0) > 0 && (profile.formats?.length ?? 0) > 0 && profile.visible && profile.status !== 'paused'
}

function initials(full: string) {
  const parts = full.trim().split(/\s+/)
  if (parts.length < 2 || !parts[1]) return full
  return `${parts[0]} ${parts[1].slice(0, 1)}.`
}

function present(db: Db, inv: S['InvitationOut']): S['InvitationOut'] {
  const person = db.people.find(p => p.candidate_id === inv.candidate_id)
  const open = inv.status === 'accepted'
  return {
    ...inv,
    candidate_email: open ? person?.email ?? null : null,
    candidate_phone: open ? person?.phone ?? null : null,
    recruiter_contact: open ? db.company.recruiter_contact?.email ?? null : null,
  }
}

function attemptView(rec: AttemptRec): S['AttemptView'] {
  const answered = rec.answers.filter(a => !a.skip).length
  const skipped = rec.answers.filter(a => a.skip).length
  const seen = new Set(rec.answers.map(a => a.task_id))
  const currentId = rec.finished_at ? null : rec.order.find(id => !seen.has(id)) ?? null
  const remaining = Math.max(0, Math.floor((Date.parse(rec.deadline_at) - Date.now()) / 1000))
  return {
    id: rec.id,
    specialization: rec.specialization,
    declared_grade: rec.declared_grade,
    started_at: rec.started_at,
    deadline_at: rec.deadline_at,
    finished_at: rec.finished_at,
    remaining_seconds: remaining,
    progress: {
      current: currentId ? rec.order.indexOf(currentId) + 1 : rec.order.length,
      total: rec.order.length,
      answered,
      skipped,
    },
    task: currentId ? taskById(currentId) : null,
    result: rec.result,
  }
}

function scoreAttempt(rec: AttemptRec): S['AttemptResult'] {
  const skills = new Map<string, { ok: number; total: number }>()
  let ok = 0
  for (const id of rec.order) {
    const task = taskById(id)
    const answer = rec.answers.find(a => a.task_id === id && !a.skip)
    const taskSkills = task?.skills ?? []
    let good = false
    if (task?.kind === 'mcq') good = answer?.answer === correctOption(id)
    if (task?.kind === 'code') good = (answer?.code?.trim().length ?? 0) > 40
    if (good) ok += 1
    for (const skill of taskSkills) {
      const row = skills.get(skill) ?? { ok: 0, total: 0 }
      row.total += 1
      if (good) row.ok += 1
      skills.set(skill, row)
    }
  }
  const score = Math.round((ok / rec.order.length) * 100)
  const declared = rec.declared_grade
  const index = LADDER.indexOf(declared)
  let grade = declared
  let ready = false
  if (score >= 75) ready = true
  else if (score < 40) grade = LADDER[Math.max(0, index - 1)] ?? declared
  return {
    score,
    grade,
    ready_for_next: ready,
    skill_scores: [...skills.entries()].map(([skill_id, row]) => ({
      skill_id,
      score: row.total ? Math.round((row.ok / row.total) * 100) : 0,
    })),
    rank: 12,
    category_size: 340,
  }
}

function judge(code: string, hidden: boolean): S['RunOut'] {
  const total = hidden ? 5 : 2
  if (/syntax error|compile|ошибка компиляции/i.test(code) || code.includes('???')) {
    return { verdict: 'COMPILE_ERROR', passed: 0, total, stdout: '', stderr: 'SyntaxError' }
  }
  if (/while\s+True|for\s*\(\s*;\s*;|time\.sleep\(/.test(code)) {
    return { verdict: 'TIME_LIMIT', passed: 0, total, stdout: '', stderr: '' }
  }
  if (code.trim().length < 8) return { verdict: 'WRONG_ANSWER', passed: 0, total, stdout: '', stderr: '' }
  const passed = code.trim().length > 40 ? total : Math.max(1, total - 1)
  return {
    verdict: passed === total ? 'OK' : 'WRONG_ANSWER',
    passed,
    total,
    stdout: passed === total ? 'ok' : '',
    stderr: '',
  }
}

function checkNeed(body: Partial<S['NeedWrite']>) {
  if (!body.title?.trim()) return 'Укажите название роли'
  if (!body.specialization) return 'Укажите специализацию'
  if (!body.grades?.length) return 'Укажите грейд'
  if (body.grades.length > 2) return 'Можно указать не больше двух грейдов'
  if (body.salary_from == null || body.salary_to == null) return 'Вилка обязательна'
  if (body.salary_from > body.salary_to) return 'Зарплата «от» не может быть больше «до»'
  if (!body.formats?.length) return 'Укажите формат работы'
  if (!body.must_skills?.length) return 'Нужен хотя бы один обязательный навык'
  if (body.must_skills.length > 5) return 'Обязательных навыков не больше пяти — перенесите лишние в желательные'
  if ((body.nice_skills?.length ?? 0) > 5) return 'Желательных навыков не больше пяти'
  if (!body.description || body.description.trim().length < 300) return 'Описание задач команды — не меньше 300 символов'
  if (!body.domain?.trim()) return 'Укажите домен продукта'
  if (body.stages == null || body.stages < 1 || body.stages > 10) return 'Число этапов найма — от 1 до 10'
  return ''
}

function toNeed(body: S['NeedWrite'], id: string, status: string): S['NeedOut'] {
  return { ...body, nice_skills: body.nice_skills ?? [], city: body.city ?? null, id, status, company_id: IDS.company }
}

function parsedSample(): S['ParsedResume'] {
  return {
    experiences: [{
      evidence_span: 'Backend-разработчик, Сибирь Телеком, 2023 — н.в. Биллинг на Go.',
      company: 'Сибирь Телеком',
      role: 'Backend-разработчик',
      start: '2023-03-01T00:00:00.000Z',
      end: null,
      description: 'Биллинг на Go: расчёт тарифов.',
    }],
    skills: [
      { evidence_span: 'Стек: Go, PostgreSQL, Kafka', name: 'Go', skill_id: 'go' },
      { evidence_span: 'Стек: Go, PostgreSQL, Kafka', name: 'PostgreSQL', skill_id: 'postgresql' },
      { evidence_span: 'Очереди Kafka в биллинге', name: 'Kafka', skill_id: 'kafka' },
    ],
    projects: [{
      evidence_span: 'Переписал расчёт тарифов, p99 с 900 до 120 мс.',
      task: 'Переписал расчёт тарифов',
      role: 'owner',
      skills: ['go'],
      outcome: 'p99 с 900 до 120 мс',
    }],
  }
}

function hintsFor(db: Db): S['CandidateHint'][] {
  const items: S['CandidateHint'][] = []
  if (!db.profile.grade) {
    items.push({ id: 'grade', type: 'test', title: 'Пройдите тест на грейд', effect_text: 'без грейда профиль не попадает в категорию', action_label: 'Начать тест', action_href: '/candidate/onboarding', priority: 30 })
  } else {
    items.push({ id: 'k8s', type: 'skill', title: 'Подтвердите знание Kubernetes', effect_text: '+30% работодателей', action_label: 'Пройти тест', action_href: '/candidate/onboarding', priority: 30 })
  }
  if (!db.profile.projects?.length) {
    items.push({ id: 'project', type: 'project', title: 'Добавьте проект через мастер', effect_text: '+18% просмотров', action_label: 'Добавить проект', action_href: '/candidate/profile#projects', priority: 20 })
  } else {
    items.push({ id: 'fresh', type: 'activity', title: 'Решите задание, чтобы подняться в категории', effect_text: '12 → 7 место', action_label: 'К тесту', action_href: '/candidate/onboarding', priority: 20 })
  }
  if (!db.profile.fsp_achievements?.length) {
    items.push({ id: 'fsp', type: 'fsp', title: 'Свяжите ФСП ID', effect_text: 'до 3 достижений в профиле', action_label: 'Связать', action_href: '/candidate/profile#fsp', priority: 10 })
  } else if (!db.profile.in_pool_eligible) {
    items.push({ id: 'pool', type: 'settings', title: 'Укажите зарплату и формат', effect_text: 'иначе профиль не участвует в подборках', action_label: 'Заполнить', action_href: '/candidate/profile#search', priority: 10 })
  } else {
    items.push({ id: 'visibility', type: 'settings', title: 'Проверьте видимость профиля', effect_text: 'скрытый профиль не попадает в подборки', action_label: 'Настройки', action_href: '/candidate/settings', priority: 10 })
  }
  return items
}

function employerHints(people: PoolPerson[]): S['EmployerHint'][] {
  const before = people.length
  const rows = [
    { id: 'kafka', title: 'Kafka — только подтверждённая тестом', pred: (p: PoolPerson) => p.skills.includes('kafka'), filter: { stack: 'kafka' } },
    { id: 'fintech', title: 'Опыт в финтехе от 1 года', pred: (p: PoolPerson) => p.domains.includes('fintech'), filter: { domain: 'fintech' } },
    { id: 'active', title: 'Активен за последние 30 дней', pred: (p: PoolPerson) => p.active_30d, filter: { active_30d: true } },
  ]
  return rows.map(row => ({
    id: row.id,
    type: 'filter',
    title: row.title,
    before,
    after: people.filter(row.pred).length,
    avg_before: null,
    avg_after: null,
    apply: { kind: 'filter', filter: row.filter },
  }))
}

function applyHint<T extends PoolPerson>(people: T[], hintId: string | null): T[] {
  if (hintId === 'kafka') return people.filter(p => p.skills.includes('kafka'))
  if (hintId === 'fintech') return people.filter(p => p.domains.includes('fintech'))
  if (hintId === 'active') return people.filter(p => p.active_30d)
  return people
}

function categoryTitle(id: string) {
  const [spec, grade] = id.split(':')
  const specs: Record<string, string> = { backend: 'Backend', frontend: 'Frontend', data_ml: 'Data/ML', devops: 'DevOps' }
  const grades: Record<string, string> = { intern: 'Intern', junior: 'Junior', middle: 'Middle', senior: 'Senior', lead: 'Lead' }
  return `${specs[spec ?? ''] ?? spec} · ${grades[grade ?? ''] ?? grade}`
}

function invitationStatus(db: Db, candidateId: string, needId: string) {
  const found = db.invitations.find(i => i.candidate_id === candidateId && i.need_id === needId && i.status !== 'revoked')
  return found?.status ?? null
}

type VacancyRec = {
  id: string
  company_id: string
  company_name: string
  title: string
  specialization: string
  grades: string[]
  salary_from: number
  salary_to: number
  description: string
  domain: string
  must_skills: string[]
  formats: string[]
  city: string | null
  status: string
}

type AppRec = {
  id: string
  vacancy_id: string
  candidate_id: string
  status: string
  message: string
  title: string
  company_name: string
  salary_from: number
  salary_to: number
  candidate_display_name: string
  candidate_email: string
  candidate_phone: string
}

type MicroRec = { id: string; title: string; body: string }

type PsychRec = { id: string; answers: PsychAnswers; result: PsychResult | null; started_at: string; finished_at: string | null }

type Privacy = {
  show_full_name: boolean
  show_current_job: boolean
  show_fsp: boolean
  show_pdf: boolean
  show_psych: boolean
  consent_processing_at: string | null
  consent_publication_at: string | null
}

type Gap = {
  psych?: PsychRec[]
  privacy?: Privacy
  vacancies?: VacancyRec[]
  applications?: AppRec[]
  micro_tasks?: MicroRec[]
  micro_answers?: string[]
  consent_processing?: boolean
  consent_publication?: boolean
  soft_skills?: string[]
  retake_locked?: boolean
}

function gap(db: Db) {
  return db as Db & Gap
}

function ensureVacancies(db: Db) {
  const state = gap(db)
  if (!state.vacancies) {
    const description = 'Ищем разработчика в антифрод: потоковая обработка событий, PostgreSQL и дежурства. Описание длиннее пятидесяти символов.'
    state.vacancies = [
      {
        id: '88888888-8888-4888-8888-888888888881',
        company_id: IDS.company,
        company_name: db.company.name,
        title: 'Backend-разработчик (Go) в антифрод',
        specialization: 'backend',
        grades: ['middle'],
        salary_from: 250000,
        salary_to: 320000,
        description,
        domain: 'fintech',
        must_skills: ['go', 'postgresql'],
        formats: ['remote'],
        city: 'Новосибирск',
        status: 'open',
      },
      {
        id: '88888888-8888-4888-8888-888888888882',
        company_id: IDS.company,
        company_name: db.company.name,
        title: 'Frontend-разработчик кабинета мерчанта',
        specialization: 'frontend',
        grades: ['middle'],
        salary_from: 180000,
        salary_to: 240000,
        description: 'Нужен человек на кабинет мерчанта: Vue, витрины платежей и спокойный релиз раз в неделю. Текст длиннее пятидесяти символов.',
        domain: 'fintech',
        must_skills: ['vue', 'javascript'],
        formats: ['remote'],
        city: 'Новосибирск',
        status: 'open',
      },
    ]
  }
  if (!state.applications) {
    const first = state.vacancies[0]
    const second = state.vacancies[1]
    state.applications = []
    if (first) {
      state.applications.push({
        id: '99999999-9999-4999-8999-999999999991',
        vacancy_id: first.id,
        candidate_id: IDS.c2,
        status: 'sent',
        message: 'Готова посмотреть антифрод на Go.',
        title: first.title,
        company_name: first.company_name,
        salary_from: first.salary_from,
        salary_to: first.salary_to,
        candidate_display_name: 'Мария С.',
        candidate_email: 'm.sokolova@mail.ru',
        candidate_phone: '+7 843 000-11-22',
      })
    }
    if (second) {
      state.applications.push({
        id: '99999999-9999-4999-8999-999999999992',
        vacancy_id: second.id,
        candidate_id: IDS.candidate,
        status: 'viewed',
        message: 'Интересен кабинет мерчанта.',
        title: second.title,
        company_name: second.company_name,
        salary_from: second.salary_from,
        salary_to: second.salary_to,
        candidate_display_name: db.profile.display_name,
        candidate_email: db.profile.contact_email || 'candidate@demo.fsp',
        candidate_phone: db.profile.phone || '',
      })
    }
  }
  return state
}

function appView(row: AppRec, employer: boolean) {
  const base = {
    id: row.id,
    vacancy_id: row.vacancy_id,
    status: row.status,
    title: row.title,
    company_name: row.company_name,
    salary_from: row.salary_from,
    salary_to: row.salary_to,
    message: row.message,
    created_at: (row as AppRec & { created_at?: string }).created_at ?? new Date().toISOString(),
    decline_reason: (row as AppRec & { decline_reason?: string }).decline_reason ?? null,
  }
  if (!employer) return base
  return {
    ...base,
    candidate_display_name: row.candidate_display_name,
    candidate_email: row.candidate_email,
    candidate_phone: row.candidate_phone,
  }
}

function privacy(db: Db): Privacy {
  const state = gap(db)
  if (!state.privacy) {
    state.privacy = {
      show_full_name: false, show_current_job: true, show_fsp: true, show_pdf: true, show_psych: false,
      consent_processing_at: state.consent_processing ? new Date().toISOString() : null,
      consent_publication_at: state.consent_publication ? new Date().toISOString() : null,
    }
  }
  return state.privacy
}

const OTHER_COMPANIES = [
  { id: '22222222-2222-4222-8222-222222222299', name: 'Ромашка Финтех', city: 'Москва' },
  { id: '22222222-2222-4222-8222-222222222298', name: 'Тайга Софт', city: 'Томск' },
]

function companyIndex(db: Db) {
  return [{ id: db.company.id, name: db.company.name || 'Компания', city: db.company.city ?? null }, ...OTHER_COMPANIES]
}

function settingsView(db: Db) {
  const p = privacy(db)
  const names = companyIndex(db)
  return {
    ...db.settings,
    consent_processing: gap(db).consent_processing ?? false,
    consent_publication: gap(db).consent_publication ?? false,
    soft_skills: gap(db).soft_skills ?? [],
    ...p,
    hidden_companies: (db.settings.hidden_company_ids ?? []).map(id => ({ id, name: names.find(c => c.id === id)?.name ?? 'Компания удалена' })),
    fsp_linked: (db.profile.fsp_achievements?.length ?? 0) > 0,
  }
}

function psychState(db: Db) {
  const rows = gap(db).psych ?? []
  const open = rows.find(r => !r.finished_at) ?? null
  const last = rows.filter(r => r.finished_at).sort((a, b) => String(b.finished_at).localeCompare(String(a.finished_at)))[0] ?? null
  const nextAt = last?.finished_at ? new Date(new Date(last.finished_at).getTime() + 30 * 864e5) : null
  const locked = nextAt != null && nextAt.getTime() > Date.now()
  return {
    attempt: open ? { id: open.id, version: PSYCH_PUBLIC.version, answers: open.answers, progress: progressOf(open.answers), started_at: open.started_at, finished_at: null } : null,
    result: last?.result ? candidateView(last.result) : null,
    finished_at: last?.finished_at ?? null,
    can_start: open != null || !locked,
    next_attempt_at: locked ? nextAt!.toISOString() : null,
    share_with_employers: privacy(db).show_psych,
    limitations: PSYCH_LIMITATIONS,
  }
}

function ensureMicro(db: Db) {
  const state = gap(db)
  if (!state.micro_tasks) {
    state.micro_tasks = [
      { id: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeee01', title: 'Разберите гонку в кэше', body: 'Где гонка и как её закрыть, не останавливая чтение.' },
      { id: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeee02', title: 'Как бы вы деградировали Kafka-консьюмер', body: 'Что отключите первым, если лаг растёт.' },
    ]
  }
  if (!state.micro_answers) state.micro_answers = []
  return state
}

function skillList(raw: string[] | string | undefined) {
  if (Array.isArray(raw)) return raw.map(item => item.trim()).filter(Boolean)
  return String(raw ?? '').split(',').map(item => item.trim()).filter(Boolean)
}

async function routeOfficial(db: Db, method: string, path: string, url: URL, req: Request): Promise<Response | null> {
  // ---------- тест рабочего стиля
  if (path === '/api/v1/psych/test' && method === 'GET') return json(PSYCH_PUBLIC)
  if (path === '/api/v1/psych/me' && method === 'GET') return json(psychState(db))
  if (path === '/api/v1/psych/attempts' && method === 'POST') {
    const state = psychState(db)
    if (state.attempt) return json(state.attempt, 201)
    if (!state.can_start) return fail(409, `Пройти тест снова можно с ${new Date(state.next_attempt_at!).toLocaleDateString('ru-RU')}`, 'retake_too_early')
    const rec: PsychRec = { id: uid(), answers: { disc: {}, statements: {}, cases: {} }, result: null, started_at: new Date().toISOString(), finished_at: null }
    gap(db).psych = [...(gap(db).psych ?? []), rec]
    return json(psychState(db).attempt, 201)
  }
  const psychSave = path.match(/^\/api\/v1\/psych\/attempts\/([^/]+)$/)
  if (psychSave && method === 'PUT') {
    const rec = (gap(db).psych ?? []).find(r => r.id === take(psychSave) && !r.finished_at)
    if (!rec) return fail(404, 'Прохождение не найдено')
    rec.answers = cleanAnswers(await readBody<PsychAnswers>(req))
    return json(psychState(db).attempt)
  }
  const psychFinish = path.match(/^\/api\/v1\/psych\/attempts\/([^/]+)\/finish$/)
  if (psychFinish && method === 'POST') {
    const rec = (gap(db).psych ?? []).find(r => r.id === take(psychFinish) && !r.finished_at)
    if (!rec) return fail(404, 'Прохождение не найдено')
    const body = await readBody<{ answers?: PsychAnswers; share_with_employers?: boolean }>(req)
    if (body.answers) rec.answers = cleanAnswers(body.answers)
    rec.finished_at = new Date().toISOString()
    rec.result = scoreMock(rec.answers, (Date.now() - new Date(rec.started_at).getTime()) / 1000)
    if (typeof body.share_with_employers === 'boolean') privacy(db).show_psych = body.share_with_employers
    return json(psychState(db))
  }
  if (path === '/api/v1/psych/me/share' && method === 'PUT') {
    const body = await readBody<{ share_with_employers?: boolean }>(req)
    privacy(db).show_psych = !!body.share_with_employers
    return json(psychState(db))
  }
  const psychEmployer = path.match(/^\/api\/v1\/psych\/candidates\/([^/]+)$/)
  if (psychEmployer && method === 'GET') {
    const id = take(psychEmployer)
    // В моке результат есть только у демо-кандидата, остальным показываем пояснение.
    if (id !== IDS.candidate) return json({ available: false, reason: 'Кандидат ещё не проходил тест рабочего стиля.', finished_at: null, result: null, limitations: PSYCH_LIMITATIONS })
    const last = (gap(db).psych ?? []).filter(r => r.finished_at && r.result).pop()
    if (!privacy(db).show_psych) return json({ available: false, reason: 'Кандидат не открыл результаты теста рабочего стиля.', finished_at: null, result: null, limitations: PSYCH_LIMITATIONS })
    if (!last) return json({ available: false, reason: 'Кандидат ещё не проходил тест рабочего стиля.', finished_at: null, result: null, limitations: PSYCH_LIMITATIONS })
    return json({ available: true, reason: null, finished_at: last.finished_at, result: last.result, limitations: PSYCH_LIMITATIONS })
  }

  // ---------- приватность, ФСП ID, компании
  if (path === '/api/v1/candidates/me/fsp-link' && method === 'DELETE') {
    db.profile.fsp_achievements = []
    db.profile.skills = (db.profile.skills ?? []).filter(s => s.source !== 'fsp_id')
    return json(db.profile)
  }
  if (path === '/api/v1/candidates/me/settings' && method === 'GET') return json(settingsView(db))
  if (path === '/api/v1/candidates/me/settings' && method === 'PUT') {
    const body = await readBody<Record<string, unknown>>(req)
    const p = privacy(db)
    const was = { processing: gap(db).consent_processing ?? false, publication: gap(db).consent_publication ?? false }
    db.settings = { visible: !!body.visible, hidden_company_ids: Array.isArray(body.hidden_company_ids) ? body.hidden_company_ids as string[] : [] }
    db.profile.visible = !!body.visible
    gap(db).consent_processing = !!body.consent_processing
    gap(db).consent_publication = !!body.consent_publication
    p.consent_processing_at = body.consent_processing ? (was.processing && p.consent_processing_at ? p.consent_processing_at : new Date().toISOString()) : null
    p.consent_publication_at = body.consent_publication ? (was.publication && p.consent_publication_at ? p.consent_publication_at : new Date().toISOString()) : null
    for (const key of ['show_full_name', 'show_current_job', 'show_fsp', 'show_pdf', 'show_psych'] as const) {
      if (typeof body[key] === 'boolean') p[key] = body[key] as boolean
    }
    eligibility(db.profile)
    return json(settingsView(db))
  }
  if (path === '/api/v1/companies' && method === 'GET') {
    const q = (qstr(url, 'q') ?? '').toLowerCase()
    if (q.length < 2) return json([])
    return json(companyIndex(db).filter(c => c.name.toLowerCase().includes(q)).slice(0, 10))
  }

  // ---------- вакансии и отклики: редактирование и решения работодателя
  const vacancyEdit = path.match(/^\/api\/v1\/vacancies\/([^/]+)$/)
  if (vacancyEdit && method === 'PUT') {
    const state = ensureVacancies(db)
    const vacancy = (state.vacancies ?? []).find(v => v.id === take(vacancyEdit))
    if (!vacancy) return fail(404, 'Вакансия не найдена')
    const body = await readBody<Partial<VacancyRec>>(req)
    if ((body.description ?? '').trim().length < 50) return fail(422, 'Описание — не меньше 50 символов')
    Object.assign(vacancy, body, { id: vacancy.id, company_id: vacancy.company_id, company_name: vacancy.company_name, status: vacancy.status })
    return json(vacancy)
  }
  const appAction = path.match(/^\/api\/v1\/applications\/([^/]+)\/(view|accept|decline)$/)
  if (appAction && method === 'POST') {
    const state = ensureVacancies(db)
    const row = (state.applications ?? []).find(a => a.id === take(appAction))
    if (!row) return fail(404, 'Отклик не найден')
    const action = take(appAction, 2)
    if (action === 'view' && row.status === 'sent') row.status = 'viewed'
    if (action === 'accept') {
      if (row.status === 'declined') return fail(409, 'Отклик уже отклонён')
      row.status = 'accepted'
    }
    if (action === 'decline') {
      if (row.status === 'accepted') return fail(409, 'Отклик уже принят')
      const body = await readBody<{ reason?: string }>(req)
      row.status = 'declined'
      ;(row as AppRec & { decline_reason?: string }).decline_reason = body.reason ?? 'other'
    }
    return json(appView(row, true))
  }
  const cardPdf = path.match(/^\/api\/v1\/needs\/([^/]+)\/candidates\/([^/]+)\/profile\.pdf$/)
  if (cardPdf && method === 'GET') {
    if (take(cardPdf, 2) === IDS.candidate && !privacy(db).show_pdf) return fail(403, 'Кандидат не открыл PDF-профиль работодателям')
    const pdf = '%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF'
    return new Response(pdf, { status: 200, headers: { 'content-type': 'application/pdf' } })
  }

  if (path === '/api/v1/candidates/me/profile.pdf' && method === 'GET') {
    const pdf = '%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF'
    return new Response(pdf, { status: 200, headers: { 'content-type': 'application/pdf' } })
  }

  if (path === '/api/v1/candidates' && method === 'GET') {
    let rows = [...db.people]
    const specialization = (qstr(url, 'specialization') ?? '').toLowerCase()
    const grade = (qstr(url, 'grade') ?? '').toLowerCase()
    if (specialization) rows = rows.filter(p => p.category_id.toLowerCase().startsWith(`${specialization}:`))
    if (grade) rows = rows.filter(p => p.grade.toLowerCase() === grade)
    if (qbool(url, 'fsp')) rows = rows.filter(p => p.fsp_badge)
    const stack = (qstr(url, 'stack') ?? '').toLowerCase().split(/[,\s]+/).filter(Boolean)
    if (stack.length) rows = rows.filter(p => stack.every(part => p.skills.some(skill => skill.toLowerCase().includes(part))))
    const items = rows.slice(0, 50).map(p => ({
      id: p.candidate_id,
      display_name: p.display_name,
      specialization: p.category_id.split(':')[0] ?? '',
      grade: p.grade,
      city: p.city,
      skills: p.skills,
      has_fsp: Boolean(p.fsp_badge),
      test_score: p.test_score,
    }))
    return json({ items, total: rows.length })
  }

  if (path === '/api/v1/vacancies' && method === 'GET') {
    const state = ensureVacancies(db)
    const rows = role() === 'employer'
      ? (state.vacancies ?? []).filter(v => v.company_id === IDS.company)
      : (state.vacancies ?? []).filter(v => v.status === 'open')
    return json(rows)
  }
  if (path === '/api/v1/vacancies' && method === 'POST') {
    if (role() !== 'employer') return fail(403, 'Недостаточно прав')
    const body = await readBody<{
      title?: string
      specialization?: string
      grades?: string[]
      grade?: string
      salary_from?: number
      salary_to?: number
      description?: string
      domain?: string
      must_skills?: string[] | string
      formats?: string[]
      city?: string | null
    }>(req)
    const grades = body.grades?.length ? body.grades : (body.grade ? [body.grade] : [])
    const specs = ['backend', 'frontend', 'data_ml', 'devops']
    if (!body.title?.trim()) return fail(422, 'Укажите название')
    if (!specs.includes(body.specialization ?? '')) return fail(422, 'Укажите специализацию')
    if (!grades.length || grades.some(item => !LADDER.includes(item as S['Grade']))) return fail(422, 'Укажите грейд')
    if (grades.length > 2) return fail(422, 'Можно указать не больше двух грейдов')
    if (typeof body.salary_from !== 'number' || typeof body.salary_to !== 'number') return fail(422, 'Вилка обязательна')
    if (body.salary_from > body.salary_to) return fail(422, 'Зарплата «от» не может быть больше «до»')
    if ((body.description ?? '').trim().length < 50) return fail(422, 'Описание — не меньше 50 символов')
    if (!body.domain?.trim()) return fail(422, 'Укажите домен')
    const must = skillList(body.must_skills)
    if (!must.length) return fail(422, 'Укажите обязательные навыки')
    const state = ensureVacancies(db)
    const vacancy: VacancyRec = {
      id: uid(),
      company_id: IDS.company,
      company_name: db.company.name,
      title: body.title.trim(),
      specialization: body.specialization ?? 'backend',
      grades,
      salary_from: body.salary_from,
      salary_to: body.salary_to,
      description: body.description?.trim() ?? '',
      domain: body.domain.trim(),
      must_skills: must,
      formats: body.formats?.length ? body.formats : ['remote'],
      city: body.city ?? null,
      status: 'open',
    }
    state.vacancies = [vacancy, ...(state.vacancies ?? [])]
    return json(vacancy, 201)
  }

  const applyPath = path.match(/^\/api\/v1\/vacancies\/([^/]+)\/applications$/)
  if (applyPath && method === 'POST') {
    if (role() !== 'candidate') return fail(403, 'Недостаточно прав')
    const state = ensureVacancies(db)
    const vacancy = (state.vacancies ?? []).find(v => v.id === take(applyPath))
    if (!vacancy || vacancy.status !== 'open') return fail(404, 'Вакансия не найдена')
    const dup = (state.applications ?? []).find(a => a.vacancy_id === vacancy.id && a.candidate_id === IDS.candidate)
    if (dup) return fail(409, 'Вы уже откликались на эту вакансию')
    const body = await readBody<{ message?: string }>(req)
    const row: AppRec = {
      id: uid(),
      vacancy_id: vacancy.id,
      candidate_id: IDS.candidate,
      status: 'sent',
      message: body.message?.trim() || 'Отклик',
      title: vacancy.title,
      company_name: vacancy.company_name,
      salary_from: vacancy.salary_from,
      salary_to: vacancy.salary_to,
      candidate_display_name: db.profile.display_name,
      candidate_email: db.profile.contact_email || 'candidate@demo.fsp',
      candidate_phone: db.profile.phone || '',
    }
    state.applications = [row, ...(state.applications ?? [])]
    return json(appView(row, false), 201)
  }

  const vacancyPath = path.match(/^\/api\/v1\/vacancies\/([^/]+)$/)
  if (vacancyPath && method === 'GET') {
    const state = ensureVacancies(db)
    const vacancy = (state.vacancies ?? []).find(v => v.id === take(vacancyPath))
    if (!vacancy) return fail(404, 'Вакансия не найдена')
    if (role() !== 'employer' && vacancy.status !== 'open') return fail(404, 'Вакансия не найдена')
    return json(vacancy)
  }

  if (path === '/api/v1/applications' && method === 'GET') {
    const state = ensureVacancies(db)
    const asked = qstr(url, 'role') ?? role()
    const employer = asked === 'employer'
    const rows = (state.applications ?? []).filter(a => employer ? true : a.candidate_id === IDS.candidate)
    const items = rows.map(row => appView(row, employer))
    const counts: Record<string, number> = {}
    for (const row of rows) counts[row.status] = (counts[row.status] ?? 0) + 1
    return json({ items, counts })
  }

  if (path === '/api/v1/assessment/retake' && method === 'POST') {
    const body = await readBody<{ direction?: string }>(req)
    if (body.direction !== 'up' && body.direction !== 'down') return fail(422, 'Укажите направление: up или down')
    const state = gap(db)
    if (state.retake_locked) return fail(409, 'Менять грейд можно не чаще раза в 90 дней', 'grade_cooldown')
    const current = db.profile.grade ?? db.grade.grade
    if (!current) return fail(409, 'Сначала подтвердите грейд тестом', 'grade_missing')
    const index = LADDER.indexOf(current)
    const nextIndex = body.direction === 'up' ? index + 1 : index - 1
    const next = LADDER[nextIndex]
    if (!next) {
      return fail(409, body.direction === 'up' ? 'Выше этого грейда подняться нельзя' : 'Ниже этого грейда опуститься нельзя', 'grade_edge')
    }
    db.profile.grade = next
    db.grade.grade = next
    state.retake_locked = true
    return json({ direction: body.direction, grade: next })
  }

  if (path === '/api/v1/assessment/micro-tasks' && method === 'GET') {
    const state = ensureMicro(db)
    const answered = new Set(state.micro_answers ?? [])
    return json((state.micro_tasks ?? []).filter(task => !answered.has(task.id)))
  }

  const answerPath = path.match(/^\/api\/v1\/assessment\/micro-tasks\/([^/]+)\/answer$/)
  if (answerPath && method === 'POST') {
    const state = ensureMicro(db)
    const taskId = take(answerPath)
    const task = (state.micro_tasks ?? []).find(item => item.id === taskId)
    if (!task) return fail(404, 'Задание не найдено')
    const body = await readBody<{ answer?: string }>(req)
    if ((body.answer ?? '').trim().length < 20) return fail(422, 'Ответ — не меньше 20 символов')
    if ((state.micro_answers ?? []).includes(taskId)) return fail(409, 'Ответ уже отправлен')
    state.micro_answers = [...(state.micro_answers ?? []), taskId]
    db.profile.last_active_at = new Date().toISOString()
    return json({ id: taskId, status: 'answered' })
  }

  return null
}

async function route(db: Db, method: string, path: string, url: URL, req: Request): Promise<Response> {
  const official = await routeOfficial(db, method, path, url, req)
  if (official) return official
  if (method === 'GET' && path === '/api/v1/me') return json(me())

  if (path === '/api/v1/candidates/me' && method === 'GET') return json({ ...db.profile, soft_skills: gap(db).soft_skills ?? [] })
  if (path === '/api/v1/candidates/me' && method === 'PUT') {
    const body = await readBody<S['CandidateUpdate'] & { soft_skills?: string[] | string }>(req)
    const profile = db.profile
    if (body.full_name) {
      profile.full_name = body.full_name
      profile.display_name = initials(body.full_name)
    }
    if (body.city !== undefined) profile.city = body.city
    if (body.specialization !== undefined) profile.specialization = body.specialization
    if (body.min_salary !== undefined) profile.min_salary = body.min_salary
    if (body.formats) profile.formats = body.formats
    if (body.status) profile.status = body.status
    if (body.visible != null) profile.visible = body.visible
    if (body.liked_skills) profile.liked_skills = body.liked_skills
    if (body.disliked_skills) profile.disliked_skills = body.disliked_skills
    if (body.liked_domains) profile.liked_domains = body.liked_domains
    if (body.blocked_domains) profile.blocked_domains = body.blocked_domains
    if (body.phone !== undefined) profile.phone = body.phone
    if (body.contact_email !== undefined) profile.contact_email = body.contact_email
    if (body.soft_skills !== undefined) {
      gap(db).soft_skills = Array.isArray(body.soft_skills)
        ? body.soft_skills.map(item => item.trim()).filter(Boolean)
        : body.soft_skills.split(',').map(item => item.trim()).filter(Boolean)
    }
    eligibility(profile)
    return json({ ...profile, soft_skills: gap(db).soft_skills ?? [] })
  }

  if (path === '/api/v1/candidates/me/projects' && method === 'GET') return json(db.profile.projects ?? [])
  if (path === '/api/v1/candidates/me/projects' && method === 'POST') {
    const body = await readBody<S['ProjectIn']>(req)
    if (!body.task?.trim() || !body.role || !body.skills?.length) return fail(422, 'Заполните задачу, роль и хотя бы одну технологию')
    const project: S['ProjectOut'] = { ...body, id: uid(), source: 'project', scale: body.scale ?? null, outcome: body.outcome ?? null, date: body.date ?? null, url: body.url ?? null }
    db.profile.projects = [...(db.profile.projects ?? []), project]
    return json(project, 201)
  }

  const projectPath = path.match(/^\/api\/v1\/candidates\/me\/projects\/([^/]+)$/)
  if (projectPath && method === 'PUT') {
    const projectId = take(projectPath)
    const body = await readBody<S['ProjectIn']>(req)
    const current = (db.profile.projects ?? []).find(p => p.id === projectId)
    if (!current) return fail(404, 'Проект не найден')
    const next: S['ProjectOut'] = { ...current, ...body, id: current.id, source: current.source }
    db.profile.projects = (db.profile.projects ?? []).map(p => p.id === projectId ? next : p)
    return json(next)
  }
  if (projectPath && method === 'DELETE') {
    const projectId = take(projectPath)
    db.profile.projects = (db.profile.projects ?? []).filter(p => p.id !== projectId)
    return new Response(null, { status: 204 })
  }

  if (path === '/api/v1/candidates/me/fsp-link' && method === 'POST') {
    if (!db.profile.fsp_achievements?.length) {
      db.profile.fsp_achievements = [
        { id: uid(), discipline: 'algo', event: 'Чемпионат России 2025', place: 2, year: 2025 },
        { id: uid(), discipline: 'product', event: 'Кубок России 2024', place: null, year: 2024 },
      ]
      const skills = db.profile.skills ?? []
      if (!skills.some(s => s.skill_id === 'go' && s.source === 'fsp_id')) {
        db.profile.skills = [...skills, { skill_id: 'go', score: null, source: 'fsp_id' }]
      }
    }
    return json(db.profile)
  }

  if (path === '/api/v1/candidates/me/grade' && method === 'GET') return json(db.grade)
  if (path === '/api/v1/candidates/me/resume' && method === 'POST') {
    const fd = await req.formData()
    const file = fd.get('file')
    if (!(file instanceof File)) return fail(422, 'Приложите PDF-файл')
    if (file.size > 5 * 1024 * 1024) return fail(422, 'Файл больше 5 МБ')
    const name = file.name.toLowerCase()
    if (!name.endsWith('.pdf') && file.type !== 'application/pdf') return fail(422, 'Нужен файл PDF')
    const text = new TextDecoder('latin1').decode(await file.arrayBuffer())
    const pages = (text.match(/\/Type\s*\/Page(?![a-zA-Z])/g) || []).length
    if (pages > 5) return fail(422, 'В резюме больше 5 страниц')
    const id = uid()
    db.resumes[id] = { id, status: 'parsing', error: null, parsed: null, hits: 0 }
    return json({ resume_id: id, status: 'parsing' } satisfies S['ResumeUploadOut'], 201)
  }

  const resumeConfirm = path.match(/^\/api\/v1\/candidates\/me\/resume\/([^/]+)\/confirm$/)
  if (resumeConfirm && method === 'POST') {
    const resume = db.resumes[take(resumeConfirm)]
    if (!resume) return fail(404, 'Резюме не найдено')
    const body = await readBody<S['ParsedResume']>(req)
    const missing = [
      ...(body.experiences ?? []).filter(e => !e.evidence_span?.trim()),
      ...(body.skills ?? []).filter(s => !s.evidence_span?.trim()),
      ...(body.projects ?? []).filter(p => !p.evidence_span?.trim()),
    ]
    if (missing.length) return fail(422, 'Поле без цитаты из резюме не сохраняется')
    db.profile.experiences = (body.experiences ?? []).map(e => ({
      id: uid(),
      company: e.company,
      role: e.role,
      start: e.start ?? null,
      end: e.end ?? null,
      description: e.description ?? '',
      evidence_span: e.evidence_span,
    }))
    const kept = (db.profile.skills ?? []).filter(s => s.source !== 'resume')
    const fromResume: S['SkillOut'][] = (body.skills ?? []).map(s => ({
      skill_id: s.skill_id || s.name.toLowerCase(),
      score: null,
      source: 'resume',
    }))
    db.profile.skills = [...kept, ...fromResume]
    const projects = (body.projects ?? []).map(p => ({
      id: uid(),
      task: p.task,
      role: p.role ?? 'participant',
      skills: p.skills?.length ? p.skills : ['go'],
      scale: null,
      outcome: p.outcome ?? null,
      date: null,
      url: null,
      source: 'resume',
    } satisfies S['ProjectOut']))
    db.profile.projects = [...(db.profile.projects ?? []).filter(p => p.source !== 'resume'), ...projects]
    resume.status = 'confirmed'
    resume.parsed = body
    return json({ id: resume.id, status: resume.status, error: null, parsed: body } satisfies S['ResumeView'])
  }

  const resumeGet = path.match(/^\/api\/v1\/candidates\/me\/resume\/([^/]+)$/)
  if (resumeGet && method === 'GET') {
    const resume = db.resumes[take(resumeGet)]
    if (!resume) return fail(404, 'Резюме не найдено')
    resume.hits += 1
    if (resume.status === 'parsing' && resume.hits >= 2) {
      resume.status = 'parsed'
      resume.parsed = parsedSample()
    }
    return json({ id: resume.id, status: resume.status, error: resume.error ?? null, parsed: resume.parsed ?? null })
  }

  if (path === '/api/v1/candidates/me/hints' && method === 'GET') return json(hintsFor(db))

  const needHints = path.match(/^\/api\/v1\/needs\/([^/]+)\/hints$/)
  if (needHints && method === 'GET') {
    const need = db.needs.find(n => n.id === take(needHints))
    if (!need) return fail(404, 'Потребность не найдена')
    const primary = `${need.specialization}:${need.grades[0]}`
    return json(employerHints(db.people.filter(p => p.category_id === primary)))
  }

  if (path === '/api/v1/assessment/attempts' && method === 'POST') {
    const body = await readBody<S['AttemptCreate']>(req)
    if (!body.specialization || !body.declared_grade) return fail(422, 'Укажите специализацию и грейд')
    const id = uid()
    const started = new Date()
    const deadline = new Date(started.getTime() + 40 * 60 * 1000)
    const rec: AttemptRec = {
      id,
      specialization: body.specialization,
      declared_grade: body.declared_grade,
      started_at: started.toISOString(),
      deadline_at: deadline.toISOString(),
      finished_at: null,
      answers: [],
      order: taskOrder(),
      result: null,
    }
    db.attempts[id] = rec
    return json(attemptView(rec), 201)
  }

  const attemptAnswer = path.match(/^\/api\/v1\/assessment\/attempts\/([^/]+)\/answers$/)
  if (attemptAnswer && method === 'POST') {
    const rec = db.attempts[take(attemptAnswer)]
    if (!rec) return fail(404, 'Попытка не найдена')
    if (rec.finished_at) return fail(409, 'Тест уже завершён')
    const body = await readBody<S['AnswerIn']>(req)
    if (!body.task_id) return fail(422, 'Не указано задание')
    rec.answers = rec.answers.filter(a => a.task_id !== body.task_id)
    rec.answers.push({ task_id: body.task_id, answer: body.answer ?? null, code: body.code ?? null, language: body.language ?? null, skip: !!body.skip })
    return json(attemptView(rec))
  }

  const attemptFinish = path.match(/^\/api\/v1\/assessment\/attempts\/([^/]+)\/finish$/)
  if (attemptFinish && method === 'POST') {
    const rec = db.attempts[take(attemptFinish)]
    if (!rec) return fail(404, 'Попытка не найдена')
    if (!rec.result) {
      rec.result = scoreAttempt(rec)
      rec.finished_at = new Date().toISOString()
      db.profile.specialization = rec.specialization
      db.profile.grade = rec.result.grade
      db.profile.grade_score = rec.result.score
      db.profile.ready_for_next = rec.result.ready_for_next
      db.profile.category_rank = rec.result.rank ?? null
      db.profile.category_size = rec.result.category_size ?? null
      const tested = new Map((db.profile.skills ?? []).filter(s => s.source !== 'test').map(s => [s.skill_id + s.source, s]))
      const nextSkills = [...tested.values()]
      for (const row of rec.result.skill_scores) nextSkills.push({ skill_id: row.skill_id, score: row.score, source: 'test' })
      db.profile.skills = nextSkills
      db.grade = {
        specialization: rec.specialization,
        declared_grade: rec.declared_grade,
        grade: rec.result.grade,
        score: rec.result.score,
        ready_for_next: rec.result.ready_for_next,
        rank: rec.result.rank ?? null,
        category_size: rec.result.category_size ?? null,
        skill_scores: rec.result.skill_scores,
        history: [{ attempt_id: rec.id, finished_at: rec.finished_at, score: rec.result.score, grade: rec.result.grade }, ...(db.grade.history ?? [])],
      }
    }
    return json(rec.result)
  }

  const attemptGet = path.match(/^\/api\/v1\/assessment\/attempts\/([^/]+)$/)
  if (attemptGet && method === 'GET') {
    const rec = db.attempts[take(attemptGet)]
    if (!rec) return fail(404, 'Попытка не найдена')
    return json(attemptView(rec))
  }

  if (path === '/api/v1/assessment/run' && method === 'POST') {
    const body = await readBody<S['RunIn']>(req)
    if (!body.task_id || !body.code?.trim() || !body.language) return fail(422, 'Нужны задание, код и язык')
    const saved = Object.values(db.attempts).some(rec => rec.answers.some(a => a.task_id === body.task_id && a.code === body.code && !a.skip))
    return json(judge(body.code, saved))
  }

  if (path === '/api/v1/companies/me' && method === 'GET') return json(db.company)
  if (path === '/api/v1/companies/me' && method === 'PUT') {
    const body = await readBody<S['CompanyWrite']>(req)
    if (!body.name?.trim()) return fail(422, 'Укажите название компании')
    db.company = { ...db.company, ...body, id: db.company.id, benefits: body.benefits ?? db.company.benefits ?? [] }
    return json(db.company)
  }

  if (path === '/api/v1/needs' && method === 'GET') return json(db.needs)
  if (path === '/api/v1/needs' && method === 'POST') {
    const body = await readBody<S['NeedWrite']>(req)
    const problem = checkNeed(body)
    if (problem) return fail(422, problem)
    const need = toNeed(body, uid(), 'open')
    db.needs.unshift(need)
    return json(need, 201)
  }

  const needParse = path.match(/^\/api\/v1\/needs\/([^/]+)\/parse$/)
  if (needParse && method === 'POST') {
    const need = db.needs.find(n => n.id === take(needParse))
    if (!need) return fail(404, 'Потребность не найдена')
    const snippet = need.description.slice(0, 180)
    const requirements: S['RequirementOut'][] = [
      { id: uid(), task: 'Вести антифрод-сервис', domain: need.domain, skills: need.must_skills.slice(0, 3), scale: null, kind: 'must', evidence_span: snippet },
      { id: uid(), task: 'Разбирать инциденты по задержке', domain: need.domain, skills: ['go'], scale: 'p99', kind: 'must', evidence_span: snippet },
      { id: uid(), task: 'Помогать с релизами раз в неделю', domain: need.domain, skills: need.nice_skills ?? [], scale: null, kind: 'nice', evidence_span: snippet },
    ]
    db.requirements[need.id] = requirements
    const result: S['ParseResult'] = {
      llm_used: true,
      requirements,
      category: { specialization: need.specialization, grades: need.grades, domain: need.domain, evidence_span: snippet },
    }
    return json(result)
  }

  const needMatch = path.match(/^\/api\/v1\/needs\/([^/]+)\/match$/)
  if (needMatch && method === 'POST') {
    if (!db.needs.some(n => n.id === take(needMatch))) return fail(404, 'Потребность не найдена')
    const id = uid()
    db.jobs[id] = { id, status: 'queued', result: null, error: null, created_at: new Date().toISOString(), hits: 0 }
    return json({ job_id: id } satisfies S['MatchAccepted'], 202)
  }

  const needShort = path.match(/^\/api\/v1\/needs\/([^/]+)\/shortlist$/)
  if (needShort && method === 'GET') {
    const need = db.needs.find(n => n.id === take(needShort))
    if (!need) return fail(404, 'Потребность не найдена')
    const ranked = [...db.people].sort((a, b) => b.match - a.match).map((p, i) => ({ ...p, position: i + 1 }))
    let rows = ranked
    const category = qstr(url, 'category')
    const tab = qstr(url, 'tab') ?? 'pool'
    if (tab === 'favorites') rows = rows.filter(p => db.favorites.includes(p.candidate_id))
    else if (category) rows = rows.filter(p => p.category_id === category)
    if (qbool(url, 'only_fsp')) rows = rows.filter(p => p.fsp_badge)
    const disc = qstr(url, 'fsp_discipline')
    if (disc) rows = rows.filter(p => p.fsp_discipline === disc)
    const minScore = qint(url, 'min_test_score')
    if (minScore != null) rows = rows.filter(p => p.test_score >= minScore)
    const stack = qstr(url, 'stack')
    if (stack) {
      const parts = stack.toLowerCase().split(/[,\s]+/).filter(Boolean)
      rows = rows.filter(p => parts.every(part => p.skills.some(s => s.includes(part)) || p.projects.some(pr => pr.toLowerCase().includes(part))))
    }
    const format = qstr(url, 'format')
    if (format) rows = rows.filter(p => p.formats.includes(format as S['WorkFormat']))
    if (qbool(url, 'active_30d')) rows = rows.filter(p => p.active_30d)
    rows = applyHint(rows, qstr(url, 'hint_id'))
    const page = qint(url, 'page') ?? 1
    const pageSize = qint(url, 'page_size') ?? 20
    const total = rows.length
    const items: S['ShortlistItemOut'][] = rows.slice((page - 1) * pageSize, page * pageSize).map(p => ({
      position: p.position,
      candidate_id: p.candidate_id,
      display_name: p.display_name,
      category: p.category,
      grade: p.grade,
      experience_years: p.experience_years,
      city: p.city,
      fsp_badge: p.fsp_badge,
      match: p.match,
      test_score: p.test_score,
      explanations: p.explanations.slice(0, 3),
      invitation_status: invitationStatus(db, p.candidate_id, need.id),
      favorite: db.favorites.includes(p.candidate_id),
    }))
    const primary = `${need.specialization}:${need.grades[0]}`
    const tiles = [primary, need.grades[1] ? `${need.specialization}:${need.grades[1]}` : '', 'frontend:middle']
      .filter((id, i, all) => id && all.indexOf(id) === i)
      .slice(0, 3)
      .map(id => ({ id, title: categoryTitle(id), count: db.people.filter(p => p.category_id === id).length }))
    const out: S['ShortlistOut'] = {
      need_id: need.id,
      total,
      page,
      page_size: pageSize,
      categories: tiles,
      items,
      hidden_count: Math.max(0, ranked.length - total),
    }
    return json(out)
  }

  const cardPath = path.match(/^\/api\/v1\/needs\/([^/]+)\/candidates\/([^/]+)$/)
  if (cardPath && method === 'GET') {
    const person = db.people.find(p => p.candidate_id === take(cardPath, 2))
    if (!person || !db.needs.some(n => n.id === take(cardPath))) return fail(404, 'Кандидат не найден')
    const status = invitationStatus(db, person.candidate_id, take(cardPath))
    const open = status === 'accepted'
    const card: S['CandidateCard'] = {
      candidate_id: person.candidate_id,
      display_name: person.display_name,
      full_name_initials: person.display_name,
      category: person.category,
      city: person.city,
      experience_years: person.experience_years,
      match: person.match,
      test_score: person.test_score,
      explanations: person.explanations,
      skills: person.skills,
      projects: person.projects,
      fsp_badge: person.fsp_badge,
      invitation_status: status,
      contacts_revealed: open,
      email: open ? person.email : null,
      phone: open ? person.phone : null,
      in_shortlist: true,
      current_job: null,
      pdf_available: true,
      psych_available: false,
    }
    if (person.candidate_id === IDS.candidate) {
      const p = privacy(db)
      if ((db.settings.hidden_company_ids ?? []).includes(db.company.id)) return fail(404, 'Кандидат не найден')
      if (p.show_full_name) card.display_name = db.profile.full_name
      if (!p.show_fsp) card.fsp_badge = null
      card.current_job = p.show_current_job ? (db.profile.experiences?.[0] ? `${db.profile.experiences[0].role} · ${db.profile.experiences[0].company}` : null) : null
      card.pdf_available = p.show_pdf
      card.psych_available = p.show_psych
    }
    return json(card)
  }

  const fav = path.match(/^\/api\/v1\/favorites\/([^/]+)$/)
  if (fav && method === 'POST') {
    const favoriteId = take(fav)
    if (!db.favorites.includes(favoriteId)) db.favorites.push(favoriteId)
    return json({ candidate_id: favoriteId, favorite: true } satisfies S['FavoriteOut'])
  }
  if (fav && method === 'DELETE') {
    const favoriteId = take(fav)
    db.favorites = db.favorites.filter(id => id !== favoriteId)
    return json({ candidate_id: favoriteId, favorite: false } satisfies S['FavoriteOut'])
  }

  if (path === '/api/v1/invitations' && method === 'GET') {
    let items = db.invitations.map(inv => present(db, inv))
    const asked = qstr(url, 'role') ?? role()
    if (asked === 'candidate') items = items.filter(i => i.candidate_id === IDS.candidate)
    const status = qstr(url, 'status')
    if (status) items = items.filter(i => i.status === status)
    const counts: Record<string, number> = {}
    for (const inv of db.invitations) counts[inv.status] = (counts[inv.status] ?? 0) + 1
    return json({ items, counts } satisfies S['InvitationList'])
  }
  if (path === '/api/v1/invitations' && method === 'POST') {
    const body = await readBody<S['InvitationCreate']>(req)
    if (!body.need_id || !body.candidate_id || !body.title?.trim()) return fail(422, 'Заполните должность и кандидата')
    if (body.salary_from == null || body.salary_to == null) return fail(422, 'Вилка обязательна')
    if (!body.contact_channel || !body.contact_value?.trim()) return fail(422, 'Укажите способ связи')
    const dup = db.invitations.find(i => i.need_id === body.need_id && i.candidate_id === body.candidate_id && !['declined', 'expired', 'revoked'].includes(i.status))
    if (dup) return fail(409, 'Приглашение этому кандидату по этой потребности уже отправлено')
    const person = db.people.find(p => p.candidate_id === body.candidate_id)
    const need = db.needs.find(n => n.id === body.need_id)
    const inv: S['InvitationOut'] = {
      id: uid(),
      need_id: body.need_id,
      candidate_id: body.candidate_id,
      status: 'sent',
      title: body.title,
      message: body.message ?? '',
      salary_from: body.salary_from,
      salary_to: body.salary_to,
      contact_channel: body.contact_channel,
      deadline: body.deadline ?? null,
      decline_reason: null,
      created_at: new Date().toISOString(),
      company_name: db.company.name,
      need_title: need?.title ?? null,
      candidate_display_name: person?.display_name ?? null,
      candidate_email: null,
      candidate_phone: null,
      recruiter_contact: null,
    }
    db.invitations.unshift(inv)
    db.messages[inv.id] = []
    return json(present(db, inv), 201)
  }

  const invAction = path.match(/^\/api\/v1\/invitations\/([^/]+)\/(view|accept|decline|revoke|remind)$/)
  if (invAction && method === 'POST') {
    const inv = db.invitations.find(i => i.id === take(invAction))
    if (!inv) return fail(404, 'Приглашение не найдено')
    const action = take(invAction, 2)
    if (action === 'view') {
      if (inv.status === 'sent') inv.status = 'viewed'
      return json(present(db, inv))
    }
    if (action === 'accept') {
      if (inv.status !== 'sent' && inv.status !== 'viewed') return fail(409, 'Это приглашение уже нельзя принять')
      inv.status = 'accepted'
      return json(present(db, inv))
    }
    if (action === 'decline') {
      if (inv.status !== 'sent' && inv.status !== 'viewed') return fail(409, 'Это приглашение уже нельзя отклонить')
      const body = await readBody<S['DeclineIn']>(req)
      if (!body.reason) return fail(422, 'Укажите причину отказа')
      inv.status = 'declined'
      inv.decline_reason = body.reason
      return json(present(db, inv))
    }
    if (action === 'revoke') {
      if (inv.status !== 'sent' && inv.status !== 'viewed') return fail(409, 'Отозвать можно только приглашение без ответа')
      inv.status = 'revoked'
      return json(present(db, inv))
    }
    if (inv.status !== 'sent' && inv.status !== 'viewed') return fail(409, 'Напомнить можно только приглашению без ответа')
    return json(present(db, inv))
  }

  const messages = path.match(/^\/api\/v1\/invitations\/([^/]+)\/messages$/)
  if (messages && method === 'GET') {
    const inv = db.invitations.find(i => i.id === take(messages))
    if (!inv) return fail(404, 'Приглашение не найдено')
    if (inv.status !== 'accepted') return fail(403, 'Чат доступен после принятия приглашения')
    const after = qstr(url, 'after')
    const items = (db.messages[inv.id] ?? []).filter(m => !after || m.created_at > after)
    return json({ items } satisfies S['MessageList'])
  }
  if (messages && method === 'POST') {
    const inv = db.invitations.find(i => i.id === take(messages))
    if (!inv) return fail(404, 'Приглашение не найдено')
    if (inv.status !== 'accepted') return fail(403, 'Чат доступен после принятия приглашения')
    const body = await readBody<S['MessageCreate']>(req)
    const msg: S['MessageOut'] = {
      id: uid(),
      author_user_id: role() === 'employer' ? IDS.userE : IDS.userC,
      kind: body.kind ?? 'text',
      body: body.body ?? '',
      slots: body.slots ?? null,
      hiring_stage: body.hiring_stage ?? null,
      created_at: new Date().toISOString(),
    }
    db.messages[inv.id] = [...(db.messages[inv.id] ?? []), msg]
    return json(msg, 201)
  }

  const needOne = path.match(/^\/api\/v1\/needs\/([^/]+)$/)
  if (needOne && method === 'GET') {
    const need = db.needs.find(n => n.id === take(needOne))
    if (!need) return fail(404, 'Потребность не найдена')
    return json(need)
  }
  if (needOne && method === 'PUT') {
    const body = await readBody<S['NeedWrite']>(req)
    const problem = checkNeed(body)
    if (problem) return fail(422, problem)
    const needId = take(needOne)
    const prev = db.needs.find(n => n.id === needId)
    if (!prev) return fail(404, 'Потребность не найдена')
    const need = toNeed(body, needId, prev.status)
    db.needs = db.needs.map(n => n.id === needId ? need : n)
    return json(need)
  }

  if (path === '/api/v1/taxonomy/skills' && method === 'GET') {
    const q = (qstr(url, 'q') ?? '').toLowerCase()
    const limit = qint(url, 'limit') ?? 10
    const items = SKILLS.filter(s => !q || s.name.toLowerCase().includes(q) || s.id.includes(q) || (s.synonyms ?? []).some(n => n.includes(q))).slice(0, limit)
    return json(items)
  }
  if (path === '/api/v1/taxonomy/specializations' && method === 'GET') {
    const items: S['SpecializationOut'][] = [
      { id: 'backend', name: 'Backend', adjacent: ['devops', 'frontend'] },
      { id: 'frontend', name: 'Frontend', adjacent: ['backend'] },
      { id: 'data_ml', name: 'Data/ML', adjacent: ['backend'] },
      { id: 'devops', name: 'DevOps', adjacent: ['backend'] },
    ]
    return json(items)
  }
  if (path === '/api/v1/taxonomy/domains' && method === 'GET') {
    const items: S['DomainOut'][] = [
      { id: 'fintech', name: 'Финтех' },
      { id: 'ecommerce', name: 'E-commerce' },
      { id: 'gov', name: 'Госсектор' },
      { id: 'industrial', name: 'Промышленность' },
      { id: 'games', name: 'Игры' },
      { id: 'security', name: 'Кибербезопасность' },
    ]
    return json(items)
  }
  if (path === '/api/v1/taxonomy/decline-reasons' && method === 'GET') {
    const items: S['DeclineReasonOut'][] = [
      { id: 'salary', name: 'Не подходит вилка' },
      { id: 'stack', name: 'Не мой стек' },
      { id: 'format', name: 'Неудобный формат' },
      { id: 'found_job', name: 'Уже нашёл работу' },
      { id: 'other', name: 'Другое' },
    ]
    return json(items)
  }

  const job = path.match(/^\/api\/v1\/jobs\/([^/]+)$/)
  if (job && method === 'GET') {
    const found = db.jobs[take(job)]
    if (!found) return fail(404, 'Задача не найдена')
    found.hits += 1
    if (found.hits === 1) found.status = 'running'
    if (found.hits >= 2) {
      found.status = 'done'
      found.result = { ready: true }
    }
    return json({ id: found.id, status: found.status, result: found.result, error: found.error, created_at: found.created_at })
  }

  return fail(404, 'Не найдено', 'not_found')
}
