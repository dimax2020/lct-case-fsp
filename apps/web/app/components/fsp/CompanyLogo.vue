<script setup lang="ts">
const props = withDefaults(defineProps<{ name?: string; src?: string; size?: number | string }>(), { name: '?', size: 48 })
const px = computed(() => Number(props.size))
const initials = computed(() => props.name.split(/\s+/).map(w => w[0]).join('').slice(0, 2))
</script>

<template>
  <span class="fsp-logo fsp-cut" :style="{ width: px + 'px', height: px + 'px', fontSize: Math.round(px * 0.34) + 'px' }" :title="name">
    <img v-if="src" :src="src" :alt="name"><template v-else>{{ initials }}</template>
  </span>
</template>
