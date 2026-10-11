<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'
import { apiBlob, apiFetch } from '~/utils/raw'
import { boostUntilLabel, type DailyStory, type DailyTask } from '~/utils/daily'
import { levelColor, type PsychState } from '~/utils/psych'

type Profile = components['schemas']['CandidateProfile'] & { soft_skills?: string[]; daily_stories?: DailyStory[] }

useHead({ title: 'Профиль кандидата — Карьера ФСП' })

const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => {
  const [profile, hints, invites] = await Promise.all([
    read(api.GET('/api/v1/candidates/me')),
    read(api.GET('/api/v1/candidates/me/hints')),
    read(api.GET('/api/v1/invitations', { params: { query: { role: 'candidate' } } })),
  ])
  return { profile, hints, invites }
})

const psych = ref<PsychState | null>(null)
const daily = ref<DailyTask | null>(null)
const dailyText = ref('')
const dailySending = ref(false)
const dailyError = ref('')
const pdfLoading = ref(false)
const hover = ref('')

onMounted(async () => {
  try {
    psych.value = await apiFetch<PsychState>('/api/v1/psych/me')
  } catch {
    psych.value = null
  }
  try {
    daily.value = await apiFetch<DailyTask>('/api/v1/candidates/me/daily-task')
    if (daily.value.answer) dailyText.value = daily.value.answer
  } catch {
    daily.value = null
  }
})

async function submitDaily() {
  dailyError.value = ''
  dailySending.value = true
  try {
    daily.value = await apiFetch<DailyTask>('/api/v1/candidates/me/daily-task', {
      method: 'POST',
      body: { answer: dailyText.value },
    })
    show(daily.value.boost_until
      ? `Ответ в профиле. Буст в подборках до ${boostUntilLabel(daily.value.boost_until)}.`
      : 'Ответ сохранён в профиле')
    await screen.load()
  } catch (e) {
    dailyError.value = e instanceof Error ? e.message : 'Не удалось сохранить ответ'
  } finally {
    dailySending.value = false
  }
}

const profile = computed(() => (screen.data.value?.profile ?? null) as Profile | null)
const stories = computed(() => daily.value?.stories ?? profile.value?.daily_stories ?? [])
const hints = computed(() => [...(screen.data.value?.hints ?? [])].sort((a, b) => b.priority - a.priority).slice(0, 3))
const incoming = computed(() => (screen.data.value?.invites.items ?? []).filter(i => i.status === 'sent' || i.status === 'viewed'))
const tested = computed(() => (profile.value?.skills ?? []).filter(s => s.source === 'test' && s.score != null))
const unverified = computed(() => (profile.value?.skills ?? []).filter(s => s.source !== 'test' || s.score == null))
const softSkills = computed(() => profile.value?.soft_skills ?? [])
const userName = computed(() => profile.value?.display_name || '…')

function years(item: NonNullable<Profile['experiences']>[number]) {
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
                <span v-if="profile.city">{{ profile.city }}<template v-if="profile.formats?.length"> · {{ profile.formats.map(f => FORMAT_LABEL[f]).join(', ') }}</template></span>
                <span v-else-if="profile.formats?.length">{{ profile.formats.map(f => FORMAT_LABEL[f]).join(', ') }}</span>
                <span v-if="profile.min_salary">от {{ rub(profile.min_salary) }}</span>
              </div>
              <div v-if="softSkills.length" class="u-row-wrap u-mt-12">
                <FspTag v-for="skill in softSkills" :key="skill">{{ skill }}</FspTag>
              </div>
              <div class="u-mt-12">
                <FspStatusBadge :status="profile.visible ? 'new' : 'archived'">{{ profile.visible ? 'Профиль виден работодателям' : 'Профиль скрыт' }}</FspStatusBadge>
              </div>
            </div>
            <div class="u-row-wrap">
              <FspButton variant="outline" size="sm" :disabled="pdfLoading" @click="downloadPdf">Скачать PDF</FspButton>
              <FspButton variant="plate" size="sm" href="/candidate/profile/edit">Редактировать</FspButton>
            </div>
          </section>

          <p v-if="!profile.in_pool_eligible" style="margin: 0; padding: 16px 20px; background: var(--surface); box-shadow: inset 3px 0 0 var(--warning); font-size: 15px;">
            Без минимальной зарплаты и формата профиль не участвует в подборках.
            <NuxtLink to="/candidate/profile/edit#search" class="fsp-link" style="margin-left: 8px;">Заполнить условия</NuxtLink>
          </p>
          <div v-if="!profile.grade" class="prof-banner">
            <div><b>Категории ещё нет.</b> Её ставит только тест на грейд — без неё работодатели не найдут вас в подборках.</div>
            <FspButton size="sm" href="/candidate/onboarding" icon-right="arrow-right">Пройти тест</FspButton>
          </div>

          <section class="fsp-cut fsp-card" style="--edge: var(--accent-mark);">
            <div class="fsp-eyebrow">Ежедневная задача</div>
            <h2 class="fsp-display u-h3" style="margin: 10px 0 8px;">{{ daily?.prompt || 'Опиши свой лучший опыт использования Redis.' }}</h2>
            <p class="u-note" style="margin: 0 0 16px;">{{ daily?.hint || 'Ответ появится в профиле — его увидят работодатели. За выполнение даётся буст в подборках на весь следующий день.' }}</p>
            <template v-if="daily?.answered">
              <p style="margin: 0 0 12px; font-size: 15px; line-height: 22px;">{{ daily.answer }}</p>
              <FspStatusBadge status="offer">{{ daily.boost_active ? `Буст действует до ${boostUntilLabel(daily.boost_until)}` : 'Задание на сегодня выполнено' }}</FspStatusBadge>
            </template>
            <template v-else>
              <textarea v-model="dailyText" rows="5" class="fsp-textarea" placeholder="Как вы применяли этот инструмент в работе — задача, решение и результат." />
              <p v-if="dailyError" class="u-danger" style="margin: 8px 0 0;">{{ dailyError }}</p>
              <div style="margin-top: 12px;">
                <FspButton :disabled="dailySending || dailyText.trim().length < 40" @click="submitDaily">{{ dailySending ? 'Сохраняем…' : 'Отправить и получить буст' }}</FspButton>
              </div>
              <p class="u-small u-mt-4">Минимум 40 символов. Завтра придёт другой вопрос.</p>
            </template>
          </section>

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

          <section v-if="hints.length" aria-label="Как подняться в выдаче" class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--accent-mark); --bw: var(--border-card); padding: 28px;">
            <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 18px;">Как подняться в выдаче · топ-3</h2>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 12px;">
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
              <section v-if="tested.length || unverified.length" class="fsp-section">
                <h2 class="fsp-display u-h3 u-mb-20">Навыки</h2>
                <div v-if="tested.length" style="display: flex; flex-direction: column; gap: 14px;">
                  <div v-for="s in tested" :key="s.skill_id + s.source" style="display: grid; grid-template-columns: 160px 1fr 48px; gap: 16px; align-items: center; font-size: 15px;">
                    <span>{{ skillLabel(s.skill_id) }}</span>
                    <div class="fsp-meter"><div :style="{ width: Math.min(100, s.score || 0) + '%', height: '8px', background: scoreColor(s.score || 0) }" /></div>
                    <b class="u-right">{{ s.score }}</b>
                  </div>
                </div>
                <div v-if="unverified.length" style="display: flex; flex-wrap: wrap; gap: 8px;" :style="tested.length ? 'margin-top: 24px; padding-top: 20px; box-shadow: inset 0 1px 0 var(--line);' : ''">
                  <span style="font-size: 13px; color: var(--text-muted); margin-right: 4px; align-self: center;">Без балла теста:</span>
                  <FspTag v-for="s in unverified" :key="s.skill_id + s.source">{{ skillLabel(s.skill_id) }}</FspTag>
                </div>
              </section>

              <section v-if="profile.experiences?.length" class="fsp-section">
                <h2 class="fsp-display u-h3 u-mb-20">Опыт работы</h2>
                <div style="display: flex; flex-direction: column; gap: 20px;">
                  <div v-for="exp in profile.experiences" :key="exp.id" class="u-row-16" @mouseenter="hover = exp.id" @mouseleave="hover = ''">
                    <FspCompanyLogo :name="exp.company" :size="44" />
                    <div>
                      <div class="u-strong">{{ exp.role }}</div>
                      <div class="u-note-sm">{{ exp.company }} · {{ shortDate(exp.start) }} — {{ exp.end ? shortDate(exp.end) : 'сейчас' }}<template v-if="years(exp)"> · {{ years(exp) }}</template></div>
                      <div v-if="exp.description" style="font-size: 14px; line-height: 20px; margin-top: 6px;">{{ exp.description }}</div>
                      <div v-if="hover === exp.id && exp.evidence_span" style="margin-top: 8px; font-size: 13px; line-height: 18px; background: var(--plate); color: var(--on-plate); padding: 8px 12px;">{{ exp.evidence_span }}</div>
                    </div>
                  </div>
                </div>
              </section>

              <section v-if="stories.length" class="fsp-section">
                <h2 class="fsp-display u-h3 u-mb-20">Опыт из ежедневных задач</h2>
                <div v-for="story in stories" :key="story.id" style="padding-bottom: 16px; box-shadow: inset 0 -1px 0 var(--line);">
                  <div class="u-strong">{{ story.skill_label }}</div>
                  <div class="u-note-sm u-mt-4">{{ story.prompt }}</div>
                  <p style="margin: 8px 0 0; font-size: 15px; line-height: 22px;">{{ story.answer }}</p>
                </div>
              </section>

              <section v-if="profile.projects?.length" class="fsp-section">
                <h2 class="fsp-display u-h3 u-mb-20">Проекты</h2>
                <div v-for="p in profile.projects" :key="p.id" style="padding-bottom: 12px; box-shadow: inset 0 -1px 0 var(--line);">
                  <b>{{ p.task }}</b>
                  <div class="u-note-sm u-mt-4">{{ ROLE_LABEL[p.role] || p.role }} · {{ p.skills.map(skillLabel).join(', ') }}<template v-if="p.outcome"> · {{ p.outcome }}</template></div>
                </div>
              </section>
            </div>

            <aside style="flex: 1 1 380px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
              <section v-if="psych?.result" class="fsp-section fsp-stack-12">
                <div class="u-between">
                  <h2 class="fsp-display u-h3" style="margin: 0;">Рабочий стиль</h2>
                  <FspStatusBadge :status="psych.share_with_employers ? 'offer' : 'archived'">{{ psych.share_with_employers ? 'Виден работодателям' : 'Скрыт' }}</FspStatusBadge>
                </div>
                <div class="u-strong-16">{{ psych.result.disc_profile.label }}</div>
                <div v-for="sc in psych.result.scales" :key="sc.scale" class="prof-scale">
                  <span>{{ sc.title }}</span>
                  <div class="fsp-meter"><span :style="{ width: sc.pct + '%', background: levelColor(sc.level) }" /></div>
                  <b>{{ sc.pct }}</b>
                </div>
                <div><FspButton size="sm" variant="ghost" href="/candidate/psych">Подробнее</FspButton></div>
              </section>
              <section v-if="profile.fsp_achievements?.length" class="fsp-section">
                <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 4px;">
                  <h2 class="fsp-display u-h3">Достижения ФСП</h2>
                  <img src="/brand/fsp-star-dark.svg" alt="" aria-hidden="true" class="fsp-only-dark" style="width: 28px; height: 28px;"><img src="/brand/fsp-star-light.svg" alt="" aria-hidden="true" class="fsp-only-light" style="width: 28px; height: 28px;">
                </div>
                <div style="display: flex; flex-direction: column; gap: 16px; margin-top: 16px;">
                  <div v-for="a in profile.fsp_achievements" :key="a.id" style="display: flex; flex-direction: column; gap: 6px; padding-bottom: 16px; box-shadow: inset 0 -1px 0 var(--line);">
                    <div style="display: flex; justify-content: space-between; gap: 8px; align-items: center;">
                      <FspDisciplineBadge :discipline="a.discipline" />
                      <span class="fsp-display" style="font-size: 16px;">{{ a.place ? a.place + ' место' : 'Участие' }}</span>
                    </div>
                    <div class="u-strong">{{ a.event }}</div>
                    <div v-if="a.year" class="u-small">{{ a.year }}</div>
                  </div>
                </div>
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
