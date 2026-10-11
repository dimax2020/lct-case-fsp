<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'

type Spec = components['schemas']['Specialization']
type Grade = components['schemas']['Grade']
type Attempt = components['schemas']['AttemptView']
type Task = components['schemas']['TaskPublic']
type Run = components['schemas']['RunOut']

useHead({ title: 'Опрос и тест на грейд — Карьера ФСП' })
const cabinetUser = useCabinetUser('Кандидат')

const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => {
  const specs = await read(api.GET('/api/v1/taxonomy/specializations'))
  const id = rememberedAttempt()
  let attempt: Attempt | null = null
  if (id) {
    try {
      attempt = await read(api.GET('/api/v1/assessment/attempts/{id}', { params: { path: { id } } }))
    } catch {
      attempt = null
    }
  }
  return { specs, attempt }
})

const spec = ref<Spec | ''>('')
const grade = ref<Grade | ''>('')
const attempt = ref<Attempt | null>(null)
const seen = ref<Task[]>([])
const reviewId = ref('')
const code = ref('')
const language = ref('python')
const picked = ref('')
const run = ref<Run | null>(null)
const busy = ref(false)
const seconds = ref(0)
let timer: ReturnType<typeof setInterval> | undefined

watch(screen.data, (bundle) => {
  if (!bundle) return
  if (bundle.attempt) applyAttempt(bundle.attempt)
}, { immediate: true })

const step = computed(() => {
  if (attempt.value?.result || attempt.value?.finished_at) return 4
  if (attempt.value) return 3
  if (grade.value) return 2
  return 1
})
const current = computed(() => {
  if (reviewId.value) return seen.value.find(t => t.id === reviewId.value) ?? attempt.value?.task ?? null
  return attempt.value?.task ?? null
})
const clock = computed(() => `${String(Math.floor(seconds.value / 60)).padStart(2, '0')}:${String(seconds.value % 60).padStart(2, '0')}`)
const cells = computed(() => {
  const total = attempt.value?.progress.total ?? 12
  const currentIndex = attempt.value?.progress.current ?? 1
  return Array.from({ length: total }, (_, i) => (i + 1 < currentIndex ? 'var(--success)' : i + 1 === currentIndex && !attempt.value?.result ? 'var(--warning)' : 'var(--line-strong)'))
})

function cacheKey(id: string) {
  return `fsp-attempt-seen:${id}`
}
function rememberSeen(id: string) {
  if (!import.meta.client) return
  sessionStorage.setItem(cacheKey(id), JSON.stringify(seen.value))
}
function restoreSeen(id: string) {
  if (!import.meta.client) return
  const raw = sessionStorage.getItem(cacheKey(id))
  if (!raw) return
  try { seen.value = JSON.parse(raw) as Task[] } catch { seen.value = [] }
}
function applyAttempt(next: Attempt) {
  attempt.value = next
  rememberAttempt(next.id)
  restoreSeen(next.id)
  seconds.value = next.remaining_seconds
  if (next.task && !seen.value.some(t => t.id === next.task?.id)) seen.value.push(next.task)
  rememberSeen(next.id)
  if (!reviewId.value && next.task) {
    language.value = next.task.languages?.[0] || 'python'
    code.value = ''
    picked.value = ''
    run.value = null
  }
}

function startClock() {
  clearInterval(timer)
  timer = setInterval(() => { if (seconds.value > 0) seconds.value -= 1 }, 1000)
}
onMounted(startClock)
onBeforeUnmount(() => clearInterval(timer))

async function start() {
  if (!spec.value || !grade.value) { show('Выберите специализацию и грейд'); return }
  busy.value = true
  try {
    const next = await read(api.POST('/api/v1/assessment/attempts', { body: { specialization: spec.value, declared_grade: grade.value } }))
    seen.value = []
    applyAttempt(next)
    show('Тест начат — ответы сохраняются после каждого задания')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось начать тест')
  } finally {
    busy.value = false
  }
}

async function sendAnswer(skip: boolean) {
  const task = current.value
  if (!attempt.value || !task) return
  if (!skip && task.kind === 'mcq' && !picked.value) { show('Выберите вариант ответа'); return }
  if (!skip && task.kind === 'code' && code.value.trim().length < 1) { show('Напишите решение'); return }
  busy.value = true
  try {
    const next = await read(api.POST('/api/v1/assessment/attempts/{id}/answers', {
      params: { path: { id: attempt.value.id } },
      body: {
        task_id: task.id,
        skip,
        answer: task.kind === 'mcq' ? picked.value || null : null,
        code: task.kind === 'code' ? code.value : null,
        language: task.kind === 'code' ? language.value : null,
      },
    }))
    reviewId.value = ''
    applyAttempt(next)
    if (task.kind === 'code' && !skip) {
      run.value = await read(api.POST('/api/v1/assessment/run', { body: { task_id: task.id, code: code.value, language: language.value } }))
    }
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось сохранить ответ')
  } finally {
    busy.value = false
  }
}

async function runCode() {
  const task = current.value
  if (!task || task.kind !== 'code') return
  if (!code.value.trim()) { show('Напишите решение'); return }
  busy.value = true
  try {
    run.value = await read(api.POST('/api/v1/assessment/run', { body: { task_id: task.id, code: code.value, language: language.value } }))
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось запустить код')
  } finally {
    busy.value = false
  }
}

async function finish() {
  if (!attempt.value) return
  busy.value = true
  try {
    const result = await read(api.POST('/api/v1/assessment/attempts/{id}/finish', { params: { path: { id: attempt.value.id } } }))
    const next = await read(api.GET('/api/v1/assessment/attempts/{id}', { params: { path: { id: attempt.value.id } } }))
    next.result = result
    applyAttempt(next)
    show('Тест завершён')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось завершить тест')
  } finally {
    busy.value = false
  }
}

function openSeen(task: Task) {
  reviewId.value = task.id
  language.value = task.languages?.[0] || 'python'
  code.value = ''
  picked.value = ''
  run.value = null
}

const sample = computed(() => current.value?.tests_public?.[0] ?? null)
const optStyle = (on: boolean) => on
  ? '--cut: var(--cut-s); padding: 14px 16px; display: flex; gap: 12px; align-items: center; cursor: pointer;'
  : '--cut: var(--cut-s); --fill: var(--bg); --edge: var(--line-strong); --bw: 1px; padding: 14px 16px; display: flex; gap: 12px; align-items: center; cursor: pointer;'
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Карьера" :user="cabinetUser" :links="candidateLinks" />
    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px;">
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <nav aria-label="Шаги онбординга" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 8px; margin-bottom: 40px;">
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step > 1 ? 'var(--success)' : 'var(--warning)') }"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Шаг 1</div><div style="font-weight: 600; margin-top: 4px;">Специализация</div></div>
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step > 2 ? 'var(--success)' : step === 2 ? 'var(--warning)' : 'var(--line-strong)') }"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Шаг 2</div><div style="font-weight: 600; margin-top: 4px;">Предполагаемый грейд</div></div>
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step > 3 ? 'var(--success)' : step === 3 ? 'var(--warning)' : 'var(--line-strong)') }"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Шаг 3</div><div style="font-weight: 600; margin-top: 4px;">Тест на грейд</div></div>
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step === 4 ? 'var(--success)' : 'var(--line-strong)') }"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Шаг 4</div><div style="font-weight: 600; margin-top: 4px;">Категория</div></div>
        </nav>

        <section v-if="step < 3" style="display: flex; flex-direction: column; gap: 20px; max-width: 760px;">
          <h1 class="fsp-display" style="font-size: 36px; line-height: 40px;">Опрос</h1>
          <p style="margin: 0; color: var(--text-muted);">Специализация и предполагаемый грейд задают набор из 12 заданий на 40 минут.</p>
          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Специализация</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="s in screen.data.value?.specs ?? []" :key="s.id" :selected="spec === s.id" locked @click="spec = s.id as Spec">{{ s.name }}</FspChip>
            </div>
          </div>
          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Грейд</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="g in GRADES" :key="g" :selected="grade === g" locked @click="grade = g">{{ GRADE_LABEL[g] }}</FspChip>
            </div>
          </div>
          <FspButton icon-right="arrow-right" :disabled="busy" @click="start">Начать тест</FspButton>
        </section>

        <section v-else-if="step === 4 && attempt?.result" style="display: flex; flex-direction: column; gap: 20px; max-width: 760px;">
          <h1 class="fsp-display" style="font-size: 36px; line-height: 40px;">{{ categoryLabel(attempt.specialization, attempt.result.grade) }}</h1>
          <FspPlate :dots="6">
            <div class="fsp-display" style="font-size: 48px; line-height: 52px;">{{ attempt.result.score }}</div>
            <div style="color: var(--on-plate-muted);">баллов из 100<template v-if="attempt.result.ready_for_next"> · готов к следующему</template></div>
            <div style="margin-top: 12px;">Место {{ attempt.result.rank ?? '—' }} из {{ attempt.result.category_size ?? '—' }}</div>
          </FspPlate>
          <div v-for="s in attempt.result.skill_scores" :key="s.skill_id" style="display: grid; grid-template-columns: 160px 1fr 48px; gap: 16px; align-items: center;">
            <span>{{ skillLabel(s.skill_id) }}</span>
            <div style="height: 8px; background: var(--surface-hover);"><div :style="{ width: Math.min(100, s.score) + '%', height: '8px', background: scoreColor(s.score) }" /></div>
            <b>{{ s.score }}</b>
          </div>
          <FspButton href="/candidate/profile">К профилю</FspButton>
        </section>

        <div v-else style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
          <section style="flex: 999 1 600px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
            <template v-if="current">
              <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 12px;">
                <span style="font-size: 14px; color: var(--text-muted);">Задание</span>
                <span class="fsp-display" style="font-size: 20px; line-height: 24px;">{{ attempt?.progress.current }} / {{ attempt?.progress.total }}</span>
                <FspTag>{{ current.kind === 'code' ? 'Код' : 'Выбор ответа' }}</FspTag>
                <FspTag>Сложность {{ current.difficulty }} из 5</FspTag>
                <span style="margin-left: auto; display: inline-flex; align-items: center; gap: 8px; font-weight: 600;"><FspIcon name="clock" />{{ clock }}</span>
              </div>
              <p style="margin: 0; font-size: 16px; line-height: 24px;">{{ current.body }}</p>
              <div v-if="current.kind === 'code'" style="display: flex; flex-direction: column; gap: 12px;">
                <div style="display: flex; gap: 8px;">
                  <FspChip v-for="lang in (current.languages?.length ? current.languages : ['python', 'go'])" :key="lang" :selected="language === lang" locked @click="language = lang">{{ lang === 'go' ? 'Go' : 'Python' }}</FspChip>
                </div>
                <CodeEditor :key="current.id + language" v-model="code" :language="language" />
                <div v-if="sample" style="font-size: 13px; color: var(--text-muted);">
                  Открытый пример: stdin «{{ sample.stdin.trim() }}» → {{ sample.expected.trim() }}
                </div>
                <div v-if="run" class="fsp-cut" style="--cut: var(--cut-s); --fill: var(--surface); --edge: var(--line-card); --bw: 1px; padding: 16px;">
                  <b>{{ VERDICT_LABEL[run.verdict] || run.verdict }}</b>
                  <div style="font-size: 14px; color: var(--text-muted); margin-top: 4px;">Тестов пройдено: {{ run.passed }} из {{ run.total }}</div>
                  <pre v-if="run.stdout || run.stderr" style="margin: 8px 0 0; white-space: pre-wrap; font: 13px/18px ui-monospace, monospace;">{{ run.stdout }}{{ run.stderr }}</pre>
                </div>
              </div>
              <fieldset v-else style="border: 0; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px;">
                <legend style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">Выберите ответ</legend>
                <label v-for="o in current.options ?? []" :key="o.id" :class="['fsp-cut', picked === o.id && 'fsp-active']" :style="optStyle(picked === o.id)">
                  <input v-model="picked" type="radio" :value="o.id" style="accent-color: var(--primary); width: 18px; height: 18px; margin: 0;">{{ o.text }}
                </label>
              </fieldset>
              <div style="display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between; padding-top: 16px; box-shadow: inset 0 1px 0 var(--line);">
                <FspButton variant="ghost" :disabled="busy" @click="sendAnswer(true)">Пропустить</FspButton>
                <div style="display: flex; gap: 8px;">
                  <FspButton v-if="current.kind === 'code'" variant="outline" :disabled="busy" @click="runCode">Запустить</FspButton>
                  <FspButton :disabled="busy" @click="sendAnswer(false)">{{ current.kind === 'code' ? 'Отправить' : 'Ответить' }}</FspButton>
                </div>
              </div>
            </template>
            <div v-else style="display: flex; flex-direction: column; gap: 12px;">
              <p style="margin: 0;">Все показанные задания сохранены. Можно вернуться к пропущенным или завершить тест.</p>
              <FspButton :disabled="busy" @click="finish">Завершить тест</FspButton>
            </div>
            <div v-if="seen.length" style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspButton v-for="(t, i) in seen" :key="t.id" size="sm" variant="ghost" @click="openSeen(t)">{{ i + 1 }}</FspButton>
            </div>
          </section>
          <aside style="flex: 1 1 320px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
            <FspPlate :dots="6">
              <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Вы проходите тест на</div>
              <div class="fsp-display" style="font-size: 26px; line-height: 30px; margin: 10px 0 6px;">{{ categoryLabel(attempt?.specialization, attempt?.declared_grade) }}</div>
              <div style="font-size: 14px; color: var(--on-plate-muted);">Отвечено {{ attempt?.progress.answered ?? 0 }}, пропущено {{ attempt?.progress.skipped ?? 0 }}</div>
            </FspPlate>
            <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line);">
              <div style="display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 12px;"><span style="color: var(--text-muted);">Прогресс</span><b>{{ (attempt?.progress.answered ?? 0) + (attempt?.progress.skipped ?? 0) }} из {{ attempt?.progress.total ?? 12 }}</b></div>
              <div style="display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 4px;">
                <span v-for="(c, i) in cells" :key="i" :style="{ height: '8px', background: c }" />
              </div>
              <p style="margin: 16px 0 0; font-size: 13px; line-height: 18px; color: var(--text-muted);">Перезагрузка не сбрасывает прогресс: ответы уже на сервере.</p>
              <FspButton variant="ghost" size="sm" href="/candidate/profile" style="margin-top: 12px;">Прервать тест</FspButton>
            </div>
          </aside>
        </div>
      </ScreenState>
    </main>
  </div>
</template>
