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

useHead({ title: 'Вакансии — Карьера ФСП' })
const cabinetUser = useCabinetUser('Кандидат')

const screen = useScreen(async () => ({
  vacancies: asList<Vacancy>(await apiFetch<unknown>('/api/v1/vacancies')),
}))

const selectedId = ref('')
const detail = ref<Vacancy | null>(null)
const detailPhase = ref<'loading' | 'ready' | 'error'>('ready')
const detailError = ref('')

const vacancies = computed(() => screen.data.value?.vacancies ?? [])

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

const cardStyle = (on: boolean) => on
  ? '--cut: var(--cut-m); padding: 16px 20px; text-align: left; cursor: pointer; font: inherit; color: inherit; border: 0; width: 100%;'
  : '--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 16px 20px; text-align: left; cursor: pointer; font: inherit; color: inherit; border: 0; width: 100%; background: none;'
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Карьера" :user="cabinetUser" :links="candidateLinks" />
    <main class="fsp-page fsp-stack-32">
      <div>
        <h1 class="fsp-display fsp-title">Вакансии</h1>
        <p style="margin: 0; font-size: 16px; color: var(--text-muted);">Каталог открытых вакансий. Откликнуться нельзя: работодатель сам присылает приглашение, если профиль подходит.</p>
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
              <p v-if="!detail" class="u-muted-p">Выберите вакансию, чтобы увидеть вилку и описание.</p>
              <template v-else>
                <div class="u-note-sm">{{ detail.company_name || 'Компания' }}<template v-if="detail.city"> · {{ detail.city }}</template></div>
                <h2 style="margin: 8px 0 0; font-size: 32px; line-height: 40px; font-weight: 700;">{{ detail.title }}</h2>
                <div style="margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px;">
                  <FspTag v-if="detail.specialization">{{ categoryLabel(detail.specialization, detail.grades?.[0]) }}</FspTag>
                  <FspTag v-if="detail.domain">{{ detail.domain }}</FspTag>
                  <FspTag v-for="skill in detail.must_skills ?? []" :key="skill">{{ skillLabel(skill) }}</FspTag>
                </div>
                <p style="margin: 20px 0 0; font-size: 16px; line-height: 26px;">{{ detail.description }}</p>
                <FspPlate :dots="6" style="margin-top: 24px;">
                  <div class="fsp-eyebrow fsp-eyebrow--plate">Зарплата</div>
                  <div style="font-size: 30px; line-height: 36px; font-weight: 700; margin: 8px 0 16px;">{{ fork(detail) }}</div>
                  <p style="margin: 0; font-size: 14px; color: var(--on-plate-muted);">Отклик недоступен. Если компания захочет поговорить, приглашение придёт в раздел «Приглашения».</p>
                  <div style="margin-top: 16px;"><FspButton variant="outline" href="/candidate/invites">К приглашениям</FspButton></div>
                </FspPlate>
              </template>
            </ScreenState>
          </article>
        </div>
      </ScreenState>
    </main>
  </div>
</template>
