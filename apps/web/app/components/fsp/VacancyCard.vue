<script setup lang="ts">
type TagT = string | { label: string; match?: boolean }
const props = defineProps<{
  variant?: 'card' | 'row'; active?: boolean; title?: string; company?: string; logo?: string; href?: string
  salaryFrom?: number | string; salaryTo?: number | string; currency?: string; salaryNote?: string
  city?: string; format?: string; experience?: string; tags?: TagT[]; discipline?: string; hot?: boolean
  posted?: string; status?: any; saved?: boolean
}>()
const emit = defineEmits<{ save: [boolean] }>()
const { show } = useToast()
const isSaved = ref(!!props.saved)

const fmt = (n: number | string) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
const salary = computed(() => {
  const cur = props.currency || '₽'
  if (props.salaryFrom && props.salaryTo) return `${fmt(props.salaryFrom)} – ${fmt(props.salaryTo)} ${cur}`
  if (props.salaryFrom) return `от ${fmt(props.salaryFrom)} ${cur}`
  if (props.salaryTo) return `до ${fmt(props.salaryTo)} ${cur}`
  return null
})
const tagList = computed(() => (props.tags || []).map(t => (typeof t === 'string' ? { label: t } : t)))
function toggle() {
  isSaved.value = !isSaved.value
  emit('save', isSaved.value)
  show(isSaved.value ? 'Вакансия добавлена в избранное' : 'Вакансия убрана из избранного')
}
</script>

<template>
  <article :class="['fsp-vacancy fsp-cut', variant === 'row' && 'fsp-vacancy-row', active && 'fsp-active']" :aria-current="active ? 'true' : undefined">
    <div class="fsp-vacancy-top">
      <FspDisciplineBadge v-if="discipline" :discipline="discipline" />
      <span v-if="hot" class="fsp-vacancy-hot">Горячая</span>
      <span v-if="posted" class="fsp-vacancy-posted">{{ posted }}</span>
    </div>
    <div class="fsp-vacancy-head">
      <FspCompanyLogo :name="company" :src="logo" :size="52" />
      <div style="min-width: 0; flex: 1">
        <h3 class="fsp-vacancy-title"><NuxtLink v-if="href" :to="href">{{ title }}</NuxtLink><template v-else>{{ title }}</template></h3>
        <div class="fsp-vacancy-company">{{ company }}</div>
      </div>
    </div>
    <div class="fsp-vacancy-salary">
      <template v-if="salary">{{ salary }}<span v-if="salaryNote"> {{ salaryNote }}</span></template>
      <span v-else>Зарплата по итогам собеседования</span>
    </div>
    <div class="fsp-vacancy-meta">
      <span v-if="city"><FspIcon name="pin" />{{ city }}</span>
      <span v-if="format"><FspIcon :name="format === 'Удалённо' ? 'remote' : 'briefcase'" />{{ format }}</span>
      <span v-if="experience"><FspIcon name="level" />{{ experience }}</span>
    </div>
    <div v-if="tagList.length" class="fsp-vacancy-tags">
      <FspTag v-for="t in tagList" :key="t.label" :match="t.match">{{ t.label }}</FspTag>
    </div>
    <div class="fsp-vacancy-foot">
      <FspStatusBadge v-if="status" :status="status" />
      <span v-else class="fsp-spacer" />
      <FspButton variant="ghost" :icon="isSaved ? 'bookmark-fill' : 'bookmark'"
        :aria-label="isSaved ? 'Убрать из избранного' : 'В избранное'" :aria-pressed="isSaved" @click="toggle" />
    </div>
  </article>
</template>
