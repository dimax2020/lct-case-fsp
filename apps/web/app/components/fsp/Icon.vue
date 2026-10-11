<script setup lang="ts">
const props = withDefaults(defineProps<{ name?: string; size?: number | string; strokeWidth?: number | string; label?: string }>(), {
  name: 'search', strokeWidth: 2
})

type Part = [string, Record<string, string | number>]
const P: Record<string, Part[]> = {
  search: [['circle', { cx: 10.5, cy: 10.5, r: 6.5 }], ['path', { d: 'M15.5 15.5L21 21' }]],
  pin: [['path', { d: 'M12 21s-6.5-6.4-6.5-11.2a6.5 6.5 0 0 1 13 0C18.5 14.6 12 21 12 21z' }], ['rect', { x: 10.5, y: 8.5, width: 3, height: 3 }]],
  briefcase: [['rect', { x: 3, y: 7, width: 18, height: 13 }], ['path', { d: 'M9 7V4h6v3M3 12.5h18' }]],
  clock: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M12 7v5l3.5 2' }]],
  bookmark: [['path', { d: 'M6 3h12v18l-6-4.5L6 21z' }]],
  'bookmark-fill': [['path', { d: 'M6 3h12v18l-6-4.5L6 21z', fill: 'currentColor' }]],
  'arrow-right': [['path', { d: 'M4 12h15M13 6l6 6-6 6' }]],
  check: [['path', { d: 'M5 12.5l4.5 4.5L19.5 7' }]],
  x: [['path', { d: 'M6 6l12 12M18 6L6 18' }]],
  'chevron-down': [['path', { d: 'M6 9l6 6 6-6' }]],
  filter: [['path', { d: 'M3 6h18M7 12h10M10 18h4' }]],
  user: [['rect', { x: 8, y: 4, width: 8, height: 8 }], ['path', { d: 'M4 21v-3l3-3h10l3 3v3' }]],
  bell: [['path', { d: 'M6 17v-6a6 6 0 0 1 12 0v6l2 2H4zM10 21.5h4' }]],
  remote: [['rect', { x: 3, y: 4, width: 18, height: 12 }], ['path', { d: 'M8 20h8M12 16v4' }]],
  level: [['path', { d: 'M5 20v-5M12 20V10M19 20V4' }]],
  wallet: [['rect', { x: 3, y: 6, width: 18, height: 14 }], ['path', { d: 'M15 13h3M3 10h18' }]],
  sun: [['circle', { cx: 12, cy: 12, r: 4 }], ['path', { d: 'M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4' }]],
  moon: [['path', { d: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z' }]],
  chat: [['path', { d: 'M4 5h16v11H9l-5 4z' }]],
  download: [['path', { d: 'M12 4v11M7 10l5 5 5-5M5 20h14' }]],
  edit: [['path', { d: 'M4 20h4L19 9l-4-4L4 16zM13 7l4 4' }]]
}
const parts = computed(() => P[props.name] || P.search)
const style = computed(() => (props.size ? { fontSize: typeof props.size === 'number' ? props.size + 'px' : props.size } : undefined))
</script>

<template>
  <svg class="fsp-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="strokeWidth"
    stroke-linecap="square" stroke-linejoin="miter" :aria-hidden="label ? undefined : 'true'"
    :role="label ? 'img' : undefined" :aria-label="label" :style="style">
    <component :is="p[0]" v-for="(p, i) in parts" :key="i" v-bind="p[1]" />
  </svg>
</template>
