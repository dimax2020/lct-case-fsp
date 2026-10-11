<script setup lang="ts">
defineProps<{ phase: 'loading' | 'ready' | 'error'; error?: string }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div v-if="phase === 'loading'" aria-busy="true" style="display: flex; flex-direction: column; gap: 12px; padding: 8px 0 24px;">
    <div v-for="n in 4" :key="n" style="height: 72px; background: var(--surface-hover);" />
  </div>
  <div v-else-if="phase === 'error'" style="padding: 28px 0; display: flex; flex-direction: column; gap: 12px; align-items: flex-start;">
    <p style="margin: 0; font-size: 16px; line-height: 24px;">{{ error || 'Не удалось загрузить данные' }}</p>
    <FspButton @click="$emit('retry')">Повторить</FspButton>
  </div>
  <slot v-else />
</template>
