<script setup lang="ts">
// Чип-фильтр: по клику переключается сам; v-model:selected — если нужно управлять снаружи.
const props = defineProps<{ count?: number | string; icon?: string; locked?: boolean }>()
const selected = defineModel<boolean>('selected', { default: false })
function toggle() { if (!props.locked) selected.value = !selected.value }
</script>

<template>
  <button type="button" class="fsp-chip fsp-cut" :aria-pressed="!!selected" @click="toggle">
    <FspIcon v-if="icon" :name="icon" /><slot />
    <span v-if="count != null" class="fsp-chip-count">{{ count }}</span>
  </button>
</template>
