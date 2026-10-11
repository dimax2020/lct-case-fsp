<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'
import { apiFetch, asList } from '~/utils/raw'

type Short = components['schemas']['ShortlistOut']
type Hint = components['schemas']['EmployerHint']
type Item = components['schemas']['ShortlistItemOut']
type Need = components['schemas']['NeedOut']

useHead({ title: 'Подборка кандидатов — Карьера ФСП' })
const route = useRoute()
const { show } = useToast()
const api = useApi()

const pickedNeed = ref('')
const needId = computed(() => String(route.query.need || pickedNeed.value || rememberedNeed() || ''))
const tab = ref('pool')
const category = ref('')
const onlyFsp = ref(false)
const discipline = ref('')
const minScore = ref<string | number>('')
const stackQ = ref('')
const format = ref('')
const fresh = ref(false)
const hintId = ref('')
const shortlist = ref<Short | null>(null)
const hints = ref<Hint[]>([])
const phase = ref<'loading' | 'ready' | 'error'>('loading')
const error = ref('')
const companyName = ref('Компания')
const needTitle = ref('Подборка')
const need = ref<Need | null>(null)
const needs = ref<Need[]>([])
let stackTimer: ReturnType<typeof setTimeout> | undefined

type BankPerson = {
  id: string
  candidate_id?: string
  display_name: string
  specialization?: string | null
  grade?: string | null
  city?: string | null
  skills?: string[]
  has_fsp?: boolean
  test_score?: number | null
}
const bankItems = ref<BankPerson[]>([])
const tabs = computed(() => [
  { value: 'pool', label: 'Подборка', count: tab.value === 'pool' ? shortlist.value?.total ?? 0 : undefined },
  { value: 'bank', label: 'Весь банк', count: tab.value === 'bank' ? bankItems.value.length : undefined },
  { value: 'favorites', label: 'Избранные', count: tab.value === 'favorites' ? shortlist.value?.total ?? 0 : undefined },
])
const refines = computed(() => {
  const rows: { label: string; off: () => void }[] = []
  if (onlyFsp.value) rows.push({ label: 'Есть ФСП', off: () => { onlyFsp.value = false } })
  if (discipline.value) rows.push({ label: discipline.value, off: () => { discipline.value = '' } })
  if (Number(minScore.value)) rows.push({ label: `Тест от ${minScore.value}`, off: () => { minScore.value = '' } })
  if (stackQ.value.trim()) rows.push({ label: stackQ.value.trim(), off: () => { stackQ.value = '' } })
  if (format.value) rows.push({ label: FORMAT_LABEL[format.value as 'remote'] || format.value, off: () => { format.value = '' } })
  if (fresh.value) rows.push({ label: 'Активен 30 дней', off: () => { fresh.value = false } })
  const hint = hints.value.find(h => h.id === hintId.value)
  if (hint) rows.push({ label: hint.title, off: () => { hintId.value = '' } })
  return rows
})

async function load() {
  if (!needId.value) {
    try {
      const needs = await read(api.GET('/api/v1/needs'))
      const first = needs[0]
      if (first) {
        rememberNeed(first.id)
        pickedNeed.value = first.id
        return
      }
    } catch {
      // The empty state below asks the employer to describe a need.
    }
    if (tab.value !== 'bank') {
      phase.value = 'ready'
      shortlist.value = null
      return
    }
    phase.value = 'loading'
    error.value = ''
    try {
      await reloadList()
      phase.value = 'ready'
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Не удалось загрузить банк'
      phase.value = 'error'
    }
    return
  }
  phase.value = 'loading'
  error.value = ''
  try {
    const [current, company, all] = await Promise.all([
      read(api.GET('/api/v1/needs/{id}', { params: { path: { id: needId.value } } })),
      read(api.GET('/api/v1/companies/me')),
      read(api.GET('/api/v1/needs')).catch(() => [] as Need[]),
    ])
    need.value = current
    needs.value = all
    needTitle.value = current.title
    companyName.value = company.name
    rememberNeed(current.id)
    hints.value = await read(api.GET('/api/v1/needs/{id}/hints', { params: { path: { id: needId.value } } }))
    await reloadList()
    phase.value = 'ready'
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось загрузить подборку'
    phase.value = 'error'
  }
}

function bankQuery() {
  const [specialization, grade] = (category.value || '').split(':')
  const query: Record<string, string | boolean> = {}
  if (specialization) query.specialization = specialization
  if (grade) query.grade = grade
  const stack = stackQ.value.trim()
  if (stack) query.stack = stack
  if (onlyFsp.value) query.fsp = true
  return query
}

async function reloadList() {
  if (tab.value === 'bank') {
    const data = await apiFetch<unknown>('/api/v1/candidates', { query: bankQuery() })
    bankItems.value = asList<BankPerson>(data).map(row => ({ ...row, id: row.id || row.candidate_id || '' }))
    return
  }
  if (!needId.value) return
  const query: Record<string, string | number | boolean> = { tab: tab.value, page: 1, page_size: 20 }
  if (tab.value === 'pool' && category.value) query.category = category.value
  if (onlyFsp.value) query.only_fsp = true
  if (discipline.value) query.fsp_discipline = discipline.value
  if (Number(minScore.value)) query.min_test_score = Number(minScore.value)
  if (stackQ.value.trim()) query.stack = stackQ.value.trim()
  if (format.value) query.format = format.value
  if (fresh.value) query.active_30d = true
  if (hintId.value) query.hint_id = hintId.value
  const next = await read(api.GET('/api/v1/needs/{id}/shortlist', {
    params: { path: { id: needId.value }, query },
  }))
  if (!category.value) {
    const first = next.categories?.find(c => c.count > 0) ?? next.categories?.[0]
    if (first && tab.value === 'pool') {
      category.value = first.id
      return reloadList()
    }
  }
  shortlist.value = next
}

function queueReload() {
  clearTimeout(stackTimer)
  stackTimer = setTimeout(() => {
    reloadList().catch(e => {
      error.value = e instanceof Error ? e.message : 'Ошибка фильтра'
      if (tab.value === 'bank') phase.value = 'error'
    })
  }, 200)
}

watch([tab, category, onlyFsp, discipline, minScore, format, fresh, hintId], () => {
  if (phase.value === 'ready') queueReload()
})
watch(stackQ, () => { if (phase.value === 'ready') queueReload() })
watch(needId, load, { immediate: false })
onMounted(load)
onBeforeUnmount(() => clearTimeout(stackTimer))

function pickNeed(id: string) {
  if (id === needId.value) return
  rememberNeed(id)
  pickedNeed.value = id
  category.value = ''
  hintId.value = ''
  navigateTo({ query: { ...route.query, need: id } })
}

const summary = computed(() => {
  const items = shortlist.value?.items ?? []
  if (!items.length) return null
  const avg = Math.round(items.reduce((sum, i) => sum + i.match, 0) / items.length)
  return {
    total: shortlist.value?.total ?? items.length,
    best: Math.max(...items.map(i => i.match)),
    avg,
    fsp: items.filter(i => i.fsp_badge).length,
    strong: items.filter(i => i.match >= 60).length,
    shown: items.length,
  }
})

function applyHint(h: Hint) {
  hintId.value = hintId.value === h.id ? '' : h.id
  show(hintId.value ? `Уточнение «${h.title}» применено` : 'Уточнение снято')
}

async function toggleSave(item: Item) {
  try {
    const next = item.favorite
      ? await read(api.DELETE('/api/v1/favorites/{candidate_id}', { params: { path: { candidate_id: item.candidate_id } } }))
      : await read(api.POST('/api/v1/favorites/{candidate_id}', { params: { path: { candidate_id: item.candidate_id } } }))
    item.favorite = next.favorite
    show(next.favorite ? `${item.display_name} — в избранном` : `${item.display_name} убран(а) из избранного`)
    if (tab.value === 'favorites') await reloadList()
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось обновить избранное')
  }
}

const catStyle = (on: boolean) => on
  ? '--cut: var(--cut-m); padding: 16px 20px; text-align: left; cursor: pointer; font: inherit; min-width: 220px; border: 0;'
  : '--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-strong); --bw: 1px; color: var(--text); padding: 16px 20px; text-align: left; cursor: pointer; font: inherit; min-width: 220px; border: 0; background: none;'
const discs = [
  { id: 'algo', label: 'Алгоритмическое' },
  { id: 'product', label: 'Продуктовое' },
  { id: 'infosec', label: 'Инфобезопасность' },
]
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Для компаний" :user="companyName" :links="employerLinks" />
    <main class="fsp-page">
      <div v-if="needs.length > 1" class="pool-needs" role="tablist" aria-label="Потребности компании">
        <button v-for="n in needs" :key="n.id" type="button" role="tab" :aria-selected="n.id === needId" :class="['fsp-cut', 'pool-need', n.id === needId && 'fsp-active']" @click="pickNeed(n.id)">
          <span class="pool-need-spec">{{ categoryLabel(n.specialization, n.grades[0]) }}</span>
          <span class="pool-need-title">{{ n.title }}</span>
        </button>
      </div>
      <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 16px; align-items: flex-end; margin-bottom: 20px;">
        <div style="min-width: 0;">
          <div class="fsp-eyebrow u-mb-8">Подборка кандидатов</div>
          <h1 class="fsp-display" style="font-size: 36px; line-height: 40px;">{{ needTitle }}</h1>
          <div v-if="need" class="pool-need-meta">
            <span>{{ need.grades.map(g => GRADE_LABEL[g as 'middle'] || g).join(' / ') }}</span>
            <span>{{ salaryRange(need.salary_from, need.salary_to) }}</span>
            <span v-if="need.city">{{ need.city }}</span>
            <span>{{ need.formats.map(f => FORMAT_LABEL[f]).join(' · ') }}</span>
          </div>
          <div v-if="need" class="u-row-wrap u-mt-12">
            <FspTag v-for="sk in need.must_skills" :key="sk" style="font-weight: 600;">{{ skillLabel(sk) }}</FspTag>
            <FspTag v-for="sk in need.nice_skills ?? []" :key="'n' + sk" style="opacity: .7;">+ {{ skillLabel(sk) }}</FspTag>
          </div>
        </div>
        <FspButton variant="outline" size="sm" href="/employer/need">Изменить описание</FspButton>
      </div>
      <ScreenState :phase="phase" :error="error" @retry="load">
        <FspTabs v-model="tab" :items="tabs" />
        <div v-if="!needId && tab !== 'bank'" style="padding: 24px 0; color: var(--text-muted);">
          Сначала опишите потребность.
          <div class="u-mt-12"><FspButton href="/employer/need">К форме</FspButton></div>
        </div>
        <template v-else>
          <section v-if="tab === 'pool' || tab === 'bank'" style="display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0;">
            <button v-for="c in shortlist?.categories ?? []" :key="c.id" type="button" :class="['fsp-cut', category === c.id && 'fsp-active']" :style="catStyle(category === c.id)" @click="category = c.id">
              <span style="display: block; font-weight: 600;">{{ c.title }}</span>
              <span style="display: block; font-size: 13px; margin-top: 4px;">{{ c.count }} кандидатов</span>
            </button>
          </section>
          <div class="fsp-columns">
            <aside style="flex: 1 1 260px; min-width: 0; padding: 0 24px 0 0; box-shadow: inset -1px 0 0 var(--line); display: flex; flex-direction: column; gap: 22px;">
              <div class="fsp-display" style="font-size: 18px;">Уточнить</div>
              <FspCheckbox v-model="onlyFsp" label="Только с достижениями" />
              <FspChip v-for="d in discs" :key="d.id" :selected="discipline === d.id" locked @click="discipline = discipline === d.id ? '' : d.id">{{ d.label }}</FspChip>
              <FspInput v-model="minScore" label="Тест не ниже" suffix="баллов" inputmode="numeric" />
              <FspInput v-model="stackQ" label="Стек" icon="search" placeholder="Kafka, Go…" />
              <div class="u-row-wrap">
                <FspChip v-for="f in FORMATS" :key="f" :selected="format === f" locked @click="format = format === f ? '' : f">{{ FORMAT_LABEL[f] }}</FspChip>
              </div>
              <FspCheckbox v-model="fresh" label="Активен за 30 дней" />
            </aside>
            <section style="flex: 999 1 640px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
              <section v-if="tab === 'pool'" class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--accent-mark); --bw: var(--border-card); padding: 24px;">
                <h2 class="fsp-display" style="font-size: 18px; margin-bottom: 16px;">Как сузить подборку · топ-3</h2>
                <p v-if="!hints.length" class="u-muted-p">Подсказок пока нет.</p>
                <div v-else style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 12px;">
                  <div v-for="(h, i) in hints.slice(0, 3)" :key="h.id" class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface-hover); padding: 18px; display: flex; flex-direction: column; gap: 8px;">
                    <span class="fsp-display" style="font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 34px; height: 24px; display: inline-grid; place-items: center;">0{{ i + 1 }}</span>
                    <b>{{ h.title }}</b>
                    <span class="fsp-display" style="font-size: 24px;">{{ h.before ?? '—' }} → {{ h.after ?? '—' }}</span>
                    <FspButton size="sm" :variant="hintId === h.id ? 'primary' : 'outline'" :icon="hintId === h.id ? 'check' : undefined" @click="applyHint(h)">{{ hintId === h.id ? 'Применено' : 'Применить' }}</FspButton>
                  </div>
                </div>
              </section>
              <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 14px;">
                <span class="u-muted">Уточнения:</span>
                <span v-if="!refines.length" class="u-muted">нет</span>
                <button v-for="r in refines" :key="r.label" type="button" class="u-unbutton" @click="r.off()"><FspTag>{{ r.label }} ×</FspTag></button>
                <span style="margin-left: auto; color: var(--text-muted);">{{ (tab === 'bank' ? bankItems.length : (shortlist?.total ?? 0)) }} в списке</span>
              </div>
              <template v-if="tab === 'bank'">
                <p v-if="!bankItems.length" style="margin: 0; padding: 32px 0; color: var(--text-muted);">В банке нет кандидатов по этим условиям.</p>
                <article v-for="c in bankItems" :key="c.id" style="padding: 24px 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start;">
                  <FspCompanyLogo :name="c.display_name" :size="48" />
                  <div style="flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px;">
                    <div class="u-lead">{{ c.display_name }}</div>
                    <div class="u-note-sm">{{ categoryLabel(c.specialization, c.grade) }}<template v-if="c.city"> · {{ c.city }}</template><template v-if="c.test_score != null"> · тест {{ c.test_score }}</template></div>
                    <div class="u-row-wrap">
                      <FspTag v-for="skill in c.skills ?? []" :key="skill">{{ skillLabel(skill) }}</FspTag>
                      <FspTag v-if="c.has_fsp">Есть ФСП</FspTag>
                    </div>
                  </div>
                  <div class="pool-bank-actions">
                    <template v-if="needId">
                      <FspButton size="sm" :block="true" :href="`/employer/candidate?need=${needId}&candidate=${c.id}`">Пригласить</FspButton>
                      <FspButton size="sm" variant="ghost" :block="true" :href="`/employer/candidate?need=${needId}&candidate=${c.id}`">Открыть профиль</FspButton>
                      <span class="u-small">Приглашение — по потребности «{{ needTitle }}»</span>
                    </template>
                    <template v-else>
                      <FspButton size="sm" variant="outline" :block="true" href="/employer/need">Описать потребность</FspButton>
                      <span class="u-small">Приглашение отправляется по описанной потребности: так кандидат видит задачу и вилку.</span>
                    </template>
                  </div>
                </article>
              </template>
              <template v-else>
              <div v-if="summary" class="pool-stats">
                <div class="pool-stat"><b class="fsp-display">{{ summary.total }}</b><span>кандидатов прошли фильтры</span></div>
                <div class="pool-stat"><b class="fsp-display" :style="{ color: scoreColor(summary.best) }">{{ summary.best }}%</b><span>лучшее совпадение</span></div>
                <div class="pool-stat"><b class="fsp-display">{{ summary.avg }}%</b><span>среднее в топ-{{ summary.shown }}</span></div>
                <div class="pool-stat"><b class="fsp-display">{{ summary.fsp }}</b><span>с достижениями ФСП</span></div>
              </div>
              <p v-if="!(shortlist?.items ?? []).length" style="margin: 0; padding: 32px 0; color: var(--text-muted);">Под эти условия никто не подходит — снимите часть уточнений.</p>
              <FspMatchCard v-for="c in shortlist?.items ?? []" :key="c.candidate_id" :item="c" :need-id="needId" :top="c.position === 1 && c.match >= 60" @save="toggleSave" />
              </template>
            </section>
          </div>
        </template>
      </ScreenState>
    </main>
  </div>
</template>

<style>
.pool-needs { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 6px; margin-bottom: 24px; scrollbar-width: thin; }
.pool-need {
  --cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-strong); --bw: 1px;
  flex: 0 0 auto; max-width: 280px; padding: 12px 16px; text-align: left; cursor: pointer; font: inherit; color: var(--text);
  display: flex; flex-direction: column; gap: 4px;
}
.pool-need:hover { --fill: var(--surface-hover); }
.pool-need.fsp-active:hover { --fill: var(--plate); }
.pool-need-spec { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .04em; }
.pool-need-title { font-size: 14px; font-weight: 600; line-height: 18px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pool-need-meta { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 10px; color: var(--text-muted); font-size: 14px; }
.pool-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.pool-stat { padding: 16px 18px; background: var(--surface); box-shadow: inset 0 0 0 1px var(--line); display: flex; flex-direction: column; gap: 4px; }
.pool-stat b { font-size: 28px; line-height: 32px; }
.pool-stat span { font-size: 13px; color: var(--text-muted); }
.pool-bank-actions { flex: 0 0 220px; display: flex; flex-direction: column; gap: 8px; }
@media (max-width: 640px) { .pool-bank-actions { flex-basis: 100%; } }
</style>
