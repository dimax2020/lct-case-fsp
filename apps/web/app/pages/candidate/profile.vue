<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'
import { apiBlob, apiFetch, asList } from '~/utils/raw'
import { levelColor, type PsychState } from '~/utils/psych'

type Profile = components['schemas']['CandidateProfile']
type Parsed = components['schemas']['ParsedResume']
type ProjectRole = components['schemas']['ProjectRole']
type Spec = components['schemas']['Specialization']
type WorkFormat = components['schemas']['WorkFormat']
type Status = components['schemas']['CandidateStatus']

useHead({ title: 'Профиль кандидата — Карьера ФСП' })

const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => {
  const [profile, hints, invites, specs, domains] = await Promise.all([
    read(api.GET('/api/v1/candidates/me')),
    read(api.GET('/api/v1/candidates/me/hints')),
    read(api.GET('/api/v1/invitations', { params: { query: { role: 'candidate' } } })),
    read(api.GET('/api/v1/taxonomy/specializations')),
    read(api.GET('/api/v1/taxonomy/domains')),
  ])
  return { profile, hints, invites, specs, domains }
})

const psych = ref<PsychState | null>(null)
onMounted(async () => {
  try {
    psych.value = await apiFetch<PsychState>('/api/v1/psych/me')
  } catch {
    psych.value = null
  }
})
const city = ref('')
const salary = ref<string | number>('')
const softSkills = ref('')
const pdfLoading = ref(false)
type MicroTask = { id: string; title: string; body?: string }
const tasks = ref<MicroTask[]>([])
const taskPhase = ref<'loading' | 'ready' | 'error'>('loading')
const taskError = ref('')
const answers = reactive<Record<string, string>>({})
const formats = ref<WorkFormat[]>([])
const status = ref<Status>('seeking')
const spec = ref<Spec | ''>('')
const hover = ref('')
const resume = ref<components['schemas']['ResumeView'] | null>(null)
const draft = ref<Parsed | null>(null)
const resumeError = ref('')
const uploading = ref(false)
const cvInput = ref<HTMLInputElement>()
let pollTimer: ReturnType<typeof setTimeout> | undefined

const step = ref(1)
const task = ref('')
const role = ref<ProjectRole>('owner')
const skillQ = ref('')
const skillHits = ref<components['schemas']['SkillHit'][]>([])
const pickedSkills = ref<string[]>([])
const scale = ref('')
const outcome = ref('')
const projectDate = ref('')
const projectUrl = ref('')
const savingProject = ref(false)

watch(screen.data, (bundle) => {
  const profile = bundle?.profile
  if (!profile) return
  city.value = profile.city ?? ''
  salary.value = profile.min_salary ?? ''
  formats.value = [...(profile.formats ?? [])]
  status.value = profile.status
  spec.value = profile.specialization ?? ''
  if ('soft_skills' in profile) {
    const extra = profile as Profile & { soft_skills?: string[] | string }
    softSkills.value = Array.isArray(extra.soft_skills) ? extra.soft_skills.join(', ') : (extra.soft_skills || '')
  }
}, { immediate: true })

const profile = computed(() => screen.data.value?.profile ?? null)
const hints = computed(() => [...(screen.data.value?.hints ?? [])].sort((a, b) => b.priority - a.priority).slice(0, 3))
const incoming = computed(() => (screen.data.value?.invites.items ?? []).filter(i => i.status === 'sent' || i.status === 'viewed'))
const tested = computed(() => (profile.value?.skills ?? []).filter(s => s.source === 'test' && s.score != null))
const unverified = computed(() => (profile.value?.skills ?? []).filter(s => s.source !== 'test' || s.score == null))
const userName = computed(() => profile.value?.display_name || '…')

function toggleFormat(f: WorkFormat) {
  formats.value = formats.value.includes(f) ? formats.value.filter(x => x !== f) : [...formats.value, f]
}

async function saveSearch() {
  const min = parseMoney(salary.value)
  try {
    const next = await read(api.PUT('/api/v1/candidates/me', {
      body: {
        city: city.value || null,
        specialization: spec.value || null,
        min_salary: Number.isFinite(min) ? min : null,
        formats: formats.value,
        status: status.value,
        soft_skills: softSkills.value.split(',').map(item => item.trim()).filter(Boolean),
      } as components['schemas']['CandidateUpdate'],
    }))
    if (screen.data.value) screen.data.value.profile = next
    show(next.in_pool_eligible ? 'Условия поиска сохранены' : 'Сохранено. Без зарплаты и формата профиль не попадёт в подборки')
    await refreshHints()
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось сохранить')
  }
}

async function refreshHints() {
  if (!screen.data.value) return
  screen.data.value.hints = await read(api.GET('/api/v1/candidates/me/hints'))
}

async function onCv(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  resumeError.value = ''
  if (file.size > 5 * 1024 * 1024) {
    resumeError.value = 'Файл больше 5 МБ'
    return
  }
  if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
    resumeError.value = 'Нужен файл PDF'
    return
  }
  const text = new TextDecoder('latin1').decode(await file.arrayBuffer())
  const pages = (text.match(/\/Type\s*\/Page(?![a-zA-Z])/g) || []).length
  if (pages > 5) {
    resumeError.value = 'В резюме больше 5 страниц'
    return
  }
  uploading.value = true
  try {
    const created = await read(api.POST('/api/v1/candidates/me/resume', {
      body: { file: file.name },
      bodySerializer: () => {
        const fd = new FormData()
        fd.append('file', file)
        return fd
      },
    }))
    show('Резюме загружено — распознаём поля')
    await poll(created.resume_id)
  } catch (err) {
    resumeError.value = err instanceof Error ? err.message : 'Не удалось загрузить резюме'
  } finally {
    uploading.value = false
    if (cvInput.value) cvInput.value.value = ''
  }
}

async function poll(id: string) {
  const view = await read(api.GET('/api/v1/candidates/me/resume/{id}', { params: { path: { id } } }))
  resume.value = view
  if (view.status === 'parsed' && view.parsed) draft.value = structuredClone(view.parsed)
  if (view.status === 'failed') resumeError.value = view.error || 'Не удалось разобрать резюме'
  if (view.status === 'parsing' || view.status === 'uploaded') {
    pollTimer = setTimeout(() => { poll(id).catch(err => { resumeError.value = err instanceof Error ? err.message : 'Ошибка статуса' }) }, 1000)
  }
}

async function confirmResume() {
  if (!resume.value || !draft.value) return
  const body = draft.value
  const missing = [
    ...(body.experiences ?? []).filter(item => !item.evidence_span?.trim()),
    ...(body.skills ?? []).filter(item => !item.evidence_span?.trim()),
    ...(body.projects ?? []).filter(item => !item.evidence_span?.trim()),
  ]
  if (missing.length) {
    show('Поле без цитаты из резюме не сохраняется')
    return
  }
  try {
    await read(api.POST('/api/v1/candidates/me/resume/{id}/confirm', {
      params: { path: { id: resume.value.id } },
      body,
    }))
    const next = await read(api.GET('/api/v1/candidates/me'))
    if (screen.data.value) screen.data.value.profile = next
    draft.value = null
    show('Резюме подтверждено')
    await refreshHints()
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось подтвердить')
  }
}

async function linkFsp() {
  const before = profile.value?.fsp_achievements?.length ?? 0
  try {
    const next = await read(api.POST('/api/v1/candidates/me/fsp-link'))
    if (screen.data.value) screen.data.value.profile = next
    const added = (next.fsp_achievements?.length ?? 0) - before
    show(added > 0 ? `ФСП ID связан — достижений: ${added}` : 'Новых достижений ФСП нет')
    await refreshHints()
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось связать ФСП ID')
  }
}

let skillTimer: ReturnType<typeof setTimeout> | undefined
function onSkillInput() {
  clearTimeout(skillTimer)
  skillTimer = setTimeout(async () => {
    const q = skillQ.value.trim()
    if (!q) { skillHits.value = []; return }
    skillHits.value = await read(api.GET('/api/v1/taxonomy/skills', { params: { query: { q, limit: 8 } } }))
  }, 200)
}

function addSkill(id: string) {
  if (!pickedSkills.value.includes(id)) pickedSkills.value.push(id)
  skillQ.value = ''
  skillHits.value = []
}

async function saveProject() {
  if (!task.value.trim() || !pickedSkills.value.length) {
    show('Укажите задачу и хотя бы одну технологию из онтологии')
    return
  }
  savingProject.value = true
  try {
    await read(api.POST('/api/v1/candidates/me/projects', {
      body: {
        task: task.value.trim(),
        role: role.value,
        skills: pickedSkills.value,
        scale: scale.value || null,
        outcome: outcome.value || null,
        date: projectDate.value ? new Date(projectDate.value).toISOString() : null,
        url: projectUrl.value || null,
      },
    }))
    const next = await read(api.GET('/api/v1/candidates/me'))
    if (screen.data.value) screen.data.value.profile = next
    task.value = ''
    pickedSkills.value = []
    scale.value = ''
    outcome.value = ''
    projectDate.value = ''
    projectUrl.value = ''
    step.value = 1
    show('Проект сохранён')
    await refreshHints()
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось сохранить проект')
  } finally {
    savingProject.value = false
  }
}

function years(item: Profile['experiences'] extends infer T ? T extends Array<infer E> ? E : never : never) {
  if (!item.start) return ''
  const end = item.end ? new Date(item.end) : new Date()
  const n = Math.max(1, Math.round((end.getTime() - new Date(item.start).getTime()) / (864e5 * 365)))
  return `${n} ${n === 1 ? 'год' : n < 5 ? 'года' : 'лет'}`
}

async function downloadPdf() {
  pdfLoading.value = true
  try {
    const blob = await apiBlob('/api/v1/candidates/me/profile.pdf')
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'profile.pdf'
    link.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось скачать PDF')
  } finally {
    pdfLoading.value = false
  }
}

async function loadTasks() {
  taskPhase.value = 'loading'
  taskError.value = ''
  try {
    tasks.value = asList<MicroTask>(await apiFetch<unknown>('/api/v1/assessment/micro-tasks'))
    for (const task of tasks.value) {
      if (answers[task.id] == null) answers[task.id] = ''
    }
    taskPhase.value = 'ready'
  } catch (e) {
    taskError.value = e instanceof Error ? e.message : 'Не удалось загрузить задания'
    taskPhase.value = 'error'
  }
}

async function sendAnswer(id: string) {
  const answer = (answers[id] || '').trim()
  if (answer.length < 20) {
    show('Ответ — не меньше 20 символов')
    return
  }
  try {
    await apiFetch(`/api/v1/assessment/micro-tasks/${encodeURIComponent(id)}/answer`, {
      method: 'POST',
      body: { answer },
    })
    show('Ответ отправлен')
    await loadTasks()
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось отправить ответ')
  }
}

onMounted(loadTasks)
onBeforeUnmount(() => { clearTimeout(pollTimer); clearTimeout(skillTimer) })
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Карьера" :user="userName" :links="candidateLinks" />
    <main class="fsp-page fsp-stack-32">
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <template v-if="profile">
          <section style="display: flex; flex-wrap: wrap; gap: 24px; align-items: center;">
            <FspCompanyLogo :name="profile.full_name" :size="88" />
            <div style="flex: 999 1 360px; min-width: 0;">
              <h1 style="margin: 0; font-size: 32px; line-height: 40px; font-weight: 700;">{{ profile.full_name }}</h1>
              <div style="margin-top: 6px; display: flex; flex-wrap: wrap; gap: 8px 20px; font-size: 15px; color: var(--text-muted);">
                <span>{{ categoryLabel(profile.specialization, profile.grade) }}</span>
                <span>{{ profile.city || 'Город не указан' }}<template v-if="profile.formats?.length"> · {{ profile.formats.map(f => FORMAT_LABEL[f]).join(', ') }}</template></span>
                <span v-if="profile.min_salary">от {{ rub(profile.min_salary) }}</span>
              </div>
              <div class="u-mt-12">
                <FspStatusBadge :status="profile.visible ? 'new' : 'archived'">{{ profile.visible ? 'Профиль виден работодателям' : 'Профиль скрыт' }}</FspStatusBadge>
              </div>
            </div>
            <div class="u-row-wrap">
              <FspButton variant="outline" size="sm" :disabled="pdfLoading" @click="downloadPdf">Скачать PDF</FspButton>
              <FspButton variant="plate" size="sm" href="/candidate/settings">Редактировать</FspButton>
            </div>
          </section>

          <p v-if="!profile.in_pool_eligible" style="margin: 0; padding: 16px 20px; background: var(--surface); box-shadow: inset 3px 0 0 var(--warning); font-size: 15px;">
            Без минимальной зарплаты и формата профиль не участвует в подборках.
          </p>
          <div v-if="!profile.grade" class="prof-banner">
            <div><b>Пройдите опрос и тест на грейд.</b> Категория определяется только тестом — без неё работодатели не найдут вас в подборках.</div>
            <FspButton size="sm" href="/candidate/onboarding" icon-right="arrow-right">Начать</FspButton>
          </div>

          <section style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 16px;">
            <FspPlate :dots="6">
              <div class="fsp-eyebrow fsp-eyebrow--plate">Ваша категория</div>
              <div class="fsp-display" style="font-size: 28px; line-height: 32px; margin: 10px 0 16px;">{{ categoryLabel(profile.specialization, profile.grade) }}</div>
              <div style="display: flex; gap: 32px;">
                <div><div class="fsp-display" style="font-size: 28px; line-height: 32px;">{{ profile.category_rank ?? '—' }}</div><div style="font-size: 13px; color: var(--on-plate-muted);">место из {{ profile.category_size ?? '—' }}</div></div>
                <div><div class="fsp-display" style="font-size: 28px; line-height: 32px;">{{ profile.grade_score ?? '—' }}</div><div style="font-size: 13px; color: var(--on-plate-muted);">балла за тест</div></div>
              </div>
              <div v-if="profile.ready_for_next" style="margin-top: 12px; font-size: 14px;">Готов к следующему грейду</div>
              <div style="margin-top: 16px;"><NuxtLink to="/candidate/grade" style="color: var(--on-plate); font-weight: 600; font-size: 14px;">Категория и грейд →</NuxtLink></div>
            </FspPlate>
            <NuxtLink to="/candidate/invites" class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 32px; text-decoration: none; color: var(--text); display: flex; flex-direction: column; gap: 8px;">
              <span class="fsp-eyebrow">Приглашения</span>
              <span class="fsp-display" style="font-size: 44px; line-height: 48px;">{{ incoming.length }} <span style="font-size: 16px; color: var(--text-muted);">новых</span></span>
              <span class="u-note">{{ incoming[0] ? incoming[0].company_name + ' — ' + salaryRange(incoming[0].salary_from, incoming[0].salary_to) : 'Пока нет входящих' }}</span>
              <span style="margin-top: auto; font-weight: 600; font-size: 14px;">Посмотреть →</span>
            </NuxtLink>
            <div class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 32px; display: flex; flex-direction: column; gap: 12px;">
              <span class="fsp-eyebrow">Участие в подборках</span>
              <span class="fsp-display u-h2">{{ profile.in_pool_eligible ? 'Да' : 'Нет' }}</span>
              <span class="u-note">{{ STATUS_LABEL[profile.status] }}. Активность: {{ shortDate(profile.last_active_at) }}</span>
            </div>
          </section>

          <section id="search" style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-direction: column; gap: 16px;">
            <h2 class="fsp-display u-h3">Условия поиска</h2>
            <div class="u-row-wrap">
              <FspChip v-for="s in screen.data.value?.specs ?? []" :key="s.id" :selected="spec === s.id" locked @click="spec = s.id as Spec">{{ s.name }}</FspChip>
            </div>
            <div class="u-row-wrap">
              <FspChip v-for="f in FORMATS" :key="f" :selected="formats.includes(f)" locked @click="toggleFormat(f)">{{ FORMAT_LABEL[f] }}</FspChip>
              <FspChip v-for="st in (['seeking', 'open', 'paused'] as Status[])" :key="st" :selected="status === st" locked @click="status = st">{{ STATUS_LABEL[st] }}</FspChip>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 12px;">
              <FspInput v-model="salary" label="Минимальная зарплата" suffix="₽" inputmode="numeric" />
              <FspInput v-model="city" label="Город" />
            </div>
            <FspInput v-model="softSkills" label="Гибкие навыки" hint="Через запятую" placeholder="коммуникация, менторство" />
            <FspButton size="sm" @click="saveSearch">Сохранить условия</FspButton>
          </section>

          <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-direction: column; gap: 12px;">
            <h2 class="fsp-display u-h3">Задание от работодателя</h2>
            <ScreenState :phase="taskPhase" :error="taskError" @retry="loadTasks">
              <p v-if="!tasks.length" class="u-muted-p">Заданий пока нет.</p>
              <div v-for="task in tasks" :key="task.id" style="display: flex; flex-direction: column; gap: 8px; padding-top: 12px;">
                <b>{{ task.title }}</b>
                <p v-if="task.body" style="margin: 0; font-size: 14px; line-height: 20px; color: var(--text-muted);">{{ task.body }}</p>
                <FspInput v-model="answers[task.id]" label="Ответ" hint="Не меньше 20 символов" />
                <div><FspButton size="sm" @click="sendAnswer(task.id)">Отправить</FspButton></div>
              </div>
            </ScreenState>
          </section>

          <section aria-label="Как подняться в выдаче" class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--accent-mark); --bw: var(--border-card); padding: 28px;">
            <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 18px;">Как подняться в выдаче · топ-3</h2>
            <p v-if="!hints.length" class="u-muted-p">Подсказок пока нет.</p>
            <div v-else style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 12px;">
              <div v-for="(h, i) in hints" :key="h.id" class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface-hover); padding: 20px; display: flex; flex-direction: column; gap: 8px;">
                <span class="fsp-display" style="font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 34px; height: 24px; display: inline-grid; place-items: center;">0{{ i + 1 }}</span>
                <b style="font-size: 16px; line-height: 22px;">{{ h.title }}</b>
                <span class="fsp-display" style="font-size: 22px; line-height: 28px;">{{ h.effect_text }}</span>
                <div style="margin-top: auto; padding-top: 8px;"><FspButton size="sm" :href="h.action_href">{{ h.action_label }}</FspButton></div>
              </div>
            </div>
          </section>

          <div style="display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start;">
            <div style="flex: 999 1 560px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
              <section class="fsp-section">
                <h2 class="fsp-display u-h3 u-mb-20">Подтверждённые навыки</h2>
                <p v-if="!tested.length" class="u-muted-p">Навыков с баллом теста пока нет.</p>
                <div v-else style="display: flex; flex-direction: column; gap: 14px;">
                  <div v-for="s in tested" :key="s.skill_id + s.source" style="display: grid; grid-template-columns: 160px 1fr 48px; gap: 16px; align-items: center; font-size: 15px;">
                    <span>{{ skillLabel(s.skill_id) }}</span>
                    <div class="fsp-meter"><div :style="{ width: Math.min(100, s.score || 0) + '%', height: '8px', background: scoreColor(s.score || 0) }" /></div>
                    <b class="u-right">{{ s.score }}</b>
                  </div>
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 24px; padding-top: 20px; box-shadow: inset 0 1px 0 var(--line);">
                  <span style="font-size: 13px; color: var(--text-muted); margin-right: 4px; align-self: center;">Без балла теста:</span>
                  <FspTag v-for="s in unverified" :key="s.skill_id + s.source">{{ skillLabel(s.skill_id) }}</FspTag>
                  <span v-if="!unverified.length" class="u-small">нет</span>
                </div>
              </section>

              <section class="fsp-section">
                <h2 class="fsp-display u-h3 u-mb-20">Опыт работы</h2>
                <p v-if="!profile.experiences?.length" class="u-muted-p">Опыт появится после подтверждения резюме.</p>
                <div v-else style="display: flex; flex-direction: column; gap: 20px;">
                  <div v-for="exp in profile.experiences" :key="exp.id" class="u-row-16" @mouseenter="hover = exp.id" @mouseleave="hover = ''">
                    <FspCompanyLogo :name="exp.company" :size="44" />
                    <div>
                      <div class="u-strong">{{ exp.role }}</div>
                      <div class="u-note-sm">{{ exp.company }} · {{ shortDate(exp.start) }} — {{ exp.end ? shortDate(exp.end) : 'сейчас' }}<template v-if="years(exp)"> · {{ years(exp) }}</template></div>
                      <div style="font-size: 14px; line-height: 20px; margin-top: 6px;">{{ exp.description }}</div>
                      <div v-if="hover === exp.id && exp.evidence_span" style="margin-top: 8px; font-size: 13px; line-height: 18px; background: var(--plate); color: var(--on-plate); padding: 8px 12px;">{{ exp.evidence_span }}</div>
                    </div>
                  </div>
                </div>
              </section>

              <section id="projects" style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-direction: column; gap: 16px;">
                <h2 class="fsp-display u-h3">Проекты</h2>
                <p v-if="!profile.projects?.length" class="u-muted-p">Проектов пока нет — добавьте первый через мастер.</p>
                <div v-for="p in profile.projects" :key="p.id" style="padding-bottom: 12px; box-shadow: inset 0 -1px 0 var(--line);">
                  <b>{{ p.task }}</b>
                  <div class="u-note-sm u-mt-4">{{ ROLE_LABEL[p.role] || p.role }} · {{ p.skills.map(skillLabel).join(', ') }}<template v-if="p.outcome"> · {{ p.outcome }}</template></div>
                </div>
                <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px; display: flex; flex-direction: column; gap: 12px;">
                  <div class="fsp-eyebrow">Мастер проекта · шаг {{ step }} из 3</div>
                  <template v-if="step === 1">
                    <FspInput v-model="task" label="Задача" />
                    <div class="u-row-wrap">
                      <FspChip v-for="r in (['owner', 'contributor', 'participant'] as ProjectRole[])" :key="r" :selected="role === r" locked @click="role = r">{{ ROLE_LABEL[r] }}</FspChip>
                    </div>
                    <FspButton size="sm" @click="task.trim() ? step = 2 : show('Опишите задачу')">Дальше</FspButton>
                  </template>
                  <template v-else-if="step === 2">
                    <FspInput v-model="skillQ" label="Технологии из онтологии" icon="search" placeholder="Go, Kafka…" @input="onSkillInput" />
                    <div class="u-row-wrap">
                      <button v-for="h in skillHits" :key="h.id" type="button" class="u-unbutton" @click="addSkill(h.id)"><FspTag>{{ h.name }}</FspTag></button>
                      <FspTag v-for="id in pickedSkills" :key="id">{{ skillLabel(id) }}</FspTag>
                    </div>
                    <div class="u-row">
                      <FspButton size="sm" variant="ghost" @click="step = 1">Назад</FspButton>
                      <FspButton size="sm" @click="pickedSkills.length ? step = 3 : show('Выберите технологию из подсказок')">Дальше</FspButton>
                    </div>
                  </template>
                  <template v-else>
                    <FspInput v-model="scale" label="Масштаб, необязательно" />
                    <FspInput v-model="outcome" label="Результат" />
                    <FspInput v-model="projectDate" label="Дата" type="date" />
                    <FspInput v-model="projectUrl" label="Ссылка" />
                    <div class="u-row">
                      <FspButton size="sm" variant="ghost" @click="step = 2">Назад</FspButton>
                      <FspButton size="sm" :disabled="savingProject" @click="saveProject">Сохранить проект</FspButton>
                    </div>
                  </template>
                </div>
              </section>

              <section v-if="draft" style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-direction: column; gap: 16px;">
                <h2 class="fsp-display u-h3">Подтвердите резюме</h2>
                <p style="margin: 0; font-size: 14px; color: var(--text-muted);">Наведите на поле — покажем цитату из резюме. Поле без цитаты не сохранится.</p>
                <div v-for="(exp, i) in draft.experiences ?? []" :key="'e' + i" style="display: flex; flex-direction: column; gap: 8px;" @mouseenter="hover = 'e' + i" @mouseleave="hover = ''">
                  <FspInput v-model="exp.company" label="Компания" />
                  <FspInput v-model="exp.role" label="Роль" />
                  <FspInput v-model="exp.description" label="Описание" />
                  <div v-if="hover === 'e' + i" style="font-size: 13px; background: var(--plate); color: var(--on-plate); padding: 8px 12px;">{{ exp.evidence_span }}</div>
                </div>
                <div v-for="(sk, i) in draft.skills ?? []" :key="'s' + i" @mouseenter="hover = 's' + i" @mouseleave="hover = ''">
                  <FspInput v-model="sk.name" label="Навык" />
                  <div v-if="hover === 's' + i" style="margin-top: 8px; font-size: 13px; background: var(--plate); color: var(--on-plate); padding: 8px 12px;">{{ sk.evidence_span }}</div>
                </div>
                <div v-for="(pr, i) in draft.projects ?? []" :key="'p' + i" @mouseenter="hover = 'p' + i" @mouseleave="hover = ''">
                  <FspInput v-model="pr.task" label="Проект из резюме" />
                  <div v-if="hover === 'p' + i" style="margin-top: 8px; font-size: 13px; background: var(--plate); color: var(--on-plate); padding: 8px 12px;">{{ pr.evidence_span }}</div>
                </div>
                <FspButton size="sm" @click="confirmResume">Подтвердить</FspButton>
              </section>
            </div>

            <aside style="flex: 1 1 380px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
              <section class="fsp-section fsp-stack-12">
                <div class="u-between">
                  <h2 class="fsp-display u-h3" style="margin: 0;">Рабочий стиль</h2>
                  <FspStatusBadge v-if="psych?.result" :status="psych.share_with_employers ? 'offer' : 'archived'">{{ psych.share_with_employers ? 'Виден работодателям' : 'Скрыт' }}</FspStatusBadge>
                </div>
                <template v-if="psych?.result">
                  <div class="u-strong-16">{{ psych.result.disc_profile.label }}</div>
                  <div v-for="sc in psych.result.scales" :key="sc.scale" class="prof-scale">
                    <span>{{ sc.title }}</span>
                    <div class="fsp-meter"><span :style="{ width: sc.pct + '%', background: levelColor(sc.level) }" /></div>
                    <b>{{ sc.pct }}</b>
                  </div>
                  <div><FspButton size="sm" variant="ghost" href="/candidate/psych">Подробнее</FspButton></div>
                </template>
                <template v-else>
                  <p class="u-note" style="margin: 0;">Тест рабочего стиля: DISC, лидерство, командность, стрессоустойчивость и трудоспособность. 20 минут, на грейд не влияет.</p>
                  <div><FspButton size="sm" variant="outline" href="/candidate/psych">{{ psych?.attempt ? 'Продолжить тест' : 'Пройти тест' }}</FspButton></div>
                </template>
              </section>
              <section id="fsp" class="fsp-section">
                <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 4px;">
                  <h2 class="fsp-display u-h3">Достижения ФСП</h2>
                  <img src="/brand/fsp-star-dark.svg" alt="" aria-hidden="true" class="fsp-only-dark" style="width: 28px; height: 28px;"><img src="/brand/fsp-star-light.svg" alt="" aria-hidden="true" class="fsp-only-light" style="width: 28px; height: 28px;">
                </div>
                <p v-if="!profile.fsp_achievements?.length" style="margin: 12px 0; color: var(--text-muted); font-size: 14px;">Пока не связаны.</p>
                <div v-else style="display: flex; flex-direction: column; gap: 16px; margin-top: 16px;">
                  <div v-for="a in profile.fsp_achievements" :key="a.id" style="display: flex; flex-direction: column; gap: 6px; padding-bottom: 16px; box-shadow: inset 0 -1px 0 var(--line);">
                    <div style="display: flex; justify-content: space-between; gap: 8px; align-items: center;">
                      <FspDisciplineBadge :discipline="a.discipline" />
                      <span class="fsp-display" style="font-size: 16px;">{{ a.place ? a.place + ' место' : 'Участие' }}</span>
                    </div>
                    <div class="u-strong">{{ a.event }}</div>
                    <div class="u-small">{{ a.year || '' }}</div>
                  </div>
                </div>
                <FspButton size="sm" variant="outline" style="margin-top: 16px;" @click="linkFsp">Связать ФСП ID</FspButton>
              </section>

              <section class="fsp-section">
                <h2 class="fsp-display" style="font-size: 16px; line-height: 20px; margin-bottom: 16px;">Резюме</h2>
                <div style="display: flex; gap: 12px; align-items: center;">
                  <FspIcon name="briefcase" :size="28" />
                  <div style="flex: 1; min-width: 0;">
                    <div style="font-weight: 600; font-size: 14px;">{{ resume ? 'PDF загружен' : 'Файл не загружен' }}</div>
                    <div class="u-small">{{ uploading ? 'Отправляем…' : resume ? (resume.status === 'parsing' ? 'Распознаём…' : resume.status === 'parsed' ? 'Проверьте поля' : resume.status === 'confirmed' ? 'Подтверждено' : resume.status) : 'PDF до 5 МБ и 5 страниц' }}</div>
                  </div>
                  <FspButton size="sm" variant="ghost" @click="cvInput?.click()">{{ resume ? 'Заменить' : 'Загрузить' }}</FspButton>
                  <input ref="cvInput" type="file" accept=".pdf,application/pdf" hidden @change="onCv">
                </div>
                <p v-if="resumeError" style="margin: 12px 0 0; color: var(--danger); font-size: 14px;">{{ resumeError }}</p>
              </section>
            </aside>
          </div>
        </template>
        <p v-else class="u-muted-p">Профиль пуст.</p>
      </ScreenState>
    </main>
  </div>
</template>

<style>
.prof-banner { display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: center; justify-content: space-between; padding: 16px 20px; background: var(--surface); box-shadow: inset 3px 0 0 var(--accent-mark); font-size: 15px; line-height: 22px; }
.prof-scale { display: grid; grid-template-columns: 150px 1fr 32px; gap: 12px; align-items: center; font-size: 14px; }
</style>
