<script setup lang="ts">
import type { components } from '~/api/schema'

type Item = components['schemas']['ShortlistItemOut']

const props = defineProps<{ item: Item; needId: string; top?: boolean }>()
defineEmits<{ save: [item: Item] }>()

const R = 34
const CIRC = 2 * Math.PI * R
const dash = computed(() => `${(CIRC * Math.max(0, Math.min(100, props.item.match))) / 100} ${CIRC}`)
const tone = computed(() => scoreColor(props.item.match))
const verdict = computed(() => {
  const m = props.item.match
  if (m >= 75) return 'Сильное совпадение'
  if (m >= 50) return 'Хорошее совпадение'
  if (m >= 35) return 'Частичное совпадение'
  return 'Слабое совпадение'
})

const FACTORS: { key: keyof NonNullable<Item['factors']>; label: string }[] = [
  { key: 'skills', label: 'Навыки' },
  { key: 'experience', label: 'Опыт' },
  { key: 'grade', label: 'Грейд' },
  { key: 'tests', label: 'Тесты' },
  { key: 'fsp', label: 'ФСП' },
  { key: 'conditions', label: 'Условия' },
]
const factors = computed(() => {
  const f = props.item.factors
  return f ? FACTORS.map(row => ({ ...row, value: f[row.key] ?? 0 })) : []
})

const tested = computed(() => new Set(props.item.tested_skills ?? []))
const coverage = computed(() => props.item.must_coverage ?? [])
const extraSkills = computed(() => {
  const must = new Set(coverage.value.map(c => c.skill))
  return (props.item.skills ?? []).filter(s => !must.has(s)).slice(0, 5)
})

// «Проект: факт ↔ требование» → факт и требование отдельными строками
const reasons = computed(() => (props.item.explanations ?? []).slice(0, 3).map((line) => {
  const [fact, req] = line.split(' ↔ ')
  const m = /^(Проект|Опыт|ФСП|Резюме|Тест|GitHub|Достижение ФСП|Ежедневная задача):\s*/.exec(fact ?? '')
  const kind = m?.[1] ?? ''
  let text = m ? (fact ?? '').slice(m[0].length) : (fact ?? '')
  // «Тест: Postgresql 74/100» → название навыка из справочника
  if (kind === 'Тест') text = text.replace(/^(\S+)/, w => skillLabel(w.toLowerCase()))
  return { kind, fact: text, req: req ?? '' }
}))

const years = computed(() => {
  const y = props.item.experience_years
  if (y == null) return ''
  const n = Math.max(1, Math.round(y))
  return `опыт ${n} ${n === 1 ? 'год' : n < 5 ? 'года' : 'лет'}`
})
const href = computed(() => `/employer/candidate?need=${props.needId}&candidate=${props.item.candidate_id}`)
</script>

<template>
  <article :class="['fsp-cut', 'mc', top && 'mc-top']">
    <div class="mc-rank fsp-display">{{ String(item.position).padStart(2, '0') }}</div>

    <div class="mc-ring" :title="`Соответствие ${item.match}%`">
      <svg viewBox="0 0 80 80" width="88" height="88" aria-hidden="true">
        <circle cx="40" cy="40" :r="R" fill="none" stroke="var(--line)" stroke-width="7" />
        <circle cx="40" cy="40" :r="R" fill="none" :stroke="tone" stroke-width="7" :stroke-dasharray="dash" transform="rotate(-90 40 40)" class="mc-arc" />
      </svg>
      <div class="mc-ring-val"><b class="fsp-display">{{ item.match }}</b><span>%</span></div>
      <div class="mc-verdict" :style="{ color: tone }">{{ verdict }}</div>
    </div>

    <div class="mc-body">
      <div class="mc-head">
        <FspCompanyLogo :name="item.display_name" :size="44" />
        <div style="min-width: 0;">
          <div class="mc-name">{{ item.display_name }}</div>
          <div class="u-note-sm">{{ item.category }}<template v-if="years"> · {{ years }}</template><template v-if="item.city"> · {{ item.city }}</template><template v-if="item.test_score != null"> · тест {{ Math.round(item.test_score) }}</template></div>
        </div>
        <div class="mc-badges">
          <span v-if="top" class="mc-ribbon">Лучшее совпадение</span>
          <FspDisciplineBadge v-if="item.fsp_badge" :discipline="item.fsp_badge.discipline">{{ item.fsp_badge.text }}</FspDisciplineBadge>
        </div>
      </div>

      <div v-if="coverage.length" class="mc-cover">
        <div v-for="c in coverage" :key="c.skill" class="mc-skill" :title="`${skillLabel(c.skill)}: покрытие ${c.value}%`">
          <div class="mc-skill-top">
            <span>{{ skillLabel(c.skill) }}<FspIcon v-if="tested.has(c.skill)" name="check" :size="12" style="margin-left: 4px; color: var(--success);" /></span>
            <b>{{ c.value }}%</b>
          </div>
          <div class="mc-bar"><i :style="{ width: c.value + '%', background: scoreColor(c.value) }" /></div>
        </div>
        <FspTag v-for="s in extraSkills" :key="s">{{ skillLabel(s) }}</FspTag>
      </div>

      <ul v-if="reasons.length" class="mc-why">
        <li v-for="(r, i) in reasons" :key="i">
          <FspIcon name="check" :size="14" class="mc-why-ico" />
          <span style="min-width: 0;">
            <span class="mc-fact"><b v-if="r.kind">{{ r.kind }}.</b> {{ r.fact }}</span>
            <span v-if="r.req" class="mc-req">→ закрывает: {{ r.req }}</span>
          </span>
        </li>
      </ul>

      <div v-if="factors.length" class="mc-factors">
        <div v-for="f in factors" :key="f.key" class="mc-factor">
          <span class="u-small">{{ f.label }}</span>
          <div class="mc-bar mc-bar-thin"><i :style="{ width: f.value + '%' }" /></div>
          <span class="mc-factor-val">{{ f.value }}</span>
        </div>
      </div>
    </div>

    <div class="mc-actions">
      <div class="u-between" style="gap: 8px;">
        <FspStatusBadge v-if="item.invitation_status" :status="inviteTone(item.invitation_status)">{{ inviteLabel(item.invitation_status) }}</FspStatusBadge>
        <span v-else class="u-small">Контакты — после принятия</span>
        <FspButton variant="ghost" size="sm" :icon="item.favorite ? 'bookmark-fill' : 'bookmark'" :aria-label="item.favorite ? 'Убрать из избранного' : 'В избранное'" @click="$emit('save', item)" />
      </div>
      <FspButton v-if="!item.invitation_status" :block="true" :href="href" icon-right="arrow-right">Пригласить</FspButton>
      <FspButton :block="true" variant="outline" size="sm" :href="href">Открыть профиль</FspButton>
      <div v-if="item.formats?.length" class="u-small">{{ item.formats.map(f => FORMAT_LABEL[f as 'remote'] || f).join(' · ') }}</div>
    </div>
  </article>
</template>

<style>
.mc {
  --cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card);
  display: grid; grid-template-columns: 40px 112px minmax(0, 1fr) 220px; gap: 20px; align-items: start;
  padding: 24px; transition: transform .15s ease;
}
.mc:hover { transform: translateY(-2px); --edge: var(--line-strong); }
.mc-top { --edge: var(--accent-mark); --bw: 2px; }
.mc-rank { font-size: 24px; color: var(--text-muted); padding-top: 30px; }
.mc-ring { position: relative; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.mc-ring svg { display: block; }
.mc-arc { transition: stroke-dasharray .6s ease; stroke-linecap: butt; }
.mc-ring-val { position: absolute; top: 0; left: 0; right: 0; height: 88px; display: grid; place-items: center; grid-auto-flow: column; justify-content: center; align-items: center; gap: 1px; }
.mc-ring-val b { font-size: 28px; line-height: 1; }
.mc-ring-val span { font-size: 13px; color: var(--text-muted); align-self: center; margin-top: 6px; }
.mc-verdict { font-size: 12px; font-weight: 600; text-align: center; line-height: 16px; }
.mc-body { min-width: 0; display: flex; flex-direction: column; gap: 16px; }
.mc-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.mc-name { font-size: 18px; font-weight: 600; line-height: 24px; }
.mc-badges { margin-left: auto; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.mc-ribbon { font-family: var(--font-display); text-transform: uppercase; font-size: 11px; letter-spacing: .04em; color: #fff; background: var(--accent-mark); padding: 4px 10px; }
.mc-cover { display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center; }
.mc-skill { flex: 0 1 150px; min-width: 120px; display: flex; flex-direction: column; gap: 5px; font-size: 13px; }
.mc-skill-top { display: flex; justify-content: space-between; gap: 8px; }
.mc-bar { height: 6px; background: var(--line); position: relative; overflow: hidden; }
.mc-bar i { position: absolute; inset: 0 auto 0 0; display: block; transition: width .5s ease; }
.mc-bar-thin { height: 4px; }
.mc-bar-thin i { background: var(--primary); }
.mc-why { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; font-size: 14px; line-height: 20px; }
.mc-why li { display: flex; gap: 8px; }
.mc-why-ico { color: var(--success); margin-top: 3px; }
.mc-fact { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.mc-req { display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; color: var(--text-muted); font-size: 13px; }
.mc-factors { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px 20px; padding-top: 14px; box-shadow: inset 0 1px 0 var(--line); }
.mc-factor { display: grid; grid-template-columns: 62px 1fr 26px; gap: 8px; align-items: center; }
.mc-factor-val { font-size: 12px; text-align: right; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.mc-actions { display: flex; flex-direction: column; gap: 10px; }
@media (max-width: 960px) {
  .mc { grid-template-columns: 96px minmax(0, 1fr); }
  .mc-rank { display: none; }
  .mc-actions { grid-column: 1 / -1; }
}
@media (max-width: 640px) {
  .mc { grid-template-columns: 1fr; padding: 18px; }
  .mc-ring { flex-direction: row; align-items: center; }
  .mc-ring-val { width: 88px; right: auto; }
}
</style>
