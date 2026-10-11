<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'
import { apiFetch, asList } from '~/utils/raw'

type Short = components['schemas']['ShortlistOut']
type Hint = components['schemas']['EmployerHint']
type Item = components['schemas']['ShortlistItemOut']

useHead({ title: 'Подборка кандидатов — Карьера ФСП' })
const route = useRoute()
const { show } = useToast()
const api = useApi()

const needId = computed(() => String(route.query.need || rememberedNeed() || ''))
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
    const [need, company] = await Promise.all([
      read(api.GET('/api/v1/needs/{id}', { params: { path: { id: needId.value } } })),
      read(api.GET('/api/v1/companies/me')),
    ])
    needTitle.value = need.title
    companyName.value = company.name
    if (!category.value && need.grades[0]) category.value = `${need.specialization}:${need.grades[0]}`
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
  if (!category.value && next.categories?.[0]) category.value = next.categories[0].id
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
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Для компаний" :user="companyName" :links="employerLinks" />
    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px;">
      <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 16px; align-items: flex-end; margin-bottom: 24px;">
        <div>
          <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">Подборка</div>
          <h1 class="fsp-display" style="font-size: 36px; line-height: 40px;">{{ needTitle }}</h1>
        </div>
        <FspButton variant="outline" size="sm" href="/employer/need">Изменить описание</FspButton>
      </div>
      <ScreenState :phase="phase" :error="error" @retry="load">
        <FspTabs v-model="tab" :items="tabs" />
        <div v-if="!needId && tab !== 'bank'" style="padding: 24px 0; color: var(--text-muted);">
          Сначала опишите потребность.
          <div style="margin-top: 12px;"><FspButton href="/employer/need">К форме</FspButton></div>
        </div>
        <template v-else>
          <section v-if="tab === 'pool' || tab === 'bank'" style="display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0;">
            <button v-for="c in shortlist?.categories ?? []" :key="c.id" type="button" :class="['fsp-cut', category === c.id && 'fsp-active']" :style="catStyle(category === c.id)" @click="category = c.id">
              <span style="display: block; font-weight: 600;">{{ c.title }}</span>
              <span style="display: block; font-size: 13px; margin-top: 4px;">{{ c.count }} кандидатов</span>
            </button>
          </section>
          <div style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
            <aside style="flex: 1 1 260px; min-width: 0; padding: 0 24px 0 0; box-shadow: inset -1px 0 0 var(--line); display: flex; flex-direction: column; gap: 22px;">
              <div class="fsp-display" style="font-size: 18px;">Уточнить</div>
              <FspCheckbox v-model="onlyFsp" label="Только с достижениями" />
              <FspChip v-for="d in discs" :key="d.id" :selected="discipline === d.id" locked @click="discipline = discipline === d.id ? '' : d.id">{{ d.label }}</FspChip>
              <FspInput v-model="minScore" label="Тест не ниже" suffix="баллов" inputmode="numeric" />
              <FspInput v-model="stackQ" label="Стек" icon="search" placeholder="Kafka, Go…" />
              <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                <FspChip v-for="f in FORMATS" :key="f" :selected="format === f" locked @click="format = format === f ? '' : f">{{ FORMAT_LABEL[f] }}</FspChip>
              </div>
              <FspCheckbox v-model="fresh" label="Активен за 30 дней" />
            </aside>
            <section style="flex: 999 1 640px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
              <section v-if="tab === 'pool'" class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--accent-mark); --bw: var(--border-card); padding: 24px;">
                <h2 class="fsp-display" style="font-size: 18px; margin-bottom: 16px;">Как сузить подборку · топ-3</h2>
                <p v-if="!hints.length" style="margin: 0; color: var(--text-muted);">Подсказок пока нет.</p>
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
                <span style="color: var(--text-muted);">Уточнения:</span>
                <span v-if="!refines.length" style="color: var(--text-muted);">нет</span>
                <button v-for="r in refines" :key="r.label" type="button" style="all: unset; cursor: pointer;" @click="r.off()"><FspTag>{{ r.label }} ×</FspTag></button>
                <span style="margin-left: auto; color: var(--text-muted);">{{ (tab === 'bank' ? bankItems.length : (shortlist?.total ?? 0)) }} в списке</span>
              </div>
              <template v-if="tab === 'bank'">
                <p v-if="!bankItems.length" style="margin: 0; padding: 32px 0; color: var(--text-muted);">В банке нет кандидатов по этим условиям.</p>
                <article v-for="c in bankItems" :key="c.id" style="padding: 24px 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start;">
                  <FspCompanyLogo :name="c.display_name" :size="48" />
                  <div style="flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px;">
                    <div style="font-size: 18px; font-weight: 600;">{{ c.display_name }}</div>
                    <div style="font-size: 14px; color: var(--text-muted);">{{ categoryLabel(c.specialization, c.grade) }}<template v-if="c.city"> · {{ c.city }}</template><template v-if="c.test_score != null"> · тест {{ c.test_score }}</template></div>
                    <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                      <FspTag v-for="skill in c.skills ?? []" :key="skill">{{ skillLabel(skill) }}</FspTag>
                      <FspTag v-if="c.has_fsp">Есть ФСП</FspTag>
                    </div>
                  </div>
                </article>
              </template>
              <template v-else>
              <p v-if="!(shortlist?.items ?? []).length" style="margin: 0; padding: 32px 0; color: var(--text-muted);">Под эти условия никто не подходит — снимите часть уточнений.</p>
              <article v-for="c in shortlist?.items ?? []" :key="c.candidate_id" style="padding: 24px 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-wrap: wrap; gap: 24px;">
                <div class="fsp-display" style="font-size: 28px; width: 48px; color: var(--text-muted);">{{ String(c.position).padStart(2, '0') }}</div>
                <div style="flex: 999 1 380px; min-width: 0; display: flex; flex-direction: column; gap: 14px;">
                  <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: center;">
                    <FspCompanyLogo :name="c.display_name" :size="48" />
                    <div>
                      <div style="font-size: 18px; font-weight: 600;">{{ c.display_name }}</div>
                      <div style="font-size: 14px; color: var(--text-muted);">{{ c.category }}<template v-if="c.experience_years != null"> · опыт {{ c.experience_years }}</template><template v-if="c.city"> · {{ c.city }}</template></div>
                    </div>
                    <FspDisciplineBadge v-if="c.fsp_badge" :discipline="c.fsp_badge.discipline">{{ c.fsp_badge.text }}</FspDisciplineBadge>
                    <FspTag v-else>Нет истории ФСП</FspTag>
                  </div>
                  <div style="display: grid; grid-template-columns: 140px 1fr 44px; gap: 12px; align-items: center; font-size: 14px;">
                    <span style="color: var(--text-muted);">Соответствие</span>
                    <div style="height: 8px; background: var(--surface-hover);"><div :style="{ width: c.match + '%', height: '8px', background: scoreColor(c.match) }" /></div>
                    <b>{{ c.match }}%</b>
                  </div>
                  <ul style="margin: 0; padding: 0 0 0 18px; display: flex; flex-direction: column; gap: 4px; font-size: 14px;">
                    <li v-for="w in (c.explanations ?? []).slice(0, 3)" :key="w">{{ w }}</li>
                  </ul>
                </div>
                <div style="flex: 1 1 200px; display: flex; flex-direction: column; gap: 8px;">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <FspStatusBadge v-if="c.invitation_status" :status="inviteTone(c.invitation_status)">{{ inviteLabel(c.invitation_status) }}</FspStatusBadge>
                    <span v-else style="font-size: 13px; color: var(--text-muted);">Контакты — после принятия</span>
                    <FspButton variant="ghost" size="sm" :icon="c.favorite ? 'bookmark-fill' : 'bookmark'" :aria-label="c.favorite ? 'Убрать из избранного' : 'В избранное'" @click="toggleSave(c)" />
                  </div>
                  <FspButton v-if="!c.invitation_status" :block="true" :href="`/employer/candidate?need=${needId}&candidate=${c.candidate_id}`">Пригласить</FspButton>
                  <FspButton :block="true" variant="ghost" size="sm" :href="`/employer/candidate?need=${needId}&candidate=${c.candidate_id}`">Открыть профиль</FspButton>
                </div>
              </article>
              </template>
            </section>
          </div>
        </template>
      </ScreenState>
    </main>
  </div>
</template>
