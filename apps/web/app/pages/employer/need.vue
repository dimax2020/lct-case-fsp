<script setup lang="ts">
import type { components } from '~/api/schema'
import type { Blueprint } from '~/utils/cat'
import { CAT_FORMAT_LABEL } from '~/utils/cat'
import { read } from '~/utils/read'
import { apiFetch } from '~/utils/raw'

type Spec = components['schemas']['Specialization']
type Grade = components['schemas']['Grade']
type WorkFormat = components['schemas']['WorkFormat']
type Req = components['schemas']['RequirementOut']
type Kind = components['schemas']['RequirementKind']

useHead({ title: 'Описание потребности — Карьера ФСП' })
const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => {
  const [specs, domains, needs, company] = await Promise.all([
    read(api.GET('/api/v1/taxonomy/specializations')),
    read(api.GET('/api/v1/taxonomy/domains')),
    read(api.GET('/api/v1/needs')),
    read(api.GET('/api/v1/companies/me')),
  ])
  return { specs, domains, needs, company }
})

const needId = ref('')
const title = ref('')
const spec = ref<Spec>('backend')
const grades = ref<Grade[]>(['middle'])
const salaryFrom = ref<string | number>('')
const salaryTo = ref<string | number>('')
const formats = ref<WorkFormat[]>(['remote'])
const city = ref('')
const must = ref<string[]>([])
const nice = ref<string[]>([])
const description = ref('')
const domain = ref('fintech')
const stages = ref<string | number>(2)
const tech = ref('')
const hits = ref<components['schemas']['SkillHit'][]>([])
const requirements = ref<Req[]>([])
const blueprint = ref<Blueprint | null>(null)
const parsing = ref(false)
const matching = ref(false)
const jobStatus = ref('')
let skillTimer: ReturnType<typeof setTimeout> | undefined

watch(screen.data, (bundle) => {
  const saved = rememberedNeed()
  const need = bundle?.needs.find(n => n.id === saved) ?? bundle?.needs[0]
  if (!need) return
  needId.value = need.id
  rememberNeed(need.id)
  title.value = need.title
  spec.value = need.specialization
  grades.value = need.grades.filter((g): g is Grade => GRADES.includes(g as Grade))
  salaryFrom.value = need.salary_from
  salaryTo.value = need.salary_to
  formats.value = [...need.formats]
  city.value = need.city ?? ''
  must.value = [...need.must_skills]
  nice.value = [...(need.nice_skills ?? [])]
  description.value = need.description
  domain.value = need.domain
  stages.value = need.stages
}, { immediate: true })

const companyName = computed(() => screen.data.value?.company.name || 'Компания')
const adjacent = computed(() => {
  const row = screen.data.value?.specs.find(s => s.id === spec.value)
  return row?.adjacent ?? []
})

function toggleGrade(g: Grade) {
  if (grades.value.includes(g)) {
    grades.value = grades.value.filter(x => x !== g)
    return
  }
  if (grades.value.length >= 2) {
    show('Можно указать не больше двух грейдов')
    return
  }
  if (grades.value.length === 1) {
    const current = grades.value[0]
    if (!current) return
    const a = GRADES.indexOf(current)
    const b = GRADES.indexOf(g)
    if (Math.abs(a - b) !== 1) {
      show('Второй грейд должен быть соседним')
      return
    }
  }
  grades.value = [...grades.value, g]
}

function toggleFormat(f: WorkFormat) {
  formats.value = formats.value.includes(f) ? formats.value.filter(x => x !== f) : [...formats.value, f]
}

function onTech() {
  clearTimeout(skillTimer)
  skillTimer = setTimeout(async () => {
    const q = tech.value.trim()
    hits.value = q ? await read(api.GET('/api/v1/taxonomy/skills', { params: { query: { q, limit: 8 } } })) : []
  }, 200)
}

function addSkill(id: string) {
  if (must.value.includes(id) || nice.value.includes(id)) return
  if (must.value.length >= 5) {
    nice.value = [...nice.value, id].slice(0, 5)
    show('Обязательных уже пять — навык добавлен в желательные')
  } else must.value.push(id)
  tech.value = ''
  hits.value = []
}

function move(id: string, to: 'must' | 'nice') {
  if (to === 'must' && must.value.length >= 5) {
    show('Обязательных навыков не больше пяти')
    return
  }
  if (to === 'nice' && nice.value.length >= 5) {
    show('Желательных навыков не больше пяти')
    return
  }
  must.value = must.value.filter(x => x !== id)
  nice.value = nice.value.filter(x => x !== id)
  if (to === 'must') must.value.push(id)
  else nice.value.push(id)
}

function payload() {
  return {
    title: title.value.trim(),
    specialization: spec.value,
    grades: grades.value,
    salary_from: parseMoney(salaryFrom.value),
    salary_to: parseMoney(salaryTo.value),
    formats: formats.value,
    city: city.value || null,
    must_skills: must.value,
    nice_skills: nice.value,
    description: description.value,
    domain: domain.value,
    stages: Number(stages.value),
  }
}

async function save(silent = false) {
  const body = payload()
  const saved = needId.value
    ? await read(api.PUT('/api/v1/needs/{id}', { params: { path: { id: needId.value } }, body }))
    : await read(api.POST('/api/v1/needs', { body }))
  needId.value = saved.id
  rememberNeed(saved.id)
  if (!silent) show('Потребность сохранена')
  return saved
}

async function parseNeed() {
  parsing.value = true
  try {
    const saved = await save(true)
    const parsed = await read(api.POST('/api/v1/needs/{id}/parse', { params: { path: { id: saved.id } } }))
    requirements.value = parsed.requirements ?? []
    try {
      blueprint.value = await apiFetch<Blueprint>(`/api/v1/assessment/blueprint?need_id=${saved.id}`)
    } catch {
      blueprint.value = null
    }
    show(parsed.llm_used ? 'Описание разобрано' : 'Сохранено без разбора LLM — матчинг пойдёт по навыкам формы')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось сохранить')
  } finally {
    parsing.value = false
  }
}

function setKind(req: Req, kind: Kind) {
  req.kind = kind
}

async function build() {
  matching.value = true
  jobStatus.value = 'Сохраняем…'
  try {
    const saved = await save(true)
    if (!requirements.value.length) {
      const parsed = await read(api.POST('/api/v1/needs/{id}/parse', { params: { path: { id: saved.id } } }))
      requirements.value = parsed.requirements ?? []
    }
    jobStatus.value = 'Собираем подборку…'
    const accepted = await read(api.POST('/api/v1/needs/{id}/match', { params: { path: { id: saved.id } } }))
    let status = 'queued'
    for (let i = 0; i < 8 && status !== 'done' && status !== 'failed'; i++) {
      await new Promise(r => setTimeout(r, 700))
      const job = await read(api.GET('/api/v1/jobs/{id}', { params: { path: { id: accepted.job_id } } }))
      status = job.status
      jobStatus.value = status === 'done' ? 'Подборка готова' : status === 'failed' ? (job.error || 'Не удалось собрать подборку') : 'Считаем совпадения…'
    }
    if (status === 'failed') return
    show('Подборка сформирована')
    await navigateTo({ path: '/employer/pool', query: { need: saved.id } })
  } catch (e) {
    jobStatus.value = ''
    show(e instanceof Error ? e.message : 'Не удалось сформировать подборку')
  } finally {
    matching.value = false
  }
}

onBeforeUnmount(() => clearTimeout(skillTimer))
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Для компаний" :user="companyName" :links="employerLinks" />
    <main class="fsp-page">
      <h1 class="fsp-display fsp-title">Кого ищем</h1>
      <p style="margin: 0 0 32px; font-size: 16px; color: var(--text-muted);">Опишите потребность — соберём подборку из уже проверенных кандидатов. Вакансию публиковать не обязательно.</p>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <div class="fsp-columns">
          <form style="flex: 999 1 620px; min-width: 0; display: flex; flex-direction: column; gap: 28px;" @submit.prevent="build">
            <FspInput v-model="title" label="Название роли" />
            <div>
              <div class="fsp-eyebrow u-mb-10">Специализация</div>
              <div class="u-row-wrap">
                <FspChip v-for="s in screen.data.value?.specs ?? []" :key="s.id" :selected="spec === s.id" locked @click="spec = s.id as Spec">{{ s.name }}</FspChip>
              </div>
            </div>
            <div>
              <div class="fsp-eyebrow u-mb-10">Грейд</div>
              <div class="u-row-wrap">
                <FspChip v-for="g in GRADES" :key="g" :selected="grades.includes(g)" locked @click="toggleGrade(g)">{{ GRADE_LABEL[g] }}</FspChip>
              </div>
            </div>
            <div>
              <div class="fsp-eyebrow u-mb-10">Обязательные навыки · {{ must.length }}/5</div>
              <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px;">
                <button v-for="id in must" :key="id" type="button" class="u-unbutton" @click="move(id, 'nice')"><FspTag>{{ skillLabel(id) }} · в желательные</FspTag></button>
              </div>
              <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin: 12px 0 10px;">Желательные · {{ nice.length }}/5</div>
              <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px;">
                <button v-for="id in nice" :key="id" type="button" class="u-unbutton" @click="must.length < 5 ? move(id, 'must') : nice = nice.filter(x => x !== id)"><FspTag>{{ skillLabel(id) }} ×</FspTag></button>
              </div>
              <FspInput v-model="tech" icon="search" placeholder="Добавить из онтологии" aria-label="Добавить технологию" @input="onTech" />
              <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px;">
                <button v-for="h in hits" :key="h.id" type="button" class="u-unbutton" @click="addSkill(h.id)"><FspTag>{{ h.name }}</FspTag></button>
              </div>
            </div>
            <label style="display: flex; flex-direction: column; gap: 6px;">
              <span class="fsp-eyebrow">Чем занимается команда · {{ description.trim().length }}/300</span>
              <textarea v-model="description" rows="6" placeholder="Что человек будет делать первые 3 месяца" style="font: 400 16px/24px var(--font-sans); color: var(--text); background: var(--field); border: 1px solid var(--line-strong); padding: 12px 16px; resize: vertical;" />
            </label>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 16px;">
              <FspInput v-model="salaryFrom" label="Зарплата от" suffix="₽" />
              <FspInput v-model="salaryTo" label="Зарплата до" suffix="₽" />
              <FspInput v-model="city" label="Город" />
              <FspInput v-model="stages" label="Этапов найма" inputmode="numeric" />
            </div>
            <div>
              <div class="fsp-eyebrow u-mb-8">Формат</div>
              <div class="u-row-wrap">
                <FspChip v-for="f in FORMATS" :key="f" :selected="formats.includes(f)" locked @click="toggleFormat(f)">{{ FORMAT_LABEL[f] }}</FspChip>
              </div>
            </div>
            <div>
              <div class="fsp-eyebrow u-mb-8">Домен</div>
              <div class="u-row-wrap">
                <FspChip v-for="d in screen.data.value?.domains ?? []" :key="d.id" :selected="domain === d.id" locked @click="domain = d.id">{{ d.name }}</FspChip>
              </div>
            </div>
            <p style="margin: 0; font-size: 13px; color: var(--text-muted);">Вилка и описание от 300 символов проверяет API. Смежные специализации: {{ adjacent.join(', ') || '—' }}.</p>
            <section v-if="requirements.length" style="display: flex; flex-direction: column; gap: 10px;">
              <h2 class="fsp-display" style="font-size: 18px;">Разобранные требования</h2>
              <div v-for="(req, i) in requirements" :key="req.id || i" style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding-top: 10px; box-shadow: inset 0 1px 0 var(--line);">
                <div style="flex: 1 1 240px;">
                  <b>{{ req.task }}</b>
                  <div class="u-small">{{ (req.skills ?? []).map(skillLabel).join(', ') }}</div>
                </div>
                <FspChip :selected="req.kind === 'must'" locked @click="setKind(req, 'must')">Обязательно</FspChip>
                <FspChip :selected="req.kind === 'nice'" locked @click="setKind(req, 'nice')">Желательно</FspChip>
                <FspButton size="sm" variant="ghost" @click="requirements = requirements.filter((_, n) => n !== i)">Удалить</FspButton>
              </div>
            </section>
            <div v-if="jobStatus" style="font-size: 14px;">{{ jobStatus }}</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; padding-top: 20px; box-shadow: inset 0 1px 0 var(--line);">
              <FspButton size="lg" icon-right="arrow-right" type="submit" :disabled="matching">Сформировать подборку</FspButton>
              <FspButton size="lg" variant="ghost" type="button" :disabled="parsing" @click="parseNeed">Сохранить и разобрать</FspButton>
            </div>
          </form>
          <aside style="flex: 1 1 340px; min-width: 0;">
            <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line); font-size: 14px; line-height: 20px; color: var(--text-muted);">
              <div class="fsp-display" style="font-size: 16px; line-height: 20px; color: var(--text); margin-bottom: 10px;">Как строится подборка</div>
              Кандидаты попадают в категорию по результатам адаптивного теста. Описание длиннее 300 символов API разбирает на требования: их можно переключить между «обязательно» и «желательно» или удалить.
            </div>
            <div v-if="blueprint" style="margin-top: 24px; padding-top: 20px; box-shadow: inset 0 1px 0 var(--line);">
              <div class="fsp-display" style="font-size: 16px; line-height: 20px; margin-bottom: 10px;">Профильный чертёж теста</div>
              <p style="margin: 0 0 12px; font-size: 14px; color: var(--text-muted);">Теория {{ blueprint.theory }}% · практика {{ blueprint.practice }}% · отладка {{ blueprint.debug }}% · кейс {{ blueprint.case }}%</p>
              <p v-if="blueprint.note" style="margin: 0 0 12px; font-size: 13px; color: var(--text-muted);">{{ blueprint.note }}</p>
              <div v-for="item in blueprint.sample" :key="item.id" style="padding: 10px 0; box-shadow: inset 0 1px 0 var(--line); font-size: 14px;">
                <b>{{ item.title }}</b>
                <div class="u-small">{{ CAT_FORMAT_LABEL[item.format] || item.format }} · {{ item.tags.join(', ') || item.id }}</div>
              </div>
            </div>
          </aside>
        </div>
      </ScreenState>
    </main>
  </div>
</template>
