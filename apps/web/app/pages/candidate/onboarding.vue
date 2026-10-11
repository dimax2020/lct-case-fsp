<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'
import { apiFetch } from '~/utils/raw'

type Spec = components['schemas']['Specialization']
type Grade = components['schemas']['Grade']
type Mark = 'yes' | 'no' | 'unknown'

type RoadmapRun = {
  id: string
  specialization: 'backend' | 'frontend'
  declared_grade: Grade
  step: number
  total: number
  phase: 'checks' | 'concrete' | 'done'
  title: string | null
  prompt: string | null
  checks: { id: string; text: string }[]
  saved_checks: Partial<Record<string, Mark>>
  concrete_question: string | null
  nodes: { id: string; label: string; title: string; status: 'held' | 'review' | 'current' | 'ahead' | 'aside'; order: number | null }[]
  review: { label: string; title: string; items: string[] }[]
  result: {
    measured_grade: Grade
    outcome: 'up' | 'down' | 'same'
    cooldown_days: number
    locked_until: string
    message: string
    score: number
  } | null
}

const OPEN_SPECS = new Set(['backend', 'frontend'])
const RUN_KEY = 'fsp-roadmap-run'

useHead({ title: 'Опрос и тест на грейд — Карьера ФСП' })
const cabinetUser = useCabinetUser('Кандидат')
const { show } = useToast()
const api = useApi()
const route = useRoute()
const screen = useScreen(async () => {
  const [specs, domains, profile] = await Promise.all([
    read(api.GET('/api/v1/taxonomy/specializations')),
    read(api.GET('/api/v1/taxonomy/domains')),
    read(api.GET('/api/v1/candidates/me')),
  ])
  return { specs, domains, profile }
})

onMounted(async () => {
  if (route.query.consent !== '1') return
  try {
    const current = await read(api.GET('/api/v1/candidates/me/settings'))
    if (!current.consent_processing) {
      await read(api.PUT('/api/v1/candidates/me/settings', { body: { ...current, consent_processing: true } }))
    }
  } catch {
    // Согласие можно дать и позже в настройках.
  }
})

const spec = ref<Spec | ''>('')
const industries = ref<string[]>([])
const grade = ref<Grade | ''>('')
const run = ref<RoadmapRun | null>(null)
const marks = reactive<Record<string, Mark | ''>>({})
const concrete = ref('')
const busy = ref(false)

watch(screen.data, (bundle) => {
  if (!bundle) return
  industries.value = [...(bundle.profile.liked_domains ?? [])]
  if (bundle.profile.specialization && !spec.value && OPEN_SPECS.has(bundle.profile.specialization)) {
    spec.value = bundle.profile.specialization
  }
}, { immediate: true })

const step = computed(() => {
  if (run.value?.phase === 'done') return 4
  if (run.value) return 3
  if (!industries.value.length) return 1
  if (!spec.value || !grade.value) return 2
  return 2
})

function toggleIndustry(id: string) {
  if (industries.value.includes(id)) {
    industries.value = industries.value.filter(item => item !== id)
    return
  }
  if (industries.value.length >= 3) {
    show('Можно выбрать до трёх отраслей')
    return
  }
  industries.value = [...industries.value, id]
}
function rememberRun(id: string) {
  if (import.meta.client) sessionStorage.setItem(RUN_KEY, id)
}
function applyRun(next: RoadmapRun) {
  run.value = next
  rememberRun(next.id)
  for (const key of Object.keys(marks)) delete marks[key]
  for (const item of next.checks) marks[item.id] = next.saved_checks[item.id] ?? ''
  if (next.phase === 'checks') concrete.value = ''
}
async function resume() {
  if (!import.meta.client) return
  const id = sessionStorage.getItem(RUN_KEY)
  if (!id) return
  try {
    const next = await apiFetch<RoadmapRun>(`/api/v1/assessment/roadmap/runs/${id}`)
    if (next.phase === 'done') run.value = next
    else applyRun(next)
  } catch {
    sessionStorage.removeItem(RUN_KEY)
  }
}
const lockPassed = computed(() => {
  const until = run.value?.result?.locked_until
  return until ? new Date(until).getTime() <= Date.now() : false
})
onMounted(resume)

function pickSpec(id: string) {
  if (!OPEN_SPECS.has(id)) return
  spec.value = id as Spec
}

async function start() {
  if (!industries.value.length) {
    show('Выберите хотя бы одну отрасль')
    return
  }
  if (spec.value !== 'backend' && spec.value !== 'frontend') {
    show('Сейчас тест есть только для backend и frontend')
    return
  }
  if (!grade.value) {
    show('Выберите грейд')
    return
  }
  busy.value = true
  try {
    await read(api.PUT('/api/v1/candidates/me', { body: { liked_domains: industries.value, specialization: spec.value } }))
    applyRun(await apiFetch<RoadmapRun>('/api/v1/assessment/roadmap/runs', {
      method: 'POST',
      body: { specialization: spec.value, declared_grade: grade.value },
    }))
    show('Тест начат. Всю карту проходить не нужно — три темы.')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось начать тест')
  } finally {
    busy.value = false
  }
}

async function sendChecks() {
  if (!run.value) return
  const answers = run.value.checks.map(item => ({ id: item.id, value: marks[item.id] }))
  if (answers.some(item => item.value !== 'yes' && item.value !== 'no' && item.value !== 'unknown')) {
    show('Отметьте каждое утверждение: да, нет или не знаю')
    return
  }
  busy.value = true
  try {
    applyRun(await apiFetch<RoadmapRun>(`/api/v1/assessment/roadmap/runs/${run.value.id}/checks`, {
      method: 'POST',
      body: { answers },
    }))
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось сохранить отметки')
  } finally {
    busy.value = false
  }
}

async function sendConcrete() {
  if (!run.value) return
  if (concrete.value.trim().length < 10) {
    show('Ответ — хотя бы одно предложение')
    return
  }
  busy.value = true
  try {
    const next = await apiFetch<RoadmapRun>(`/api/v1/assessment/roadmap/runs/${run.value.id}/concrete`, {
      method: 'POST',
      body: { answer: concrete.value.trim() },
    })
    applyRun(next)
    if (next.phase === 'done') show('Тест завершён')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось сохранить ответ')
  } finally {
    busy.value = false
  }
}

const optStyle = (on: boolean) => on
  ? '--cut: var(--cut-s); padding: 8px 12px; cursor: pointer;'
  : '--cut: var(--cut-s); --fill: var(--bg); --edge: var(--line-strong); --bw: 1px; padding: 8px 12px; cursor: pointer;'
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Карьера" :user="cabinetUser" :links="candidateLinks" />
    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px;">
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <nav aria-label="Шаги онбординга" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 8px; margin-bottom: 40px;">
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step > 1 ? 'var(--success)' : 'var(--warning)') }"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Шаг 1</div><div style="font-weight: 600; margin-top: 4px;">Специализация</div></div>
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step > 2 ? 'var(--success)' : step === 2 ? 'var(--warning)' : 'var(--line-strong)') }"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Шаг 2</div><div style="font-weight: 600; margin-top: 4px;">Предполагаемый грейд</div></div>
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step > 3 ? 'var(--success)' : step === 3 ? 'var(--warning)' : 'var(--line-strong)') }"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Шаг 3</div><div style="font-weight: 600; margin-top: 4px;">Тест по карте</div></div>
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step === 4 ? 'var(--success)' : 'var(--line-strong)') }"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Шаг 4</div><div style="font-weight: 600; margin-top: 4px;">Результат</div></div>
        </nav>

        <section v-if="step < 3" style="display: flex; flex-direction: column; gap: 20px; max-width: 760px;">
          <h1 class="fsp-display" style="font-size: 36px; line-height: 40px;">Опрос</h1>
          <p style="margin: 0; color: var(--text-muted); line-height: 24px;">Сначала отрасль, затем специализация и грейд. Вопросы — сжатая выборка из <a class="fsp-link" href="https://roadmap.sh/backend" target="_blank" rel="noopener">карты backend</a> и <a class="fsp-link" href="https://roadmap.sh/frontend" target="_blank" rel="noopener">карты frontend</a>. Всю карту проходить не нужно.</p>
          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Отрасль · до трёх</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="d in screen.data.value?.domains ?? []" :key="d.id" :selected="industries.includes(d.id)" locked @click="toggleIndustry(d.id)">{{ d.name }}</FspChip>
            </div>
          </div>
          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Специализация</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="s in screen.data.value?.specs ?? []" :key="s.id" :selected="spec === s.id" :disabled="!OPEN_SPECS.has(s.id)" locked @click="pickSpec(s.id)">{{ s.name }}</FspChip>
            </div>
            <p style="margin: 8px 0 0; font-size: 13px; color: var(--text-muted);">Data/ML и DevOps ещё не входят в этот тест.</p>
          </div>
          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Грейд</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="g in GRADES" :key="g" :selected="grade === g" locked @click="grade = g">{{ GRADE_LABEL[g] }}</FspChip>
            </div>
          </div>
          <FspButton icon-right="arrow-right" :disabled="busy" @click="start">Начать тест</FspButton>
        </section>

        <section v-else-if="step === 4 && run?.result" style="display: flex; flex-direction: column; gap: 28px;">
          <div style="max-width: 760px;">
            <h1 class="fsp-display" style="font-size: 36px; line-height: 40px; margin: 0 0 16px;">{{ categoryLabel(run.specialization, run.result.measured_grade) }}</h1>
            <FspPlate :dots="6">
              <p style="margin: 0; font-size: 18px; line-height: 28px;">{{ run.result.message }}</p>
              <div style="margin-top: 16px; color: var(--on-plate-muted);">Следующая попытка: {{ new Date(run.result.locked_until).toLocaleDateString('ru-RU') }}</div>
            </FspPlate>
          </div>
          <FspRoadmapMap :nodes="run.nodes || []" :review="run.review || []" :specialization="run.specialization" show-review />
          <div style="display: flex; flex-wrap: wrap; gap: 8px;">
            <FspButton href="/candidate/psych" icon-right="arrow-right">Пройти тест рабочего стиля</FspButton>
            <FspButton variant="outline" href="/candidate/grade">К категории и грейду</FspButton>
            <FspButton v-if="lockPassed" variant="ghost" @click="run = null">Пройти снова</FspButton>
          </div>
        </section>

        <div v-else-if="run" style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
          <section style="flex: 999 1 640px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
            <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 12px;">
              <span style="font-size: 14px; color: var(--text-muted);">Тема</span>
              <span class="fsp-display" style="font-size: 20px; line-height: 24px;">{{ run.step }} / {{ run.total }}</span>
              <FspTag>{{ run.phase === 'concrete' ? 'Конкретный вопрос' : 'Да, нет, не знаю' }}</FspTag>
            </div>
            <h1 class="fsp-display" style="font-size: 32px; line-height: 36px; margin: 0;">{{ run.title }}</h1>
            <p style="margin: 0; color: var(--text-muted); line-height: 24px;">{{ run.prompt }}</p>

            <div v-if="run.phase === 'checks'" style="display: flex; flex-direction: column; gap: 16px;">
              <div v-for="item in run.checks" :key="item.id" style="padding-top: 16px; box-shadow: inset 0 1px 0 var(--line);">
                <p style="margin: 0 0 10px; font-size: 16px; line-height: 24px;">{{ item.text }}</p>
                <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                  <button type="button" :class="['fsp-cut', marks[item.id] === 'yes' && 'fsp-active']" :style="optStyle(marks[item.id] === 'yes')" @click="marks[item.id] = 'yes'">Да</button>
                  <button type="button" :class="['fsp-cut', marks[item.id] === 'no' && 'fsp-active']" :style="optStyle(marks[item.id] === 'no')" @click="marks[item.id] = 'no'">Нет</button>
                  <button type="button" :class="['fsp-cut', marks[item.id] === 'unknown' && 'fsp-active']" :style="optStyle(marks[item.id] === 'unknown')" @click="marks[item.id] = 'unknown'">Не знаю</button>
                </div>
              </div>
              <div style="display: flex; justify-content: flex-end; padding-top: 8px;">
                <FspButton :disabled="busy" @click="sendChecks">Дальше к вопросу</FspButton>
              </div>
            </div>

            <div v-else style="display: flex; flex-direction: column; gap: 16px;">
              <p style="margin: 0; font-size: 18px; line-height: 28px;">{{ run.concrete_question }}</p>
              <textarea v-model="concrete" aria-label="Ответ на конкретный вопрос" style="box-sizing: border-box; width: 100%; min-height: 160px; padding: 16px; resize: vertical; border: 1px solid var(--line-strong); background: var(--surface); color: var(--text); font: 16px/24px var(--font-sans);" />
              <div style="display: flex; justify-content: flex-end;">
                <FspButton :disabled="busy" @click="sendConcrete">{{ run.step === run.total ? 'Завершить тест' : 'Следующая тема' }}</FspButton>
              </div>
            </div>
          </section>
          <aside style="flex: 1 1 320px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
            <FspPlate :dots="6">
              <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Вы заявили</div>
              <div class="fsp-display" style="font-size: 26px; line-height: 30px; margin: 10px 0 6px;">{{ categoryLabel(run.specialization, run.declared_grade) }}</div>
              <div style="font-size: 14px; line-height: 20px; color: var(--on-plate-muted);">Тема на карте подсвечена. Оценка по ходу не показывается.</div>
            </FspPlate>
            <FspRoadmapMap :nodes="run.nodes || []" :specialization="run.specialization" />
            <FspButton variant="ghost" size="sm" href="/candidate/profile">Прервать тест</FspButton>
          </aside>
        </div>
      </ScreenState>
    </main>
  </div>
</template>
