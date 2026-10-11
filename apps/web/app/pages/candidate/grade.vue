<script setup lang="ts">
import { ApiError, read } from '~/utils/read'
import { apiFetch } from '~/utils/raw'
import type { PsychState } from '~/utils/psych'
useHead({ title: 'Категория и грейд — Карьера ФСП' })
const cabinetUser = useCabinetUser('Кандидат')
const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => read(api.GET('/api/v1/candidates/me/grade')))
const grade = computed(() => screen.data.value)
const ladder = GRADES
const currentGrade = computed(() => grade.value?.grade ?? null)
function passed(g: typeof ladder[number]) {
  if (!currentGrade.value) return false
  return ladder.indexOf(g) < ladder.indexOf(currentGrade.value)
}
const retakeError = ref('')
const retaking = ref(false)
async function retake(direction: 'down' | 'up') {
  if (retaking.value) return
  retakeError.value = ''
  retaking.value = true
  try {
    const created = await apiFetch<{ id?: string; attempt_id?: string }>('/api/v1/assessment/retake', { method: 'POST', body: { direction } })
    const attemptId = created?.id || created?.attempt_id
    if (attemptId) rememberAttempt(attemptId)
    show(direction === 'down' ? 'Назначен тест на грейд ниже' : 'Назначен тест на грейд выше')
    if (attemptId) {
      await navigateTo('/candidate/onboarding')
      return
    }
    await screen.load()
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) retakeError.value = e.message
    else show(e instanceof Error ? e.message : 'Не удалось назначить тест')
  } finally {
    retaking.value = false
  }
}
const psych = ref<PsychState | null>(null)
const roadmap = ref<{
  finished?: boolean
  locked_until?: string | null
  message?: string | null
  open?: boolean
  nodes?: { id: string; label: string; title: string; status: 'held' | 'review' | 'current' | 'ahead' | 'aside'; order: number | null }[]
  review?: { label: string; title: string; items: string[] }[]
} | null>(null)
onMounted(async () => {
  const [latest, style] = await Promise.all([
    apiFetch('/api/v1/assessment/roadmap/latest').catch(() => null),
    apiFetch<PsychState>('/api/v1/psych/me').catch(() => null),
  ])
  roadmap.value = latest
  psych.value = style
})
const nextAt = computed(() => {
  const locked = roadmap.value?.locked_until
  if (locked) return new Date(locked).toLocaleDateString('ru-RU')
  const last = grade.value?.history?.[0]?.finished_at
  if (!last) return ''
  const d = new Date(last)
  d.setMonth(d.getMonth() + 3)
  return d.toLocaleDateString('ru-RU')
})
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Карьера" :user="cabinetUser" :links="candidateLinks" />
    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px; display: flex; flex-direction: column; gap: 32px;">
      <div>
        <h1 class="fsp-display" style="font-size: 40px; line-height: 44px; margin-bottom: 8px;">Категория и грейд</h1>
        <p style="margin: 0; font-size: 16px; color: var(--text-muted);">Категорию видят работодатели. Она складывается из специализации и грейда, подтверждённого тестом. Тест рабочего стиля дополняет профиль и на категорию не влияет.</p>
      </div>
      <section class="psy-entry fsp-cut fsp-card">
        <div class="fsp-stack-12" style="flex: 999 1 420px; min-width: 0;">
          <div class="fsp-eyebrow">Тест рабочего стиля · около 20 минут</div>
          <div class="u-lead">
            <template v-if="psych?.result">{{ psych.result.disc_profile.label }} · пройден {{ shortDate(psych.finished_at) }}</template>
            <template v-else-if="psych?.attempt">Тест начат — ответы сохранены, можно продолжить</template>
            <template v-else>DISC, лидерство, командность, стрессоустойчивость и трудоспособность</template>
          </div>
          <p class="u-note" style="margin: 0;">Три части: стиль поведения, утверждения о работе и рабочие ситуации. Правильных ответов нет.</p>
        </div>
        <FspButton :variant="psych?.result ? 'outline' : 'primary'" href="/candidate/psych" icon-right="arrow-right">
          {{ psych?.result ? 'Открыть результат' : psych?.attempt ? 'Продолжить тест' : 'Пройти тест' }}
        </FspButton>
      </section>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <p v-if="!grade?.grade" style="margin: 0; color: var(--text-muted);">Тест ещё не пройден. <NuxtLink to="/candidate/onboarding">Начать</NuxtLink></p>
        <template v-else>
          <section style="display: flex; flex-wrap: wrap; gap: 16px;">
            <div style="flex: 1 1 420px; min-width: 0;">
              <FspPlate :dots="6">
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr)); gap: 20px;">
                  <div><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Специализация</div><div style="font-size: 18px; font-weight: 600; margin-top: 6px;">{{ categoryLabel(grade.specialization, null) }}</div></div>
                  <div><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Грейд</div><div class="fsp-display" style="font-size: 22px; line-height: 26px; margin-top: 6px;">{{ currentGrade ? GRADE_LABEL[currentGrade] : '—' }}</div></div>
                  <div><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Заявлен</div><div style="font-size: 18px; font-weight: 600; margin-top: 6px;">{{ grade.declared_grade ? GRADE_LABEL[grade.declared_grade] : '—' }}</div></div>
                </div>
                <div style="margin-top: 20px; font-size: 14px; color: var(--on-plate-muted);">{{ grade.score ?? '—' }} из 100 · место {{ grade.rank ?? '—' }} из {{ grade.category_size ?? '—' }}<template v-if="grade.ready_for_next"> · готов к следующему</template></div>
              </FspPlate>
            </div>
            <div class="fsp-cut" style="flex: 1 1 360px; min-width: 0; --cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 32px; display: flex; flex-direction: column; gap: 12px;">
              <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Следующая смена грейда</div>
              <div class="fsp-display" style="font-size: 28px; line-height: 32px;">{{ nextAt || 'после теста' }}</div>
              <div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">{{ roadmap?.message || 'Следующая попытка зависит от того, как пройден тест по карте: сильный результат открывает senior раньше, слабый удлиняет паузу.' }}</div>
            </div>
          </section>
          <section v-if="roadmap?.finished && roadmap.nodes?.length" style="padding: 8px 0 0;">
            <FspRoadmapMap :nodes="roadmap.nodes" :review="roadmap.review || []" :specialization="grade.specialization || 'backend'" show-review />
          </section>
          <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 24px;">Лестница грейдов</h2>
            <ol style="list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr)); gap: 8px;">
              <li v-for="g in ladder" :key="g">
                <div v-if="g === currentGrade" class="fsp-cut" style="--cut: var(--cut-s); --fill: var(--accent-mark); color: #ffffff; padding: 16px;">
                  <div style="font-weight: 600;">{{ GRADE_LABEL[g] }}</div>
                  <div style="font-size: 13px; margin-top: 4px;">текущий</div>
                </div>
                <div v-else :style="{ padding: '16px', boxShadow: 'inset 0 3px 0 ' + (passed(g) ? 'var(--success)' : 'var(--line-strong)') }">
                  <div style="font-weight: 600;">{{ GRADE_LABEL[g] }}</div>
                  <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">{{ passed(g) ? 'пройден' : 'позже' }}</div>
                </div>
              </li>
            </ol>
            <div style="display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px;">
              <FspButton href="/candidate/onboarding">Пройти тест</FspButton>
              <FspButton variant="outline" :disabled="retaking" @click="retake('down')">Пройти на грейд ниже</FspButton>
              <FspButton variant="outline" :disabled="retaking" @click="retake('up')">Пройти на грейд выше</FspButton>
            </div>
            <p v-if="retakeError" role="alert" style="margin: 12px 0 0; color: var(--danger);">{{ retakeError }}</p>
          </section>
          <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 20px;">Баллы по навыкам</h2>
            <div v-for="s in grade.skill_scores ?? []" :key="s.skill_id" style="display: grid; grid-template-columns: 180px 1fr 48px; gap: 16px; align-items: center; margin-bottom: 12px;">
              <span>{{ skillLabel(s.skill_id) }}</span>
              <div style="height: 8px; background: var(--surface-hover);"><div :style="{ width: Math.min(100, s.score) + '%', height: '8px', background: scoreColor(s.score) }" /></div>
              <b>{{ s.score }}</b>
            </div>
            <p v-if="!(grade.skill_scores ?? []).length" style="color: var(--text-muted);">Баллов по навыкам пока нет.</p>
          </section>
          <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 20px;">История тестов</h2>
            <p v-if="!(grade.history ?? []).length" style="color: var(--text-muted);">История пуста.</p>
            <table v-else style="width: 100%; border-collapse: collapse; font-size: 15px;">
              <tbody>
                <tr v-for="h in grade.history" :key="h.attempt_id" style="box-shadow: inset 0 1px 0 var(--line);">
                  <td style="padding: 14px 16px 14px 0;">{{ shortDate(h.finished_at) }}</td>
                  <td style="padding: 14px 16px 14px 0;">{{ GRADE_LABEL[h.grade] }}</td>
                  <td style="padding: 14px 0; font-weight: 600;">{{ h.score }} / 100</td>
                </tr>
              </tbody>
            </table>
          </section>
        </template>
      </ScreenState>
    </main>
  </div>
</template>

<style>
.psy-entry { display: flex; flex-wrap: wrap; gap: 16px 32px; align-items: center; justify-content: space-between; }
</style>
