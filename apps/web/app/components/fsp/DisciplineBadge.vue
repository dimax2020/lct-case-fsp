<script setup lang="ts">
const props = withDefaults(defineProps<{ discipline?: string; size?: 'md' | 'lg'; full?: boolean }>(), { discipline: 'algo', size: 'md' })
const D: Record<string, { short: string; full: string }> = {
  product: { short: 'Продуктовое', full: 'Продуктовое программирование' },
  algo: { short: 'Алгоритмическое', full: 'Алгоритмическое программирование' },
  uav: { short: 'БАС', full: 'Программирование беспилотных авиационных систем' },
  robot: { short: 'Робототехника', full: 'Программирование робототехники' },
  infosec: { short: 'Инфобез', full: 'Программирование систем информационной безопасности' },
  cross: { short: 'Все дисциплины', full: 'Все дисциплины' }
}
const info = computed(() => D[props.discipline] || D.algo!)
</script>

<template>
  <span :class="['fsp-disc fsp-cut', 'fsp-disc-' + discipline, size === 'lg' && 'fsp-disc-lg']" :title="info.full">
    <slot>{{ full ? info.full : info.short }}</slot>
  </span>
</template>
