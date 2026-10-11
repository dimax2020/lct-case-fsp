<script setup lang="ts">
import type { components } from '~/api/schema'
import type { CatTask, CatView, Eligibility } from '~/utils/cat'
import { CAT_DECISION_LABEL, CAT_FORMAT_LABEL, catFormat, clock } from '~/utils/cat'
import { read } from '~/utils/read'
import { apiFetch } from '~/utils/raw'

type Spec = components['schemas']['Specialization']
type Grade = components['schemas']['Grade']

const OPEN_SPECS = new Set(['backend', 'frontend', 'devops', 'data_ml'])

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
const attempt = ref<CatView | null>(null)
const eligibility = ref<Eligibility | null>(null)
const busy = ref(false)
const picked = ref('')
const pickedMany = ref<string[]>([])
const written = ref('')
const code = ref('')
const language = ref('python')
const remaining = ref(0)
let tick: ReturnType<typeof setInterval> | undefined

watch(screen.data, (bundle) => {
  if (!bundle) return
  industries.value = [...(bundle.profile.liked_domains ?? [])]
  if (bundle.profile.specialization && !spec.value && OPEN_SPECS.has(bundle.profile.specialization)) {
    spec.value = bundle.profile.specialization
  }
}, { immediate: true })

const task = computed(() => attempt.value?.task ?? null)
const result = computed(() => attempt.value?.result ?? null)
const format = computed(() => catFormat(task.value))
const step = computed(() => {
  if (result.value) return 4
  if (attempt.value && !result.value) return 3
  if (!industries.value.length) return 1
  return 2
})

function applyAttempt(next: CatView) {
  attempt.value = next
  rememberAttempt(next.id)
  picked.value = ''
  pickedMany.value = []
  written.value = ''
  code.value = ''
  language.value = next.task?.languages?.[0] || 'python'
  remaining.value = next.remaining_seconds
}

function toggleMany(id: string) {
  pickedMany.value = pickedMany.value.includes(id)
    ? pickedMany.value.filter(item => item !== id)
    : [...pickedMany.value, id]
}

function startClock() {
  clearInterval(tick)
  tick = setInterval(() => {
    remaining.value = Math.max(0, remaining.value - 1)
  }, 1000)
}

async function loadEligibility() {
  try {
    eligibility.value = await apiFetch<Eligibility>('/api/v1/assessment/eligibility')
  } catch {
    eligibility.value = null
  }
}

async function resume() {
  if (!import.meta.client) return
  await loadEligibility()
  const id = rememberedAttempt() || eligibility.value?.active_attempt_id
  if (!id) return
  try {
    applyAttempt(await apiFetch<CatView>(`/api/v1/assessment/attempts/${id}`))
    if (!attempt.value?.finished_at) startClock()
  } catch {
    sessionStorage.removeItem('fsp-attempt-id')
  }
}

onMounted(resume)
onBeforeUnmount(() => clearInterval(tick))

function pickSpec(id: string) {
  if (!OPEN_SPECS.has(id)) return
  spec.value = id as Spec
}

function payload() {
  const current = task.value
  if (!current) return null
  if (format.value === 'MCQ') return { task_id: current.id, answer: picked.value }
  if (format.value === 'MSQ') return { task_id: current.id, answer: pickedMany.value.join(',') }
  if (format.value === 'CODE') return { task_id: current.id, code: code.value, language: language.value }
  return { task_id: current.id, answer: written.value }
}

async function start() {
  if (!industries.value.length) {
    show('Выберите хотя бы одну отрасль')
    return
  }
  if (!spec.value || !OPEN_SPECS.has(spec.value)) {
    show('Выберите специализацию')
    return
  }
  if (!grade.value) {
    show('Выберите грейд')
    return
  }
  busy.value = true
  try {
    await read(api.PUT('/api/v1/candidates/me', { body: { liked_domains: industries.value, specialization: spec.value } }))
    const next = await apiFetch<CatView>('/api/v1/assessment/attempts', {
      method: 'POST',
      body: { specialization: spec.value, declared_grade: grade.value },
    })
    applyAttempt(next)
    startClock()
    show('Адаптивный тест начат. Обычно 8–20 заданий, 40–90 минут.')
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Не удалось начать тест'
    show(message)
    await loadEligibility()
    if (eligibility.value?.active_attempt_id) await resume()
  } finally {
    busy.value = false
  }
}

async function send(skip = false) {
  if (!attempt.value || !task.value) return
  const body = skip ? { task_id: task.value.id, skip: true } : payload()
  if (!skip && format.value === 'MCQ' && !picked.value) {
    show('Выберите вариант')
    return
  }
  if (!skip && format.value === 'MSQ' && !pickedMany.value.length) {
    show('Отметьте хотя бы один вариант')
    return
  }
  if (!skip && format.value === 'CODE' && !code.value.trim()) {
    show('Напишите решение')
    return
  }
  if (!skip && !['MCQ', 'MSQ', 'CODE'].includes(format.value) && written.value.trim().length < 2) {
    show('Напишите ответ')
    return
  }
  busy.value = true
  try {
    const next = await apiFetch<CatView>(`/api/v1/assessment/attempts/${attempt.value.id}/answers`, {
      method: 'POST',
      body,
    })
    applyAttempt(next)
    if (next.result) {
      clearInterval(tick)
      show('Тест завершён')
    } else {
      startClock()
    }
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось сохранить ответ')
  } finally {
    busy.value = false
  }
}

async function runCode() {
  if (!task.value || !code.value.trim()) return
  busy.value = true
  try {
    const out = await apiFetch<{ verdict: string; passed: number; total: number; stdout?: string; stderr?: string }>('/api/v1/assessment/run', {
      method: 'POST',
      body: { task_id: task.value.id, code: code.value, language: language.value },
    })
    show(out.verdict === 'PENDING' ? 'Песочница сейчас выключена, ответ всё равно можно отправить' : `${out.verdict}: ${out.passed}/${out.total}`)
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось запустить код')
  } finally {
    busy.value = false
  }
}

async function finishNow() {
  if (!attempt.value) return
  busy.value = true
  try {
    await apiFetch(`/api/v1/assessment/attempts/${attempt.value.id}/finish`, { method: 'POST' })
    applyAttempt(await apiFetch<CatView>(`/api/v1/assessment/attempts/${attempt.value.id}`))
    clearInterval(tick)
    show('Тест завершён')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось завершить тест')
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
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step > 3 ? 'var(--success)' : step === 3 ? 'var(--warning)' : 'var(--line-strong)') }"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Шаг 3</div><div style="font-weight: 600; margin-top: 4px;">Адаптивный тест</div></div>
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step === 4 ? 'var(--success)' : 'var(--line-strong)') }"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Шаг 4</div><div style="font-weight: 600; margin-top: 4px;">Результат</div></div>
        </nav>

        <section v-if="step < 3" style="display: flex; flex-direction: column; gap: 20px; max-width: 760px;">
          <h1 class="fsp-display" style="font-size: 36px; line-height: 40px;">Опрос</h1>
          <p style="margin: 0; color: var(--text-muted); line-height: 24px;">Сначала отрасль, затем специализация и самооценка грейда. Дальше адаптивный тест: теория, код, отладка, ревью и кейс. Обычно 8–20 заданий, 40–90 минут. Data/ML пока идёт по банку QA.</p>
          <p v-if="eligibility && !eligibility.can_start && eligibility.message" style="margin: 0; color: var(--text-muted);">{{ eligibility.message }}<template v-if="eligibility.retry_at"> С {{ new Date(eligibility.retry_at).toLocaleDateString('ru-RU') }}.</template></p>
          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Отрасль · до трёх</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="d in screen.data.value?.domains ?? []" :key="d.id" :selected="industries.includes(d.id)" locked @click="industries.includes(d.id) ? industries = industries.filter(x => x !== d.id) : industries.length >= 3 ? show('Можно выбрать до трёх отраслей') : industries = [...industries, d.id]">{{ d.name }}</FspChip>
            </div>
          </div>
          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Специализация</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="s in screen.data.value?.specs ?? []" :key="s.id" :selected="spec === s.id" locked @click="pickSpec(s.id)">{{ s.name }}</FspChip>
            </div>
          </div>
          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Грейд</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="g in GRADES" :key="g" :selected="grade === g" locked @click="grade = g">{{ GRADE_LABEL[g] }}</FspChip>
            </div>
          </div>
          <FspButton icon-right="arrow-right" :disabled="busy || (eligibility?.can_start === false && !eligibility.active_attempt_id)" @click="start">Начать тест</FspButton>
        </section>

        <section v-else-if="step === 4 && result" style="display: flex; flex-direction: column; gap: 28px; max-width: 760px;">
          <h1 class="fsp-display" style="font-size: 36px; line-height: 40px; margin: 0;">{{ categoryLabel(attempt?.specialization, result.grade) }}</h1>
          <FspPlate :dots="6">
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">{{ CAT_DECISION_LABEL[result.decision || ''] || 'Решение' }}</div>
            <p style="margin: 10px 0 0; font-size: 18px; line-height: 28px;">{{ result.message || 'Тест завершён.' }}</p>
            <div style="margin-top: 16px; color: var(--on-plate-muted);">
              Оценка θ {{ result.theta?.toFixed?.(2) ?? '—' }} · SE {{ result.se?.toFixed?.(2) ?? '—' }}
              · процентиль {{ result.percentile ?? '—' }}
              · измеренный грейд {{ result.measured_grade ? GRADE_LABEL[result.measured_grade] : '—' }}
            </div>
          </FspPlate>
          <div style="display: flex; flex-wrap: wrap; gap: 8px;">
            <FspButton href="/candidate/psych" icon-right="arrow-right">Пройти тест рабочего стиля</FspButton>
            <FspButton variant="outline" href="/candidate/grade">К категории и грейду</FspButton>
          </div>
        </section>

        <div v-else-if="attempt && task" style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
          <section style="flex: 999 1 640px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
            <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 12px;">
              <span style="font-size: 14px; color: var(--text-muted);">Задание</span>
              <span class="fsp-display" style="font-size: 20px; line-height: 24px;">{{ attempt.progress.current }} / {{ attempt.progress.total }}</span>
              <FspTag>{{ CAT_FORMAT_LABEL[format] || format }}</FspTag>
              <FspTag v-if="task.time_minutes">{{ task.time_minutes }} мин</FspTag>
              <span style="margin-left: auto; font-variant-numeric: tabular-nums;">{{ clock(remaining) }}</span>
            </div>
            <h1 class="fsp-display" style="font-size: 32px; line-height: 36px; margin: 0;">{{ task.title || 'Задание' }}</h1>
            <pre style="margin: 0; white-space: pre-wrap; font: 16px/24px var(--font-sans);">{{ task.body }}</pre>

            <div v-if="format === 'MCQ'" style="display: flex; flex-direction: column; gap: 8px;">
              <button v-for="opt in task.options ?? []" :key="opt.id" type="button" :class="['fsp-cut', picked === opt.id && 'fsp-active']" :style="optStyle(picked === opt.id)" @click="picked = opt.id">{{ opt.text }}</button>
            </div>
            <div v-else-if="format === 'MSQ'" style="display: flex; flex-direction: column; gap: 8px;">
              <button v-for="opt in task.options ?? []" :key="opt.id" type="button" :class="['fsp-cut', pickedMany.includes(opt.id) && 'fsp-active']" :style="optStyle(pickedMany.includes(opt.id))" @click="toggleMany(opt.id)">{{ opt.text }}</button>
            </div>
            <div v-else-if="format === 'CODE'" style="display: flex; flex-direction: column; gap: 12px;">
              <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                <FspChip v-for="lang in (task.languages.length ? task.languages : ['python'])" :key="lang" :selected="language === lang" locked @click="language = lang">{{ lang }}</FspChip>
              </div>
              <textarea v-model="code" aria-label="Код решения" spellcheck="false" style="box-sizing: border-box; width: 100%; min-height: 220px; padding: 16px; resize: vertical; border: 1px solid var(--line-strong); background: var(--surface); color: var(--text); font: 14px/22px ui-monospace, SFMono-Regular, Menlo, monospace;" />
              <FspButton variant="ghost" :disabled="busy" @click="runCode">Проверить в песочнице</FspButton>
            </div>
            <textarea v-else v-model="written" aria-label="Ответ" style="box-sizing: border-box; width: 100%; min-height: 180px; padding: 16px; resize: vertical; border: 1px solid var(--line-strong); background: var(--surface); color: var(--text); font: 16px/24px var(--font-sans);" />

            <div style="display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px;">
              <FspButton variant="ghost" :disabled="busy" @click="send(true)">Пропустить</FspButton>
              <FspButton :disabled="busy" @click="send(false)">Ответить</FspButton>
            </div>
          </section>
          <aside style="flex: 1 1 320px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
            <FspPlate :dots="6">
              <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Вы заявили</div>
              <div class="fsp-display" style="font-size: 26px; line-height: 30px; margin: 10px 0 6px;">{{ categoryLabel(attempt.specialization, attempt.declared_grade) }}</div>
              <div style="font-size: 14px; line-height: 20px; color: var(--on-plate-muted);">CAT подбирает следующее задание по θ. Оценка по ходу не показывается. Остановка при SE &lt; 0.30, минимум 8, максимум 20.</div>
            </FspPlate>
            <div v-if="task.tags?.length" style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspTag v-for="tag in task.tags" :key="tag">{{ tag }}</FspTag>
            </div>
            <FspButton variant="ghost" size="sm" :disabled="busy" @click="finishNow">Завершить досрочно</FspButton>
            <FspButton variant="ghost" size="sm" href="/candidate/grade">Прервать тест</FspButton>
          </aside>
        </div>
      </ScreenState>
    </main>
  </div>
</template>
