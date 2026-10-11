<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'

type Profile = components['schemas']['CandidateProfile'] & { soft_skills?: string[] }
type Parsed = components['schemas']['ParsedResume']
type ProjectRole = components['schemas']['ProjectRole']
type Spec = components['schemas']['Specialization']
type WorkFormat = components['schemas']['WorkFormat']
type Status = components['schemas']['CandidateStatus']

useHead({ title: 'Редактирование профиля — Карьера ФСП' })

const route = useRoute()
const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => {
  const [profile, specs] = await Promise.all([
    read(api.GET('/api/v1/candidates/me')),
    read(api.GET('/api/v1/taxonomy/specializations')),
  ])
  return { profile, specs }
})

const section = ref('search')
const sections = [
  { id: 'search', label: 'Условия поиска' },
  { id: 'projects', label: 'Проекты' },
  { id: 'resume', label: 'Резюме' },
  { id: 'fsp', label: 'ФСП ID' },
]
const navStyle = (on: boolean) => on
  ? 'padding: 12px 16px; font-weight: 600; text-decoration: none; color: var(--text); box-shadow: inset 3px 0 0 var(--accent-mark); background: var(--surface-hover);'
  : 'padding: 12px 16px; text-decoration: none; color: var(--text-muted);'

const city = ref('')
const salary = ref<string | number>('')
const softSkills = ref('')
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
const savingSearch = ref(false)

watch(screen.data, (bundle) => {
  const profile = bundle?.profile as Profile | undefined
  if (!profile) return
  city.value = profile.city ?? ''
  salary.value = profile.min_salary ?? ''
  formats.value = [...(profile.formats ?? [])]
  status.value = profile.status
  spec.value = profile.specialization ?? ''
  softSkills.value = (profile.soft_skills ?? []).join(', ')
}, { immediate: true })

const profile = computed(() => (screen.data.value?.profile ?? null) as Profile | null)
const userName = computed(() => profile.value?.display_name || '…')

function openSection(id: string) {
  section.value = id
  void navigateTo({ path: '/candidate/profile/edit', hash: `#${id}` }, { replace: true })
}

function toggleFormat(f: WorkFormat) {
  formats.value = formats.value.includes(f) ? formats.value.filter(x => x !== f) : [...formats.value, f]
}

async function refreshProfile() {
  const next = await read(api.GET('/api/v1/candidates/me'))
  if (screen.data.value) screen.data.value.profile = next
}

async function saveSearch() {
  const min = parseMoney(salary.value)
  savingSearch.value = true
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
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось сохранить')
  } finally {
    savingSearch.value = false
  }
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
    await refreshProfile()
    draft.value = null
    show('Резюме подтверждено — опыт и навыки появились в профиле')
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
    await refreshProfile()
    task.value = ''
    pickedSkills.value = []
    scale.value = ''
    outcome.value = ''
    projectDate.value = ''
    projectUrl.value = ''
    step.value = 1
    show('Проект сохранён')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось сохранить проект')
  } finally {
    savingProject.value = false
  }
}

onMounted(() => {
  const id = String(route.hash || '').replace('#', '')
  if (sections.some(item => item.id === id)) section.value = id
  if (id) nextTick(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
})
onBeforeUnmount(() => { clearTimeout(pollTimer); clearTimeout(skillTimer) })
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Карьера" :user="userName" :links="candidateLinks" />
    <main class="fsp-page">
      <NuxtLink to="/candidate/profile" style="display: inline-block; font-size: 14px; color: var(--text-muted); text-decoration: none; margin-bottom: 16px;">← К профилю</NuxtLink>
      <h1 class="fsp-display fsp-title" style="margin-bottom: 8px;">Редактирование профиля</h1>
      <p class="u-muted-p" style="margin: 0 0 32px;">Здесь меняются условия поиска, проекты, резюме и связь с ФСП. На вкладке профиля остаётся только то, что уже сохранено.</p>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <div class="fsp-columns">
          <nav aria-label="Разделы редактирования" class="edit-nav">
            <a v-for="sct in sections" :key="sct.id" :href="'#' + sct.id" :style="navStyle(section === sct.id)" @click.prevent="openSection(sct.id)">{{ sct.label }}</a>
          </nav>

          <div class="fsp-stack-24" style="flex: 999 1 640px; min-width: 0;">
            <section id="search" class="fsp-section">
              <h2 class="fsp-display u-h3 u-mb-8">Условия поиска</h2>
              <p class="u-note" style="margin: 0 0 20px;">Зарплата и формат нужны, чтобы попасть в подборки. Специализация должна совпадать с категорией теста.</p>
              <div class="fsp-stack-16">
                <div class="u-row-wrap">
                  <FspChip v-for="s in screen.data.value?.specs ?? []" :key="s.id" :selected="spec === s.id" locked @click="spec = s.id as Spec">{{ s.name }}</FspChip>
                </div>
                <div class="u-row-wrap">
                  <FspChip v-for="f in FORMATS" :key="f" :selected="formats.includes(f)" locked @click="toggleFormat(f)">{{ FORMAT_LABEL[f] }}</FspChip>
                </div>
                <div class="u-row-wrap">
                  <FspChip v-for="st in (['seeking', 'open', 'paused'] as Status[])" :key="st" :selected="status === st" locked @click="status = st">{{ STATUS_LABEL[st] }}</FspChip>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 12px;">
                  <FspInput v-model="salary" label="Минимальная зарплата" suffix="₽" inputmode="numeric" />
                  <FspInput v-model="city" label="Город" />
                </div>
                <FspInput v-model="softSkills" label="Гибкие навыки" hint="Через запятую" placeholder="коммуникация, менторство" />
                <FspButton size="sm" :disabled="savingSearch" @click="saveSearch">Сохранить условия</FspButton>
              </div>
            </section>

            <section id="projects" class="fsp-section">
              <h2 class="fsp-display u-h3 u-mb-8">Проекты</h2>
              <p class="u-note" style="margin: 0 0 20px;">Добавленные проекты сразу видны в профиле и участвуют в матчинге.</p>
              <div v-if="profile?.projects?.length" class="fsp-stack-12" style="margin-bottom: 20px;">
                <div v-for="p in profile.projects" :key="p.id" style="padding-bottom: 12px; box-shadow: inset 0 -1px 0 var(--line);">
                  <b>{{ p.task }}</b>
                  <div class="u-note-sm u-mt-4">{{ ROLE_LABEL[p.role] || p.role }} · {{ p.skills.map(skillLabel).join(', ') }}<template v-if="p.outcome"> · {{ p.outcome }}</template></div>
                </div>
              </div>
              <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px; display: flex; flex-direction: column; gap: 12px;">
                <div class="fsp-eyebrow">Новый проект · шаг {{ step }} из 3</div>
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

            <section id="resume" class="fsp-section">
              <h2 class="fsp-display u-h3 u-mb-8">Резюме</h2>
              <p class="u-note" style="margin: 0 0 20px;">PDF до 5 МБ и 5 страниц. После распознавания нужно подтвердить поля — без цитаты из файла они не сохранятся.</p>
              <div style="display: flex; gap: 12px; align-items: center;">
                <FspIcon name="briefcase" :size="28" />
                <div style="flex: 1; min-width: 0;">
                  <div style="font-weight: 600; font-size: 14px;">{{ resume ? 'PDF загружен' : 'Файл не загружен' }}</div>
                  <div class="u-small">{{ uploading ? 'Отправляем…' : resume ? (resume.status === 'parsing' ? 'Распознаём…' : resume.status === 'parsed' ? 'Проверьте поля ниже' : resume.status === 'confirmed' ? 'Подтверждено' : resume.status) : 'Опыт и навыки из резюме появятся в профиле после подтверждения' }}</div>
                </div>
                <FspButton size="sm" variant="outline" @click="cvInput?.click()">{{ resume ? 'Заменить' : 'Загрузить PDF' }}</FspButton>
                <input ref="cvInput" type="file" accept=".pdf,application/pdf" hidden @change="onCv">
              </div>
              <p v-if="resumeError" style="margin: 12px 0 0; color: var(--danger); font-size: 14px;">{{ resumeError }}</p>
              <div v-if="draft" class="fsp-stack-16" style="margin-top: 24px;">
                <h3 class="fsp-display u-h3" style="margin: 0;">Подтвердите распознанные поля</h3>
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
              </div>
            </section>

            <section id="fsp" class="fsp-section">
              <div class="u-row-center" style="gap: 20px;">
                <img src="/brand/fsp-star-dark.svg" alt="" aria-hidden="true" class="fsp-only-dark" style="width: 56px; height: 56px;"><img src="/brand/fsp-star-light.svg" alt="" aria-hidden="true" class="fsp-only-light" style="width: 56px; height: 56px;">
                <div style="flex: 1 1 280px; min-width: 0;">
                  <h2 class="fsp-display u-h3">ФСП ID</h2>
                  <div class="u-mt-6">
                    <FspStatusBadge v-if="profile?.fsp_achievements?.length" status="new">Связан</FspStatusBadge>
                    <FspStatusBadge v-else status="archived">Не привязан</FspStatusBadge>
                  </div>
                  <div class="u-note" style="margin-top: 8px;">{{ profile?.fsp_achievements?.length ? `В профиле ${profile.fsp_achievements.length} достижений.` : 'После связи результаты соревнований появятся в профиле и поднимут вас в выдаче.' }}</div>
                </div>
                <FspButton size="sm" @click="linkFsp">{{ profile?.fsp_achievements?.length ? 'Обновить' : 'Связать ФСП ID' }}</FspButton>
              </div>
            </section>

            <div class="u-row-wrap" style="justify-content: flex-end; padding-top: 8px;">
              <FspButton variant="ghost" href="/candidate/profile">Смотреть профиль</FspButton>
            </div>
          </div>
        </div>
      </ScreenState>
    </main>
  </div>
</template>

<style>
.edit-nav { flex: 1 1 220px; display: flex; flex-direction: column; gap: 4px; position: sticky; top: 88px; }
@media (max-width: 960px) {
  .edit-nav { position: static; flex-direction: row; flex-wrap: wrap; flex-basis: 100%; }
}
</style>
