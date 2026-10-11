<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'
import { apiFetch, asList } from '~/utils/raw'

type Spec = components['schemas']['Specialization']
type Grade = components['schemas']['Grade']
type WorkFormat = components['schemas']['WorkFormat']
type SkillHit = components['schemas']['SkillHit']
type Vacancy = {
  id: string
  title: string
  specialization?: string
  grades?: string[]
  salary_from?: number
  salary_to?: number
  description?: string
  domain?: string
  must_skills?: string[]
  formats?: string[]
  city?: string | null
  status?: string
}
useHead({ title: 'Вакансии — Карьера ФСП' })

const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => {
  const [vacancies, company, domains] = await Promise.all([
    apiFetch<unknown>('/api/v1/vacancies'),
    read(api.GET('/api/v1/companies/me')).catch(() => null),
    read(api.GET('/api/v1/taxonomy/domains')).catch(() => []),
  ])
  return {
    vacancies: asList<Vacancy>(vacancies).filter(v => !company || !('company_id' in v) || (v as Vacancy & { company_id?: string }).company_id === company.id),
    companyName: company?.name || 'Компания',
    domains,
  }
})

const specIds = Object.keys(SPEC_LABEL) as Spec[]
const editingId = ref('')
const title = ref('')
const spec = ref<Spec>('backend')
const grades = ref<Grade[]>(['middle'])
const salaryFrom = ref<string | number>('')
const salaryTo = ref<string | number>('')
const formats = ref<WorkFormat[]>(['remote'])
const city = ref('')
const description = ref('')
const domain = ref('fintech')
const skills = ref<string[]>([])
const skillQ = ref('')
const skillHits = ref<SkillHit[]>([])
const formError = ref('')
const saving = ref(false)
let skillTimer: ReturnType<typeof setTimeout> | undefined

function fork(row: { salary_from?: number; salary_to?: number }) {
  if (typeof row.salary_from === 'number' && typeof row.salary_to === 'number') return salaryRange(row.salary_from, row.salary_to)
  return '—'
}

function toggleGrade(g: Grade) {
  if (grades.value.includes(g)) {
    if (grades.value.length > 1) grades.value = grades.value.filter(x => x !== g)
    return
  }
  if (grades.value.length === 1) {
    const [current] = grades.value
    if (current && Math.abs(GRADES.indexOf(current) - GRADES.indexOf(g)) === 1) {
      grades.value = [...grades.value, g]
      return
    }
  }
  grades.value = [g]
}

function toggleFormat(f: WorkFormat) {
  formats.value = formats.value.includes(f) ? formats.value.filter(x => x !== f) : [...formats.value, f]
}

function onSkill() {
  clearTimeout(skillTimer)
  skillTimer = setTimeout(async () => {
    const q = skillQ.value.trim()
    skillHits.value = q ? await read(api.GET('/api/v1/taxonomy/skills', { params: { query: { q, limit: 8 } } })).catch(() => []) : []
  }, 200)
}
onBeforeUnmount(() => clearTimeout(skillTimer))

function addSkill(id: string) {
  if (skills.value.includes(id)) return
  if (skills.value.length >= 12) { show('Обязательных навыков не больше 12'); return }
  skills.value = [...skills.value, id]
  skillQ.value = ''
  skillHits.value = []
}

function resetForm() {
  editingId.value = ''
  title.value = ''
  spec.value = 'backend'
  grades.value = ['middle']
  salaryFrom.value = ''
  salaryTo.value = ''
  formats.value = ['remote']
  city.value = ''
  description.value = ''
  domain.value = 'fintech'
  skills.value = []
  formError.value = ''
}

function edit(v: Vacancy) {
  editingId.value = v.id
  title.value = v.title
  spec.value = (v.specialization as Spec) || 'backend'
  grades.value = (v.grades ?? ['middle']).filter((g): g is Grade => GRADES.includes(g as Grade))
  salaryFrom.value = v.salary_from ?? ''
  salaryTo.value = v.salary_to ?? ''
  formats.value = (v.formats ?? ['remote']).filter((f): f is WorkFormat => FORMATS.includes(f as WorkFormat))
  city.value = v.city ?? ''
  description.value = v.description ?? ''
  domain.value = v.domain ?? 'fintech'
  skills.value = [...(v.must_skills ?? [])]
  formError.value = ''
  if (import.meta.client) document.getElementById('vacancy-form')?.scrollIntoView({ behavior: 'smooth' })
}

async function submit() {
  formError.value = ''
  const from = parseMoney(salaryFrom.value)
  const to = parseMoney(salaryTo.value)
  if (!title.value.trim()) formError.value = 'Укажите название'
  else if (!Number.isFinite(from) || !Number.isFinite(to) || !from || !to) formError.value = 'Вилка обязательна: кандидат видит её до начала общения'
  else if (from > to) formError.value = 'Зарплата «от» не может быть больше «до»'
  else if (!formats.value.length) formError.value = 'Выберите хотя бы один формат работы'
  else if (description.value.trim().length < 50) formError.value = 'Описание — не меньше 50 символов'
  else if (!domain.value) formError.value = 'Выберите домен'
  else if (!skills.value.length) formError.value = 'Добавьте хотя бы один обязательный навык из онтологии'
  if (formError.value) return
  saving.value = true
  const body = {
    title: title.value.trim(),
    specialization: spec.value,
    grades: grades.value,
    salary_from: from,
    salary_to: to,
    description: description.value.trim(),
    domain: domain.value,
    must_skills: skills.value,
    formats: formats.value,
    city: city.value.trim() || null,
  }
  try {
    if (editingId.value) {
      await apiFetch(`/api/v1/vacancies/${encodeURIComponent(editingId.value)}`, { method: 'PUT', body })
      show('Вакансия обновлена')
    } else {
      await apiFetch('/api/v1/vacancies', { method: 'POST', body })
      show('Вакансия опубликована')
    }
    resetForm()
    await screen.load()
  } catch (e) {
    formError.value = e instanceof Error ? e.message : 'Не удалось сохранить вакансию'
  } finally {
    saving.value = false
  }
}

</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Для компаний" :user="screen.data.value?.companyName || 'Компания'" :links="employerLinks" />
    <main class="fsp-page fsp-stack-32">
      <div>
        <h1 class="fsp-display fsp-title">Вакансии</h1>
        <p class="u-muted-p" style="font-size: 16px;">Публичный каталог вакансий. Кандидаты не откликаются: найм идёт через приглашение из подборки, к нему можно прикрепить тестовое задание.</p>
      </div>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <form id="vacancy-form" class="fsp-cut fsp-card fsp-stack-16" @submit.prevent="submit">
          <div class="u-between">
            <h2 class="fsp-display u-h3" style="margin: 0;">{{ editingId ? 'Редактирование вакансии' : 'Новая вакансия' }}</h2>
            <FspButton v-if="editingId" variant="ghost" size="sm" @click="resetForm">Отменить редактирование</FspButton>
          </div>
          <FspInput v-model="title" label="Название" placeholder="Backend-разработчик (Go) в антифрод" />
          <div>
            <div class="fsp-eyebrow u-mb-10">Специализация</div>
            <div class="u-row-wrap">
              <FspChip v-for="id in specIds" :key="id" :selected="spec === id" locked @click="spec = id">{{ SPEC_LABEL[id] }}</FspChip>
            </div>
          </div>
          <div>
            <div class="fsp-eyebrow u-mb-10">Грейд · один или два соседних</div>
            <div class="u-row-wrap">
              <FspChip v-for="g in GRADES" :key="g" :selected="grades.includes(g)" locked @click="toggleGrade(g)">{{ GRADE_LABEL[g] }}</FspChip>
            </div>
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 12px;">
            <FspInput v-model="salaryFrom" label="Зарплата от" suffix="₽" inputmode="numeric" />
            <FspInput v-model="salaryTo" label="Зарплата до" suffix="₽" inputmode="numeric" />
            <FspInput v-model="city" label="Город" icon="pin" placeholder="Необязательно для удалёнки" />
          </div>
          <div>
            <div class="fsp-eyebrow u-mb-10">Формат работы</div>
            <div class="u-row-wrap">
              <FspChip v-for="f in FORMATS" :key="f" :selected="formats.includes(f)" locked @click="toggleFormat(f)">{{ FORMAT_LABEL[f] }}</FspChip>
            </div>
          </div>
          <div>
            <div class="fsp-eyebrow u-mb-10">Домен</div>
            <div class="u-row-wrap">
              <FspChip v-for="d in screen.data.value?.domains ?? []" :key="d.id" :selected="domain === d.id" locked @click="domain = d.id">{{ d.name }}</FspChip>
            </div>
          </div>
          <div style="position: relative;">
            <FspInput v-model="skillQ" label="Обязательные навыки" icon="search" placeholder="Go, PostgreSQL, Kafka…" autocomplete="off" hint="Навыки выбираются из онтологии платформы — так по ним работает подбор" @input="onSkill" />
            <div v-if="skillHits.length" class="u-row-wrap u-mt-6">
              <button v-for="h in skillHits" :key="h.id" type="button" class="u-unbutton" @click="addSkill(h.id)"><FspTag>+ {{ h.name }}</FspTag></button>
            </div>
            <div v-if="skills.length" class="u-row-wrap u-mt-12">
              <FspChip v-for="id in skills" :key="id" :selected="true" locked icon="x" :aria-label="'Убрать ' + skillLabel(id)" @click="skills = skills.filter(x => x !== id)">{{ skillLabel(id) }}</FspChip>
            </div>
          </div>
          <div class="fsp-stack-12" style="gap: 6px;">
            <label class="fsp-eyebrow" for="vacancy-description">Описание</label>
            <textarea id="vacancy-description" v-model="description" class="fsp-textarea" rows="5" placeholder="Чем занимается команда и что человек будет делать первые 3 месяца" />
            <span class="u-small">{{ description.trim().length }} / 50 символов минимум</span>
          </div>
          <p v-if="formError" role="alert" class="u-danger" style="margin: 0; font-size: 14px;">{{ formError }}</p>
          <div class="u-row-wrap"><FspButton type="submit" :disabled="saving">{{ editingId ? 'Сохранить изменения' : 'Опубликовать' }}</FspButton></div>
        </form>

        <section class="fsp-section fsp-stack-24">
          <h2 class="fsp-display u-h3">Мои вакансии</h2>
          <p class="u-note">Найм идёт из подборки: приглашение и тестовое задание отправляются кандидату напрямую.</p>
          <p v-if="!(screen.data.value?.vacancies.length)" class="u-muted-p">Опубликованных вакансий пока нет.</p>
          <article v-for="v in screen.data.value?.vacancies ?? []" :key="v.id" class="fsp-divider fsp-stack-12">
            <div class="u-between" style="align-items: baseline;">
              <div>
                <div class="u-lead">{{ v.title }}</div>
                <div class="u-note-sm u-mt-4">{{ SPEC_LABEL[v.specialization as Spec] ?? v.specialization }} · {{ (v.grades ?? []).map(g => GRADE_LABEL[g as Grade] ?? g).join(' / ') }}<template v-if="v.domain"> · {{ domainLabel(v.domain, screen.data.value?.domains) }}</template><template v-if="v.city"> · {{ v.city }}</template></div>
              </div>
              <div class="u-row-center">
                <b>{{ fork(v) }}</b>
                <FspButton size="sm" variant="outline" icon="edit" @click="edit(v)">Редактировать</FspButton>
              </div>
            </div>
            <div class="u-row-wrap">
              <FspTag v-for="skill in v.must_skills ?? []" :key="skill">{{ skillLabel(skill) }}</FspTag>
            </div>
          </article>
        </section>
      </ScreenState>
    </main>
  </div>
</template>

