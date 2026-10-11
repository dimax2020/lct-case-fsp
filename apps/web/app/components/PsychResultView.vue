<script setup lang="ts">
import { DISC_COLOR, levelColor, type PsychResult } from '~/utils/psych'

// Результат теста рабочего стиля. hr=true — вид для работодателя: сырые баллы, флаги надёжности,
// социальная желательность и выбор профиля позиции для индекса соответствия.
const props = withDefaults(defineProps<{ result: PsychResult; hr?: boolean }>(), { hr: false })
const fitId = ref('universal')
const fit = computed(() => props.result.fits.find(f => f.id === fitId.value) ?? props.result.fits[0] ?? null)
const primary = computed(() => props.result.disc_profile.primary)
</script>

<template>
  <div class="fsp-stack-24">
    <section class="fsp-stack-12">
      <div class="u-between">
        <h3 class="fsp-display u-h3" style="margin: 0;">Стиль поведения · DISC</h3>
        <span class="psy-profile">
          <i v-for="s in [...primary, ...result.disc_profile.secondary]" :key="s" :style="{ background: DISC_COLOR[s] }" aria-hidden="true" />
          {{ result.disc_profile.label }}
        </span>
      </div>
      <p class="u-note" style="margin: 0;">
        Цвет описывает стиль поведения, а не способности. Основной цвет — шкала с наибольшей суммой<template v-if="result.disc_profile.secondary.length">, вторичный — близкая к ней вторая шкала</template>.
      </p>
      <div v-for="d in result.disc" :key="d.scale" class="fsp-bar-row">
        <span><b>{{ d.color_name }} · {{ d.scale }}</b><span class="u-small" style="display: block;">{{ d.text }}</span></span>
        <div class="fsp-meter" role="img" :aria-label="`${d.color_name}: ${d.pct}%`"><span :style="{ width: d.pct + '%', background: DISC_COLOR[d.scale] }" /></div>
        <b class="u-right">{{ d.pct }}%<span v-if="hr" class="u-small" style="display: block; font-weight: 400;">{{ d.sum > 0 ? '+' : '' }}{{ d.sum }}</span></b>
      </div>
    </section>

    <section class="fsp-section fsp-stack-12">
      <h3 class="fsp-display u-h3" style="margin: 0;">Рабочие качества</h3>
      <div v-for="s in result.scales" :key="s.scale" class="fsp-bar-row">
        <span><b>{{ s.title }}</b><span class="u-small" style="display: block;">{{ s.level_title }} · {{ s.level_text }}</span></span>
        <div class="fsp-meter" role="img" :aria-label="`${s.title}: ${s.pct}%`"><span :style="{ width: s.pct + '%', background: levelColor(s.level) }" /></div>
        <b class="u-right">{{ s.pct }}%</b>
      </div>
      <div v-if="hr" class="fsp-table-wrap">
        <table class="psy-table">
          <thead><tr><th>Шкала</th><th>Утвержд.</th><th>Ситуации</th><th>Сырой</th><th>Мин–макс</th><th>%</th></tr></thead>
          <tbody>
            <tr v-for="s in result.scales" :key="s.scale"><td>{{ s.title }}</td><td>{{ s.statements }}</td><td>{{ s.situations }}</td><td>{{ s.raw }}</td><td>{{ s.min }}–{{ s.max }}</td><td>{{ s.pct }}</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="fsp-section fsp-stack-12">
      <h3 class="fsp-display u-h3" style="margin: 0;">Индекс соответствия позиции</h3>
      <template v-if="hr">
        <div class="u-row-wrap">
          <FspChip v-for="f in result.fits" :key="f.id" :selected="fitId === f.id" locked @click="fitId = f.id">{{ f.title }}</FspChip>
        </div>
        <div v-if="fit" class="u-row-center">
          <span class="fsp-display" style="font-size: 40px; line-height: 44px;">{{ fit.index }}%</span>
          <span><b>{{ fit.level_title }} соответствие</b><span class="u-small" style="display: block;">Веса: Л {{ fit.weights.leadership }} · К {{ fit.weights.teamwork }} · С {{ fit.weights.stress }} · Т {{ fit.weights.diligence }}<template v-if="fit.disc !== '—'"> · ориентир DISC: {{ fit.disc }}</template></span></span>
        </div>
        <p class="u-small" style="margin: 0;">70% и выше — высокое соответствие, 50–69% — среднее, ниже 50% — низкое. Цвет DISC в индекс не входит.</p>
      </template>
      <div v-else class="psy-fits">
        <div v-for="f in result.fits" :key="f.id" class="psy-fit">
          <span>{{ f.title }}</span><b>{{ f.index }}%</b><span class="u-small">{{ f.level_title }}</span>
        </div>
      </div>
    </section>

    <section v-if="hr" class="fsp-section fsp-stack-12">
      <h3 class="fsp-display u-h3" style="margin: 0;">Надёжность</h3>
      <p v-if="result.social_desirability" style="margin: 0;">
        Социальная желательность: <b>{{ result.social_desirability.sum }} из 20</b> ({{ result.social_desirability.pct }}%)
        — {{ result.social_desirability.flag ? 'выше порога 17, возможно приукрашивание' : 'ниже порога, флага нет' }}.
      </p>
      <p v-if="result.duration_seconds != null" class="u-note" style="margin: 0;">Время прохождения: {{ Math.round(result.duration_seconds / 60) }} мин · пропусков: {{ result.skipped?.total ?? 0 }}</p>
      <ul v-if="result.flags?.length" class="psy-flags">
        <li v-for="f in result.flags" :key="f.id">{{ f.text }}</li>
      </ul>
      <p v-else style="margin: 0;"><FspStatusBadge status="offer">Флагов надёжности нет</FspStatusBadge></p>
    </section>
  </div>
</template>

<style>
.psy-profile { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 16px; }
.psy-profile i { width: 14px; height: 14px; display: inline-block; }
.psy-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.psy-table th { text-align: left; font-weight: 600; color: var(--text-muted); padding: 8px 12px 8px 0; white-space: nowrap; }
.psy-table td { padding: 8px 12px 8px 0; box-shadow: inset 0 1px 0 var(--line); white-space: nowrap; }
.psy-fits { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 8px; }
.psy-fit { display: grid; grid-template-columns: 1fr auto; gap: 2px 12px; padding: 12px 0; box-shadow: inset 0 1px 0 var(--line); }
.psy-fit .u-small { grid-column: 1 / -1; }
.psy-flags { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 6px; color: var(--warning); }
[data-theme="light"] .psy-flags { color: var(--text); }
</style>
