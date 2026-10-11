<script setup lang="ts">
import { apiFetch } from '~/utils/raw'
import { emptyAnswers, minutesSince, type Letter, type PsychAnswers, type PsychAttempt, type PsychState, type PsychTest } from '~/utils/psych'

useHead({ title: 'Тест рабочего стиля — Карьера ФСП' })
const cabinetUser = useCabinetUser('Кандидат')
const { show } = useToast()

const screen = useScreen(async () => {
  const [test, state] = await Promise.all([
    apiFetch<PsychTest>('/api/v1/psych/test'),
    apiFetch<PsychState>('/api/v1/psych/me'),
  ])
  return { test, state }
})

const test = computed(() => screen.data.value?.test ?? null)
const state = computed(() => screen.data.value?.state ?? null)
const view = ref<'intro' | 'run' | 'result'>('intro')
const part = ref(1)
const attempt = ref<PsychAttempt | null>(null)
const answers = reactive<PsychAnswers>(emptyAnswers())
const consent = ref(false)
const share = ref(false)
const busy = ref(false)
const saveState = ref<'' | 'saving' | 'saved' | 'error'>('')
const skipWarned = ref(false)
const minutes = ref(0)
let saveTimer: ReturnType<typeof setTimeout> | undefined
let clock: ReturnType<typeof setInterval> | undefined

watch(screen.data, (bundle) => {
  if (!bundle) return
  share.value = bundle.state.share_with_employers
  if (bundle.state.attempt) {
    loadAttempt(bundle.state.attempt)
    consent.value = true
  }
  view.value = bundle.state.result && !bundle.state.attempt ? 'result' : 'intro'
}, { immediate: true })

function loadAttempt(next: PsychAttempt) {
  attempt.value = next
  answers.disc = { ...next.answers.disc }
  answers.statements = { ...next.answers.statements }
  answers.cases = { ...next.answers.cases }
  minutes.value = minutesSince(next.started_at)
}

onMounted(() => { clock = setInterval(() => { minutes.value = minutesSince(attempt.value?.started_at) }, 30000) })
onBeforeUnmount(() => { clearInterval(clock); clearTimeout(saveTimer) })

const blocksDone = computed(() => (test.value?.blocks ?? []).filter(b => answers.disc[String(b.id)]?.most && answers.disc[String(b.id)]?.least).length)
const statementsDone = computed(() => Object.keys(answers.statements).length)
const casesDone = computed(() => Object.keys(answers.cases).length)
const missingBlocks = computed(() => (test.value?.blocks ?? []).filter(b => !(answers.disc[String(b.id)]?.most && answers.disc[String(b.id)]?.least)).map(b => b.id))
const missingCases = computed(() => (test.value?.cases ?? []).filter(c => !answers.cases[String(c.id)]).map(c => c.id))
const skippedStatements = computed(() => (test.value?.statements.length ?? 30) - statementsDone.value)
const totalItems = computed(() => (test.value ? test.value.blocks.length + test.value.statements.length + test.value.cases.length : 47))
const percent = computed(() => Math.round(((blocksDone.value + statementsDone.value + casesDone.value) / totalItems.value) * 100))

async function begin() {
  if (!consent.value) { show('Нужно согласие на обработку результатов теста'); return }
  busy.value = true
  try {
    loadAttempt(await apiFetch<PsychAttempt>('/api/v1/psych/attempts', { method: 'POST' }))
    part.value = firstOpenPart()
    view.value = 'run'
    scrollTop()
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось начать тест')
  } finally {
    busy.value = false
  }
}

function firstOpenPart() {
  if (missingBlocks.value.length) return 1
  if (skippedStatements.value > 0) return 2
  return 3
}

function queueSave() {
  if (!attempt.value) return
  saveState.value = 'saving'
  clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    if (!attempt.value) return
    try {
      await apiFetch(`/api/v1/psych/attempts/${attempt.value.id}`, { method: 'PUT', body: toRaw(answers) })
      saveState.value = 'saved'
    } catch {
      saveState.value = 'error'
    }
  }, 700)
}

function mark(block: number, letter: Letter, sign: 'most' | 'least') {
  const key = String(block)
  const current = { ...(answers.disc[key] ?? {}) }
  const other = sign === 'most' ? 'least' : 'most'
  current[sign] = current[sign] === letter ? undefined : letter
  if (current[other] === letter) current[other] = undefined
  answers.disc[key] = current
  queueSave()
}

function rate(id: number, value: number) {
  const key = String(id)
  if (answers.statements[key] === value) delete answers.statements[key]
  else answers.statements[key] = value
  queueSave()
}

function choose(id: number, letter: Letter) {
  answers.cases[String(id)] = letter
  queueSave()
}

function scrollTop() {
  if (import.meta.client) window.scrollTo({ top: 0, behavior: 'smooth' })
}

function next() {
  if (part.value === 1 && missingBlocks.value.length) {
    show(`В блоках ${missingBlocks.value.join(', ')} нужна одна отметка «+» и одна «−»`)
    return
  }
  part.value = Math.min(3, part.value + 1)
  scrollTop()
}

function back() {
  part.value = Math.max(1, part.value - 1)
  scrollTop()
}

async function finish() {
  if (!attempt.value) return
  if (missingBlocks.value.length) { part.value = 1; show('Сначала заполните все блоки части 1'); return }
  if (missingCases.value.length) { show(`Выберите вариант в ситуациях: ${missingCases.value.join(', ')}`); return }
  if (skippedStatements.value > 0 && !skipWarned.value) {
    skipWarned.value = true
    show(`В части 2 пропущено утверждений: ${skippedStatements.value}. Нажмите ещё раз, чтобы завершить так.`, 4000)
    return
  }
  busy.value = true
  clearTimeout(saveTimer)
  try {
    const nextState = await apiFetch<PsychState>(`/api/v1/psych/attempts/${attempt.value.id}/finish`, {
      method: 'POST',
      body: { answers: toRaw(answers), share_with_employers: share.value },
    })
    if (screen.data.value) screen.data.value.state = nextState
    attempt.value = null
    view.value = 'result'
    show('Тест завершён')
    scrollTop()
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось завершить тест')
  } finally {
    busy.value = false
  }
}

async function toggleShare() {
  const value = !share.value
  try {
    const nextState = await apiFetch<PsychState>('/api/v1/psych/me/share', { method: 'PUT', body: { share_with_employers: value } })
    if (screen.data.value) screen.data.value.state = nextState
    share.value = nextState.share_with_employers
    show(value ? 'Результаты видны работодателям' : 'Результаты скрыты от работодателей')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось сохранить')
  }
}

const partTabs = computed(() => [
  { id: 1, label: 'Стиль поведения', done: blocksDone.value, total: test.value?.blocks.length ?? 12 },
  { id: 2, label: 'Утверждения', done: statementsDone.value, total: test.value?.statements.length ?? 30 },
  { id: 3, label: 'Ситуации', done: casesDone.value, total: test.value?.cases.length ?? 5 },
])
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Карьера" :user="cabinetUser" :links="candidateLinks" />
    <main class="fsp-page">
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <template v-if="test && state">
          <!-- Вступление -->
          <section v-if="view === 'intro'" class="fsp-stack-24" style="max-width: 860px;">
            <div>
              <div class="fsp-eyebrow u-mb-8">Необязательный тест · не влияет на грейд</div>
              <h1 class="fsp-display fsp-title">{{ test.title }}</h1>
              <p class="u-muted-p" style="font-size: 16px; line-height: 24px;">{{ test.subtitle }}</p>
            </div>
            <p style="margin: 0; font-size: 16px; line-height: 24px;">{{ test.instruction }}</p>
            <div class="psy-parts">
              <div v-for="p in test.parts" :key="p.id" class="fsp-cut fsp-card fsp-stack-12">
                <span class="fsp-step-num">0{{ p.id }}</span>
                <b>{{ p.title }}</b>
                <span class="u-small">{{ p.meta }}</span>
                <span class="u-note">{{ p.hint }}</span>
              </div>
            </div>
            <div class="fsp-stack-12">
              <FspCheckbox v-model="consent" label="Согласен(на) на обработку результатов теста. Результаты хранятся до 12 месяцев; работодатели увидят их, только если я сам(а) открою доступ." />
              <ul class="u-note" style="margin: 0; padding-left: 20px;">
                <li v-for="l in state.limitations" :key="l">{{ l }}</li>
              </ul>
            </div>
            <div class="u-row-wrap">
              <FspButton v-if="state.attempt" size="lg" icon-right="arrow-right" :disabled="busy" @click="begin">Продолжить тест</FspButton>
              <FspButton v-else-if="state.can_start" size="lg" icon-right="arrow-right" :disabled="busy" @click="begin">Начать тест</FspButton>
              <FspButton v-if="state.result" size="lg" variant="outline" @click="view = 'result'">Мой результат</FspButton>
            </div>
            <p v-if="!state.can_start && state.next_attempt_at" class="u-note" style="margin: 0;">Пройти тест снова можно с {{ longDate(state.next_attempt_at) }}.</p>
          </section>

          <!-- Прохождение -->
          <section v-else-if="view === 'run'" class="fsp-stack-24">
            <div class="psy-sticky">
              <div class="u-between">
                <h1 class="fsp-display u-h3" style="margin: 0;">Часть {{ part }} из 3 · {{ test.parts[part - 1]?.title }}</h1>
                <span class="u-small">{{ minutes }} мин · {{ saveState === 'saving' ? 'сохраняем…' : saveState === 'saved' ? 'ответы сохранены' : saveState === 'error' ? 'не удалось сохранить, повторим' : 'ответы сохраняются автоматически' }}</span>
              </div>
              <div class="fsp-meter u-mt-12" role="progressbar" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100"><span :style="{ width: percent + '%', background: 'var(--success)' }" /></div>
              <nav class="psy-tabs" aria-label="Части теста">
                <button v-for="t in partTabs" :key="t.id" type="button" :aria-current="part === t.id ? 'step' : undefined" @click="part = t.id">
                  <span>{{ t.id }}. {{ t.label }}</span><b>{{ t.done }}/{{ t.total }}</b>
                </button>
              </nav>
            </div>

            <p class="u-note" style="margin: 0; max-width: 860px;">{{ test.parts[part - 1]?.hint }}</p>

            <!-- Часть 1 -->
            <div v-if="part === 1" class="psy-grid">
              <fieldset v-for="b in test.blocks" :key="b.id" :class="['fsp-cut', 'psy-block', answers.disc[String(b.id)]?.most && answers.disc[String(b.id)]?.least && 'psy-block-done']">
                <legend class="fsp-eyebrow">Блок {{ b.id }}</legend>
                <div class="psy-block-head" aria-hidden="true"><span /><span>+</span><span>−</span></div>
                <div v-for="it in b.items" :key="it.key" class="psy-block-row">
                  <span>{{ it.text }}</span>
                  <button type="button" class="psy-mark psy-mark-plus" :aria-pressed="answers.disc[String(b.id)]?.most === it.key" :aria-label="`Наиболее точно: ${it.text}`" @click="mark(b.id, it.key, 'most')">+</button>
                  <button type="button" class="psy-mark psy-mark-minus" :aria-pressed="answers.disc[String(b.id)]?.least === it.key" :aria-label="`Наименее точно: ${it.text}`" @click="mark(b.id, it.key, 'least')">−</button>
                </div>
              </fieldset>
            </div>

            <!-- Часть 2 -->
            <div v-else-if="part === 2" class="fsp-stack-12">
              <div class="psy-legend u-small">
                <span v-for="l in test.likert" :key="l.value"><b>{{ l.value }}</b> — {{ l.label.toLowerCase() }}</span>
              </div>
              <div v-for="s in test.statements" :key="s.id" class="psy-likert">
                <span><span class="u-small">{{ s.id }}.</span> {{ s.text }}</span>
                <div role="radiogroup" :aria-label="s.text" class="psy-scale">
                  <button v-for="l in test.likert" :key="l.value" type="button" role="radio" :aria-checked="answers.statements[String(s.id)] === l.value" :title="l.label" @click="rate(s.id, l.value)">{{ l.value }}</button>
                </div>
              </div>
            </div>

            <!-- Часть 3 -->
            <div v-else class="fsp-stack-24" style="max-width: 860px;">
              <fieldset v-for="c in test.cases" :key="c.id" class="psy-case">
                <legend><span class="fsp-eyebrow">Ситуация {{ c.id }}</span><span class="psy-case-text">{{ c.text }}</span></legend>
                <label v-for="o in c.options" :key="o.key" :class="['fsp-cut', 'psy-option', answers.cases[String(c.id)] === o.key && 'fsp-active']">
                  <input type="radio" :name="`case-${c.id}`" :checked="answers.cases[String(c.id)] === o.key" @change="choose(c.id, o.key)">
                  <span><b>{{ o.key }})</b> {{ o.text }}</span>
                </label>
              </fieldset>
              <FspCheckbox v-model="share" label="Показывать результаты работодателям (можно изменить позже)" />
            </div>

            <div class="u-between fsp-divider">
              <FspButton variant="ghost" :disabled="part === 1" @click="back">Назад</FspButton>
              <FspButton v-if="part < 3" icon-right="arrow-right" @click="next">Дальше</FspButton>
              <FspButton v-else variant="accept" icon="check" :disabled="busy" @click="finish">Завершить тест</FspButton>
            </div>
          </section>

          <!-- Результат -->
          <section v-else-if="state.result" class="fsp-columns">
            <div class="fsp-col-main fsp-stack-24">
              <div>
                <div class="fsp-eyebrow u-mb-8">Тест рабочего стиля · {{ longDate(state.finished_at) }}</div>
                <h1 class="fsp-display fsp-title">Ваш результат</h1>
                <p class="u-muted-p">Это описание рабочего стиля, а не оценка способностей. Работодатели видят его только с вашего согласия.</p>
              </div>
              <PsychResultView :result="state.result" />
            </div>
            <aside class="fsp-col-side fsp-stack-16">
              <div class="fsp-cut fsp-card fsp-stack-12">
                <div class="fsp-eyebrow">Видимость для работодателей</div>
                <div class="u-strong-16">{{ share ? 'Результаты открыты' : 'Результаты скрыты' }}</div>
                <p class="u-note" style="margin: 0;">Работодатель увидит стиль, шкалы и флаги надёжности в карточке кандидата. Результат старше 12 месяцев не показывается.</p>
                <FspButton size="sm" :variant="share ? 'outline' : 'primary'" @click="toggleShare">{{ share ? 'Скрыть от работодателей' : 'Открыть работодателям' }}</FspButton>
              </div>
              <div class="fsp-section-20 fsp-stack-12">
                <div class="u-note">{{ state.can_start ? 'Можно пройти тест заново.' : `Пройти тест заново можно с ${longDate(state.next_attempt_at)}.` }}</div>
                <FspButton v-if="state.can_start" size="sm" variant="outline" @click="view = 'intro'">Пройти заново</FspButton>
                <FspButton size="sm" variant="ghost" href="/candidate/grade">К тестам и грейду</FspButton>
              </div>
              <ul class="u-small" style="margin: 0; padding-left: 18px;">
                <li v-for="l in state.limitations" :key="l">{{ l }}</li>
              </ul>
            </aside>
          </section>
        </template>
      </ScreenState>
    </main>
  </div>
</template>

<style>
.psy-parts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr)); gap: 12px; }
.psy-sticky { position: sticky; top: 0; z-index: 5; background: var(--bg); padding: 12px 0; box-shadow: 0 1px 0 var(--line); }
.psy-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.psy-tabs button { all: unset; cursor: pointer; display: inline-flex; gap: 10px; padding: 8px 12px; font-size: 14px; color: var(--text-muted); box-shadow: inset 0 -2px 0 transparent; }
.psy-tabs button[aria-current="step"] { color: var(--text); box-shadow: inset 0 -3px 0 var(--accent-mark); }
.psy-tabs button:focus-visible { outline: 2px solid var(--focus); }
.psy-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 380px), 1fr)); gap: 16px; }
.psy-block { --cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: 1px; margin: 0; padding: 16px 16px 12px; border: 0; }
.psy-block-done { --edge: var(--success); }
.psy-block legend { padding: 0 4px; }
.psy-block-head, .psy-block-row { display: grid; grid-template-columns: 1fr 40px 40px; gap: 8px; align-items: center; }
.psy-block-head span { text-align: center; font-weight: 700; color: var(--text-muted); font-size: 13px; }
.psy-block-row { padding: 6px 0; box-shadow: inset 0 1px 0 var(--line); font-size: 15px; line-height: 21px; }
.psy-mark { width: 40px; height: 36px; border: 1px solid var(--line-strong); background: transparent; color: var(--text); font: 700 18px/1 var(--font-sans); cursor: pointer; }
.psy-mark:hover { background: var(--surface-hover); }
.psy-mark-plus[aria-pressed="true"] { background: var(--success); border-color: var(--success); color: var(--brand-black); }
.psy-mark-minus[aria-pressed="true"] { background: var(--danger); border-color: var(--danger); color: #ffffff; }
.psy-mark:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
.psy-legend { display: flex; flex-wrap: wrap; gap: 6px 16px; }
.psy-likert { display: grid; grid-template-columns: 1fr auto; gap: 8px 24px; align-items: center; padding: 10px 0; box-shadow: inset 0 1px 0 var(--line); font-size: 15px; line-height: 22px; }
.psy-scale { display: flex; gap: 4px; }
.psy-scale button { width: 44px; height: 40px; border: 1px solid var(--line-strong); background: transparent; color: var(--text); font: 600 15px/1 var(--font-sans); cursor: pointer; }
.psy-scale button:hover { background: var(--surface-hover); }
.psy-scale button[aria-checked="true"] { background: var(--primary); border-color: var(--primary); color: var(--on-primary); }
.psy-scale button:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
.psy-case { border: 0; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.psy-case legend { display: flex; flex-direction: column; gap: 6px; margin-bottom: 8px; }
.psy-case-text { font-size: 17px; line-height: 25px; font-weight: 600; }
.psy-option { --cut: var(--cut-s); --fill: var(--bg); --edge: var(--line-strong); --bw: 1px; padding: 14px 16px; display: flex; gap: 12px; align-items: flex-start; cursor: pointer; line-height: 22px; }
.psy-option input { accent-color: var(--primary); width: 18px; height: 18px; margin: 2px 0 0; flex: none; }
@media (max-width: 640px) {
  .psy-likert { grid-template-columns: 1fr; }
  .psy-scale button { flex: 1; width: auto; }
  .psy-block-head, .psy-block-row { grid-template-columns: 1fr 36px 36px; }
  .psy-mark { width: 36px; }
}
</style>
