<script setup lang="ts">
import type { components } from '~/api/schema'
import type { CatView, Eligibility } from '~/utils/cat'
import { CAT_DECISION_LABEL, CAT_FORMAT_LABEL, CAT_MAX_ITEMS, CAT_MIN_ITEMS, catFormat, catMode, clock } from '~/utils/cat'
import { read } from '~/utils/read'
import { apiFetch } from '~/utils/raw'

type Spec = components['schemas']['Specialization']
type Grade = components['schemas']['Grade']

const OPEN_SPECS = new Set(['backend', 'frontend'])
const LETTERS = 'ABCDEFGHIJ'

useHead({ title: 'Опрос и тест на грейд — Карьера ФСП' })
const cabinetUser = useCabinetUser('Кандидат')
const links = candidateLinks.map(link => ({ ...link, active: link.href === '/candidate/grade' }))
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
const confirmFinish = ref(false)
let tick: ReturnType<typeof setInterval> | undefined
let confirmTimer: ReturnType<typeof setTimeout> | undefined

watch(screen.data, (bundle) => {
  if (!bundle) return
  industries.value = [...(bundle.profile.liked_domains ?? [])]
  if (bundle.profile.specialization && !spec.value && OPEN_SPECS.has(bundle.profile.specialization)) {
    spec.value = bundle.profile.specialization
  }
}, { immediate: true })

const openSpecs = computed(() => (screen.data.value?.specs ?? []).filter(s => OPEN_SPECS.has(s.id)))
const task = computed(() => attempt.value?.task ?? null)
const result = computed(() => attempt.value?.result ?? null)
const format = computed(() => catFormat(task.value))
const mode = computed(() => catMode(task.value))
const multiple = computed(() => !!task.value?.multiple || format.value === 'MSQ')
const languages = computed(() => task.value?.languages?.length ? task.value.languages : ['python'])
const timerOn = computed(() => attempt.value?.timer_enabled === true)
const limitMinutes = computed(() => attempt.value?.time_limit_minutes ?? 90)
const answered = computed(() => attempt.value?.progress.answered ?? 0)
const progressPct = computed(() => Math.min(100, Math.round(answered.value / CAT_MAX_ITEMS * 100)))
const step = computed(() => {
  if (result.value) return 4
  if (attempt.value && !result.value) return 3
  if (!industries.value.length) return 1
  return 2
})
const canStart = computed(() => !!industries.value.length && !!spec.value && !!grade.value)

const canSubmit = computed(() => {
  if (!task.value || busy.value) return false
  if (mode.value === 'choice') return multiple.value ? pickedMany.value.length > 0 : !!picked.value
  if (mode.value === 'code') return code.value.trim().length >= 10
  if (mode.value === 'short') return written.value.trim().length > 0
  return written.value.trim().length >= 15
})

const hint = computed(() => {
  if (mode.value === 'choice') {
    const keys = `Клавиши 1–${Math.min(task.value?.options?.length ?? 0, 9)} выбирают вариант, Enter — ответить.`
    return multiple.value
      ? `Отметьте все верные варианты: за каждый лишний снимается балл. ${keys}`
      : `Выберите один вариант. ${keys}`
  }
  if (mode.value === 'short') return 'Короткий ответ: число, слово или порядок через запятую. Enter — ответить.'
  if (mode.value === 'code') return 'Решение оценивается по ключевым элементам рубрики, запуск в песочнице подключим позже. Tab — отступ, Ctrl+Enter — ответить.'
  return 'Отвечайте по пунктам: проверяется, назвали ли вы ключевые проблемы и решения. Ctrl+Enter — ответить.'
})

function applyAttempt(next: CatView) {
  const changed = next.task?.id !== attempt.value?.task?.id
  attempt.value = next
  rememberAttempt(next.id)
  picked.value = ''
  pickedMany.value = []
  written.value = ''
  code.value = ''
  language.value = next.task?.languages?.[0] || 'python'
  remaining.value = next.remaining_seconds
  resetConfirm()
  if (changed && import.meta.client) window.scrollTo({ top: 0, behavior: 'smooth' })
}

function choose(id: string) {
  if (!multiple.value) {
    picked.value = id
    return
  }
  pickedMany.value = pickedMany.value.includes(id)
    ? pickedMany.value.filter(item => item !== id)
    : [...pickedMany.value, id]
}

function isPicked(id: string) {
  return multiple.value ? pickedMany.value.includes(id) : picked.value === id
}

function startClock() {
  clearInterval(tick)
  if (!timerOn.value || attempt.value?.finished_at) return
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
  const ids = [...new Set([eligibility.value?.active_attempt_id, rememberedAttempt()].filter(Boolean))] as string[]
  for (const id of ids) {
    try {
      const view = await apiFetch<CatView>(`/api/v1/assessment/attempts/${id}`)
      if (view.engine !== 'cat' || view.finished_at) continue
      applyAttempt(view)
      startClock()
      return
    } catch {
      // Попытка удалена или чужая — пробуем следующую.
    }
  }
  sessionStorage.removeItem('fsp-attempt-id')
}

function onKey(event: KeyboardEvent) {
  if (step.value !== 3 || !task.value || busy.value) return
  const target = event.target as HTMLElement | null
  const typing = !!target && (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT') && target.getAttribute('type') !== 'radio' && target.getAttribute('type') !== 'checkbox'
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    if (canSubmit.value) void send(false)
    return
  }
  if (typing || mode.value !== 'choice' || event.altKey || event.ctrlKey || event.metaKey) return
  const options = task.value.options ?? []
  const index = Number(event.key) - 1
  if (Number.isInteger(index) && index >= 0 && index < options.length) {
    event.preventDefault()
    choose(options[index]!.id)
  } else if (event.key === 'Enter' && canSubmit.value && target?.tagName !== 'BUTTON' && target?.tagName !== 'A') {
    event.preventDefault()
    void send(false)
  }
}

onMounted(() => {
  void resume()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  clearInterval(tick)
  clearTimeout(confirmTimer)
  window.removeEventListener('keydown', onKey)
})

function pickSpec(id: string) {
  if (!OPEN_SPECS.has(id)) return
  spec.value = id as Spec
}

function toggleIndustry(id: string) {
  if (industries.value.includes(id)) {
    industries.value = industries.value.filter(x => x !== id)
  } else if (industries.value.length >= 3) {
    show('Можно выбрать до трёх отраслей')
  } else {
    industries.value = [...industries.value, id]
  }
}

function onCodeKey(event: KeyboardEvent) {
  if (event.key !== 'Tab' || event.shiftKey) return
  const target = event.target as HTMLTextAreaElement
  event.preventDefault()
  const { selectionStart: from, selectionEnd: to, value } = target
  code.value = value.slice(0, from) + '    ' + value.slice(to)
  void nextTick(() => { target.selectionStart = target.selectionEnd = from + 4 })
}

function payload() {
  const current = task.value
  if (!current) return null
  if (mode.value === 'choice') return { task_id: current.id, answer: multiple.value ? pickedMany.value.join(',') : picked.value }
  if (mode.value === 'code') return { task_id: current.id, code: code.value, language: language.value }
  return { task_id: current.id, answer: written.value.trim() }
}

async function start() {
  if (!canStart.value) {
    show(!industries.value.length ? 'Выберите хотя бы одну отрасль' : !spec.value ? 'Выберите специализацию' : 'Выберите грейд')
    return
  }
  busy.value = true
  try {
    await read(api.PUT('/api/v1/candidates/me', { body: { liked_domains: industries.value, specialization: spec.value as Spec } }))
    const next = await apiFetch<CatView>('/api/v1/assessment/attempts', {
      method: 'POST',
      body: { specialization: spec.value, declared_grade: grade.value },
    })
    applyAttempt(next)
    startClock()
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось начать тест')
    await loadEligibility()
    if (eligibility.value?.active_attempt_id) await resume()
  } finally {
    busy.value = false
  }
}

async function send(skip: boolean) {
  if (!attempt.value || !task.value || busy.value) return
  if (!skip && !canSubmit.value) return
  const body = skip ? { task_id: task.value.id, skip: true } : payload()
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

function resetConfirm() {
  confirmFinish.value = false
  clearTimeout(confirmTimer)
}

async function finishNow() {
  if (!attempt.value || busy.value) return
  if (task.value && !confirmFinish.value) {
    confirmFinish.value = true
    clearTimeout(confirmTimer)
    confirmTimer = setTimeout(resetConfirm, 5000)
    return
  }
  resetConfirm()
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
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Карьера" :user="cabinetUser" :links="links" />
    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px;">
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <nav aria-label="Шаги онбординга" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr)); gap: 8px; margin-bottom: 40px;">
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step > 1 ? 'var(--success)' : 'var(--warning)') }"><div class="cat-label">Шаг 1</div><div style="font-weight: 600; margin-top: 4px;">Специализация</div></div>
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step > 2 ? 'var(--success)' : step === 2 ? 'var(--warning)' : 'var(--line-strong)') }"><div class="cat-label">Шаг 2</div><div style="font-weight: 600; margin-top: 4px;">Предполагаемый грейд</div></div>
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step > 3 ? 'var(--success)' : step === 3 ? 'var(--warning)' : 'var(--line-strong)') }"><div class="cat-label">Шаг 3</div><div style="font-weight: 600; margin-top: 4px;">Адаптивный тест</div></div>
          <div :style="{ padding: '14px 0', boxShadow: 'inset 0 3px 0 ' + (step === 4 ? 'var(--success)' : 'var(--line-strong)') }"><div class="cat-label">Шаг 4</div><div style="font-weight: 600; margin-top: 4px;">Результат</div></div>
        </nav>

        <section v-if="step < 3" style="display: flex; flex-direction: column; gap: 24px; max-width: 760px;">
          <h1 class="fsp-display" style="font-size: 36px; line-height: 40px; margin: 0;">Опрос</h1>
          <p style="margin: 0; color: var(--text-muted); line-height: 24px;">Выберите отрасли, специализацию и грейд, на который претендуете. Дальше адаптивный тест: теория, отладка, код, ревью и кейс. Обычно 8–20 заданий; на тест будет отведено 90 минут, но сейчас таймер выключен.</p>
          <p v-if="eligibility && !eligibility.can_start && eligibility.message" style="margin: 0; color: var(--text-muted);">{{ eligibility.message }}<template v-if="eligibility.retry_at"> С {{ new Date(eligibility.retry_at).toLocaleDateString('ru-RU') }}.</template></p>
          <div>
            <div class="cat-label" style="margin-bottom: 10px;">Отрасль · до трёх</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="d in screen.data.value?.domains ?? []" :key="d.id" :selected="industries.includes(d.id)" locked @click="toggleIndustry(d.id)">{{ d.name }}</FspChip>
            </div>
          </div>
          <div>
            <div class="cat-label" style="margin-bottom: 10px;">Специализация</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="s in openSpecs" :key="s.id" :selected="spec === s.id" locked @click="pickSpec(s.id)">{{ s.name }}</FspChip>
            </div>
            <p style="margin: 10px 0 0; font-size: 14px; color: var(--text-muted);">Сейчас тест доступен для Backend и Frontend. Остальные направления подключим позже.</p>
          </div>
          <div>
            <div class="cat-label" style="margin-bottom: 10px;">Грейд</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="g in GRADES" :key="g" :selected="grade === g" locked @click="grade = g">{{ GRADE_LABEL[g] }}</FspChip>
            </div>
          </div>
          <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 16px;">
            <FspButton icon-right="arrow-right" :disabled="busy || !canStart || (eligibility?.can_start === false && !eligibility.active_attempt_id)" @click="start">Начать тест</FspButton>
            <span v-if="!canStart" style="font-size: 14px; color: var(--text-muted);">{{ !industries.length ? 'Выберите хотя бы одну отрасль' : !spec ? 'Выберите специализацию' : 'Выберите грейд' }}</span>
          </div>
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

        <div v-else-if="attempt" style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
          <section v-if="task" style="flex: 999 1 640px; min-width: 0; display: flex; flex-direction: column; gap: 20px;">
            <div style="display: flex; flex-direction: column; gap: 10px;">
              <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 10px;">
                <span class="fsp-display" style="font-size: 18px; line-height: 24px;">Задание {{ answered + 1 }}</span>
                <span style="font-size: 14px; color: var(--text-muted);">из {{ CAT_MIN_ITEMS }}–{{ CAT_MAX_ITEMS }}</span>
                <FspTag>{{ CAT_FORMAT_LABEL[format] || format }}</FspTag>
                <FspTag v-if="task.time_minutes">≈ {{ task.time_minutes }} мин</FspTag>
                <span v-if="timerOn" style="margin-left: auto; font-variant-numeric: tabular-nums;">{{ clock(remaining) }}</span>
                <span v-else style="margin-left: auto; font-size: 14px; color: var(--text-muted);" title="Таймер пока выключен: отвечайте в своём темпе">Таймер {{ limitMinutes }} мин · выключен</span>
              </div>
              <div class="cat-progress" role="progressbar" :aria-valuenow="answered" aria-valuemin="0" :aria-valuemax="CAT_MAX_ITEMS" :aria-label="`Отвечено ${answered} из максимум ${CAT_MAX_ITEMS}`">
                <div class="cat-progress-fill" :style="{ width: progressPct + '%' }" />
                <div class="cat-progress-min" :style="{ left: (CAT_MIN_ITEMS / CAT_MAX_ITEMS * 100) + '%' }" />
              </div>
            </div>

            <h1 class="fsp-display" style="font-size: 26px; line-height: 32px; margin: 0;">{{ task.title || 'Задание' }}</h1>
            <p style="margin: 0; white-space: pre-line; font-size: 17px; line-height: 27px;">{{ task.body }}</p>
            <pre v-if="task.snippet" class="cat-snippet">{{ task.snippet }}</pre>

            <form style="display: flex; flex-direction: column; gap: 12px;" @submit.prevent="send(false)">
              <div v-if="mode === 'choice'" :role="multiple ? 'group' : 'radiogroup'" :aria-label="multiple ? 'Варианты, можно несколько' : 'Варианты ответа'" style="display: flex; flex-direction: column; gap: 8px;">
                <label v-for="(opt, i) in task.options ?? []" :key="opt.id" :class="['cat-option', isPicked(opt.id) && 'is-on', multiple && 'is-multi']">
                  <input :type="multiple ? 'checkbox' : 'radio'" name="cat-option" :value="opt.id" :checked="isPicked(opt.id)" @change="choose(opt.id)">
                  <span class="cat-option-key" aria-hidden="true">{{ multiple && isPicked(opt.id) ? '✓' : LETTERS[i] }}</span>
                  <span class="cat-option-text">{{ opt.text }}</span>
                </label>
              </div>

              <input v-else-if="mode === 'short'" v-model="written" class="cat-field" type="text" autocomplete="off" aria-label="Ответ" :placeholder="task.placeholder || 'Ваш ответ'" @keydown.enter.prevent="send(false)">

              <template v-else-if="mode === 'code'">
                <div v-if="languages.length > 1" style="display: flex; flex-wrap: wrap; gap: 8px;">
                  <FspChip v-for="lang in languages" :key="lang" :selected="language === lang" locked @click="language = lang">{{ lang }}</FspChip>
                </div>
                <div v-else class="cat-label">Язык: {{ languages[0] }}</div>
                <textarea v-model="code" class="cat-field is-code" aria-label="Код решения" spellcheck="false" autocomplete="off" :placeholder="task.placeholder || 'Напишите решение'" @keydown="onCodeKey" />
              </template>

              <textarea v-else v-model="written" class="cat-field is-text" aria-label="Ответ" :placeholder="task.placeholder || 'Ваш ответ'" />

              <p style="margin: 0; font-size: 14px; line-height: 20px; color: var(--text-muted);">{{ hint }}</p>

              <div style="display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 4px;">
                <FspButton variant="ghost" :disabled="busy" @click="send(true)">Пропустить</FspButton>
                <FspButton type="submit" icon-right="arrow-right" :disabled="!canSubmit">{{ busy ? 'Сохраняем…' : 'Ответить' }}</FspButton>
              </div>
            </form>
          </section>

          <section v-else style="flex: 999 1 640px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
            <h1 class="fsp-display" style="font-size: 26px; line-height: 32px; margin: 0;">Задания закончились</h1>
            <p style="margin: 0; color: var(--text-muted); line-height: 24px;">Подходящих заданий в банке больше нет. Завершите тест, чтобы получить результат по уже данным ответам.</p>
            <div><FspButton :disabled="busy" @click="finishNow">Завершить и посмотреть результат</FspButton></div>
          </section>

          <aside style="flex: 1 1 300px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
            <FspPlate :dots="6">
              <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Вы заявили</div>
              <div class="fsp-display" style="font-size: 24px; line-height: 28px; margin: 10px 0 6px;">{{ categoryLabel(attempt.specialization, attempt.declared_grade) }}</div>
              <div style="font-size: 14px; line-height: 20px; color: var(--on-plate-muted);">Тест адаптивный: следующее задание подбирается по вашим ответам. Он закончится сам, когда оценка станет точной — от {{ CAT_MIN_ITEMS }} до {{ CAT_MAX_ITEMS }} заданий.</div>
            </FspPlate>
            <div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">
              <template v-if="timerOn">На весь тест {{ limitMinutes }} минут. Когда время выйдет, тест завершится по уже данным ответам.</template>
              <template v-else>На весь тест будет отведено {{ limitMinutes }} минут. Сейчас таймер выключен — отвечайте в своём темпе, прогресс сохраняется.</template>
            </div>
            <div v-if="task?.tags?.length" style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspTag v-for="tag in task.tags" :key="tag">{{ tag }}</FspTag>
            </div>
            <div v-if="task" style="display: flex; flex-direction: column; gap: 8px;">
              <FspButton :variant="confirmFinish ? 'decline' : 'outline'" size="sm" :disabled="busy" @click="finishNow">{{ confirmFinish ? 'Точно завершить? Нажмите ещё раз' : 'Завершить досрочно' }}</FspButton>
              <span v-if="confirmFinish" style="font-size: 13px; line-height: 18px; color: var(--text-muted);">Результат посчитаем по {{ answered }} {{ answered === 1 ? 'ответу' : 'ответам' }}. Пересдача — через 30 дней.</span>
            </div>
            <FspButton variant="ghost" size="sm" href="/candidate/grade">Вернуться позже</FspButton>
          </aside>
        </div>
      </ScreenState>
    </main>
  </div>
</template>

<style>
.cat-label { font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); }
.cat-progress { position: relative; height: 4px; background: var(--line); }
.cat-progress-fill { height: 100%; background: var(--primary); transition: width .3s ease; }
.cat-progress-min { position: absolute; top: -4px; width: 2px; height: 12px; background: var(--text-muted); }
.cat-snippet { margin: 0; padding: 16px 18px; overflow-x: auto; white-space: pre; border: 1px solid var(--line); background: color-mix(in srgb, var(--text) 6%, var(--bg)); color: var(--text); font: 14px/22px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; tab-size: 4; }
.cat-option { position: relative; display: flex; align-items: flex-start; gap: 14px; padding: 14px 16px; border: 1px solid var(--line-strong); background: var(--surface); color: var(--text); cursor: pointer; transition: border-color .15s, background-color .15s, color .15s; }
.cat-option:hover { border-color: var(--text); }
.cat-option input { position: absolute; opacity: 0; pointer-events: none; }
.cat-option:has(input:focus-visible) { outline: 2px solid var(--focus); outline-offset: 2px; }
.cat-option.is-on { border-color: var(--plate); background: var(--plate); color: var(--on-plate); }
.cat-option-key { flex: none; display: grid; place-items: center; width: 28px; height: 28px; border: 1px solid currentColor; border-radius: 50%; font: 600 13px/1 var(--font-sans); }
.cat-option.is-multi .cat-option-key { border-radius: 0; }
.cat-option.is-on .cat-option-key { border-color: var(--primary); background: var(--primary); color: var(--on-primary); }
.cat-option-text { padding-top: 2px; font-size: 16px; line-height: 24px; overflow-wrap: anywhere; }
.cat-field { box-sizing: border-box; width: 100%; margin: 0; padding: 14px 16px; border: 1px solid var(--line-strong); background: var(--field); color: var(--text); font: 16px/24px var(--font-sans); }
.cat-field:focus { outline: 2px solid var(--focus); outline-offset: 1px; }
.cat-field.is-text { min-height: 200px; resize: vertical; }
.cat-field.is-code { min-height: 280px; resize: vertical; font: 14px/22px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; tab-size: 4; white-space: pre; overflow-x: auto; }
</style>
