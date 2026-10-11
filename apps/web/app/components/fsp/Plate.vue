<script setup lang="ts">
const props = withDefaults(defineProps<{ dots?: number | boolean | string; size?: 'md' | 'xl'; as?: string }>(), { dots: 0, size: 'md', as: 'div' })
const n = computed(() => (props.dots === true ? 6 : Number(props.dots) || 0))
</script>

<template>
  <component :is="as" :class="['fsp-plate fsp-cut', size === 'xl' && 'fsp-plate-xl']">
    <span v-if="n > 0" class="fsp-plate-dots" aria-hidden="true"><i v-for="i in n" :key="i" /></span>
    <slot />
  </component>
</template>
