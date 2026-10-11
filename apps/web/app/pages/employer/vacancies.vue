<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'
import { apiFetch, asList } from '~/utils/raw'

type Spec = components['schemas']['Specialization']
type Grade = components['schemas']['Grade']
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
  status?: string
}
type AppRow = {
  id: string
  vacancy_id?: string
  status?: string
  candidate_display_name?: string
  candidate_email?: string | null
  message?: string
}

useHead({ title: 'Вакансии — Карьера ФСП' })

const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => {
  const [vacancies, applications, company] = await Promise.all([
    apiFetch<unknown>('/api/v1/vacancies'),
    apiFetch<unknown>('/api/v1/applications', { query: { role: 'employer' } }),
    read(api.GET('/api/v1/companies/me')).catch(() => null),
  ])
  return {
    vacancies: asList<Vacancy>(vacancies),
    applications: asList<AppRow>(applications),
    companyName: company?.name || 'Компания',
  }
})

const specIds = Object.keys(SPEC_LABEL) as Spec[]
const title = ref('')
const spec = ref<Spec>('backend')
const grade = ref<Grade>('middle')
const salaryFrom = ref<string | number>('')
const salaryTo = ref<string | number>('')
const description = ref('')
const domain = ref('fintech')
const skillsText = ref('')
const formError = ref('')
const saving = ref(false)

function fork(row: { salary_from?: number; salary_to?: number }) {
  if (typeof row.salary_from === 'number' && typeof row.salary_to === 'number') return salaryRange(row.salary_from, row.salary_to)
  return '—'
}

function appsFor(id: string) {
  return (screen.data.value?.applications ?? []).filter(row => row.vacancy_id === id)
}

async function publish() {
  formError.value = ''
  const from = parseMoney(salaryFrom.value)
  const to = parseMoney(salaryTo.value)
  const must = skillsText.value.split(',').map(item => item.trim()).filter(Boolean)
  if (!title.value.trim()) formError.value = 'Укажите название'
  else if (!Number.isFinite(from) || !Number.isFinite(to)) formError.value = 'Вилка обязательна'
  else if (from > to) formError.value = 'Зарплата «от» не может быть больше «до»'
  else if (description.value.trim().length < 50) formError.value = 'Описание — не меньше 50 символов'
  else if (!domain.value.trim()) formError.value = 'Укажите домен'
  else if (!must.length) formError.value = 'Укажите обязательные навыки через запятую'
  if (formError.value) return
  saving.value = true
  try {
    await apiFetch('/api/v1/vacancies', {
      method: 'POST',
      body: {
        title: title.value.trim(),
        specialization: spec.value,
        grades: [grade.value],
        salary_from: from,
        salary_to: to,
        description: description.value.trim(),
        domain: domain.value.trim(),
        must_skills: must,
        formats: ['remote'],
        city: null,
      },
    })
    show('Вакансия опубликована')
    await screen.load()
  } catch (e) {
    formError.value = e instanceof Error ? e.message : 'Не удалось опубликовать вакансию'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Для компаний" :user="screen.data.value?.companyName || 'Компания'" :links="employerLinks" />
    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px; display: flex; flex-direction: column; gap: 32px;">
      <div>
        <h1 class="fsp-display" style="font-size: 40px; line-height: 44px; margin-bottom: 8px;">Вакансии</h1>
        <p style="margin: 0; font-size: 16px; color: var(--text-muted);">Публикация и отклики кандидатов. Почта видна после их отклика.</p>
      </div>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <form style="display: flex; flex-direction: column; gap: 16px; padding-bottom: 8px;" @submit.prevent="publish">
          <FspInput v-model="title" label="Название" />
          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Специализация</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="id in specIds" :key="id" :selected="spec === id" locked @click="spec = id">{{ SPEC_LABEL[id] }}</FspChip>
            </div>
          </div>
          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Грейд</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="g in GRADES" :key="g" :selected="grade === g" locked @click="grade = g">{{ GRADE_LABEL[g] }}</FspChip>
            </div>
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 12px;">
            <FspInput v-model="salaryFrom" label="Зарплата от" suffix="₽" inputmode="numeric" />
            <FspInput v-model="salaryTo" label="Зарплата до" suffix="₽" inputmode="numeric" />
            <FspInput v-model="domain" label="Домен" placeholder="fintech" />
          </div>
          <FspInput v-model="skillsText" label="Обязательные навыки" hint="Идентификаторы через запятую: go, postgresql" />
          <FspInput v-model="description" label="Описание" :hint="`${description.trim().length} / 50`" />
          <p v-if="formError" style="margin: 0; color: var(--danger); font-size: 14px;">{{ formError }}</p>
          <div><FspButton type="submit" :disabled="saving">Опубликовать</FspButton></div>
        </form>

        <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-direction: column; gap: 20px;">
          <h2 class="fsp-display" style="font-size: 20px; line-height: 24px;">Мои вакансии</h2>
          <p v-if="!(screen.data.value?.vacancies.length)" style="margin: 0; color: var(--text-muted);">Опубликованных вакансий пока нет.</p>
          <article v-for="v in screen.data.value?.vacancies ?? []" :key="v.id" style="padding: 20px 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-direction: column; gap: 12px;">
            <div style="display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: baseline; justify-content: space-between;">
              <div>
                <div style="font-size: 18px; font-weight: 600;">{{ v.title }}</div>
                <div style="font-size: 14px; color: var(--text-muted); margin-top: 4px;">{{ categoryLabel(v.specialization, v.grades?.[0]) }}<template v-if="v.domain"> · {{ v.domain }}</template></div>
              </div>
              <div style="font-weight: 700;">{{ fork(v) }}</div>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspTag v-for="skill in v.must_skills ?? []" :key="skill">{{ skillLabel(skill) }}</FspTag>
            </div>
            <div>
              <div style="font-size: 13px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">Отклики</div>
              <p v-if="!appsFor(v.id).length" style="margin: 0; color: var(--text-muted);">Откликов пока нет.</p>
              <div v-for="a in appsFor(v.id)" :key="a.id" style="padding: 10px 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: baseline;">
                <b>{{ a.candidate_display_name || 'Кандидат' }}</b>
                <FspStatusBadge v-if="a.status" :status="inviteTone(a.status)">{{ inviteLabel(a.status) }}</FspStatusBadge>
                <span v-if="a.candidate_email">{{ a.candidate_email }}</span>
                <span v-if="a.message" style="color: var(--text-muted);">{{ a.message }}</span>
              </div>
            </div>
          </article>
        </section>
      </ScreenState>
    </main>
  </div>
</template>
