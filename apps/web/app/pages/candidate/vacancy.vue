<script setup lang="ts">
import { apiFetch, asList } from '~/utils/raw'

type Vacancy = {
  id: string
  title: string
  company_name?: string
  specialization?: string
  grades?: string[]
  salary_from?: number
  salary_to?: number
  description?: string
  domain?: string
  must_skills?: string[]
  city?: string | null
}

type AppRow = {
  id: string
  vacancy_id?: string
  status?: string
  title?: string
  company_name?: string
  salary_from?: number
  salary_to?: number
}

useHead({ title: 'Вакансии — Карьера ФСП' })
const cabinetUser = useCabinetUser('Кандидат')

const { show } = useToast()
const screen = useScreen(async () => {
  const [vacancies, applications] = await Promise.all([
    apiFetch<unknown>('/api/v1/vacancies'),
    apiFetch<unknown>('/api/v1/applications', { query: { role: 'candidate' } }),
  ])
  return { vacancies: asList<Vacancy>(vacancies), applications: asList<AppRow>(applications) }
})

const selectedId = ref('')
const detail = ref<Vacancy | null>(null)
const detailPhase = ref<'loading' | 'ready' | 'error'>('ready')
const detailError = ref('')
const applying = ref(false)
const coverLetter = ref('')

const vacancies = computed(() => screen.data.value?.vacancies ?? [])
const applications = computed(() => screen.data.value?.applications ?? [])
const appliedIds = computed(() => new Set(applications.value.map(row => row.vacancy_id).filter(Boolean)))

function fork(row: { salary_from?: number; salary_to?: number }) {
  if (typeof row.salary_from === 'number' && typeof row.salary_to === 'number') return salaryRange(row.salary_from, row.salary_to)
  return '—'
}

async function openVacancy(id: string) {
  selectedId.value = id
  detailPhase.value = 'loading'
  detailError.value = ''
  try {
    detail.value = await apiFetch<Vacancy>(`/api/v1/vacancies/${encodeURIComponent(id)}`)
    detailPhase.value = 'ready'
  } catch (e) {
    detail.value = null
    detailError.value = e instanceof Error ? e.message : 'Не удалось открыть вакансию'
    detailPhase.value = 'error'
  }
}

async function apply() {
  const id = detail.value?.id
  if (!id || applying.value) return
  applying.value = true
  try {
    await apiFetch(`/api/v1/vacancies/${encodeURIComponent(id)}/applications`, {
      method: 'POST',
      body: { message: coverLetter.value.trim() || 'Хочу рассмотреть эту вакансию' },
    })
    const fresh = asList<AppRow>(await apiFetch<unknown>('/api/v1/applications', { query: { role: 'candidate' } }))
    if (screen.data.value) screen.data.value.applications = fresh
    coverLetter.value = ''
    show('Отклик отправлен — компания увидит ваши контакты')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось откликнуться')
  } finally {
    applying.value = false
  }
}

const cardStyle = (on: boolean) => on
  ? '--cut: var(--cut-m); padding: 16px 20px; text-align: left; cursor: pointer; font: inherit; color: inherit; border: 0; width: 100%;'
  : '--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 16px 20px; text-align: left; cursor: pointer; font: inherit; color: inherit; border: 0; width: 100%; background: none;'
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Карьера" :user="cabinetUser" :links="candidateLinks" logo-dark="/brand/championship-logo-white.svg" logo-light="/brand/championship-logo-navy.svg" />
    <main class="fsp-page fsp-stack-32">
      <div>
        <h1 class="fsp-display fsp-title">Вакансии</h1>
        <p style="margin: 0; font-size: 16px; color: var(--text-muted);">Открытые вакансии и ваши отклики.</p>
      </div>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <div class="fsp-columns">
          <section style="flex: 1 1 320px; min-width: 0; display: flex; flex-direction: column; gap: 12px;">
            <p v-if="!vacancies.length" class="u-muted-p">Открытых вакансий пока нет.</p>
            <button v-for="v in vacancies" :key="v.id" type="button" :class="['fsp-cut', selectedId === v.id && 'fsp-active']" :style="cardStyle(selectedId === v.id)" @click="openVacancy(v.id)">
              <span style="display: block; font-weight: 600; font-size: 16px;">{{ v.title }}</span>
              <span style="display: block; margin-top: 4px; font-size: 14px; color: var(--text-muted);">{{ v.company_name || 'Компания' }}</span>
              <span style="display: block; margin-top: 8px; font-weight: 700;">{{ fork(v) }}</span>
            </button>
          </section>
          <article style="flex: 999 1 520px; min-width: 0;">
            <ScreenState :phase="detailPhase" :error="detailError" @retry="selectedId && openVacancy(selectedId)">
              <p v-if="!detail" class="u-muted-p">Выберите вакансию, чтобы увидеть вилку и откликнуться.</p>
              <template v-else>
                <div class="u-note-sm">{{ detail.company_name || 'Компания' }}<template v-if="detail.city"> · {{ detail.city }}</template></div>
                <h2 style="margin: 8px 0 0; font-size: 32px; line-height: 40px; font-weight: 700;">{{ detail.title }}</h2>
                <div style="margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px;">
                  <FspTag v-if="detail.specialization">{{ categoryLabel(detail.specialization, detail.grades?.[0]) }}</FspTag>
                  <FspTag v-if="detail.domain">{{ detail.domain }}</FspTag>
                  <FspTag v-for="skill in detail.must_skills ?? []" :key="skill">{{ skillLabel(skill) }}</FspTag>
                </div>
                <p style="margin: 20px 0 0; font-size: 16px; line-height: 26px;">{{ detail.description }}</p>
                <div v-if="!appliedIds.has(detail.id)" class="fsp-stack-12" style="margin-top: 24px;">
                  <label class="fsp-eyebrow" for="cover-letter">Сопроводительное сообщение · необязательно</label>
                  <textarea id="cover-letter" v-model="coverLetter" class="fsp-textarea" rows="4" maxlength="4000" placeholder="Коротко: почему вам интересна эта вакансия и что вы уже делали похожего" />
                </div>
                <FspPlate :dots="6" style="margin-top: 24px;">
                  <div class="fsp-eyebrow fsp-eyebrow--plate">Зарплата</div>
                  <div style="font-size: 30px; line-height: 36px; font-weight: 700; margin: 8px 0 16px;">{{ fork(detail) }}</div>
                  <template v-if="!appliedIds.has(detail.id)">
                    <FspButton size="lg" :block="true" :disabled="applying" @click="apply">Откликнуться</FspButton>
                    <p style="margin: 10px 0 0; font-size: 13px; color: var(--on-plate-muted);">Откликнувшись, вы открываете компании свои контакты.</p>
                  </template>
                  <div v-else class="u-strong">Отклик отправлен</div>
                </FspPlate>
              </template>
            </ScreenState>
          </article>
        </div>
        <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line); margin-top: 32px;">
          <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 16px;">Мои отклики</h2>
          <p v-if="!applications.length" class="u-muted-p">Откликов пока нет.</p>
          <div v-for="row in applications" :key="row.id" style="padding: 16px 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: baseline;">
            <div style="flex: 999 1 280px; min-width: 0;">
              <div class="u-strong">{{ row.title || 'Вакансия' }}</div>
              <div class="u-note-sm u-mt-4">{{ row.company_name || 'Компания' }}</div>
            </div>
            <div style="font-weight: 700;">{{ fork(row) }}</div>
            <FspStatusBadge v-if="row.status" :status="inviteTone(row.status)">{{ inviteLabel(row.status) }}</FspStatusBadge>
          </div>
        </section>
      </ScreenState>
    </main>
  </div>
</template>
