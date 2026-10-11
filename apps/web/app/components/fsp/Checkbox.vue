<script setup lang="ts">
const props = defineProps<{ label?: string; count?: number | string; swatch?: string; defaultChecked?: boolean }>()
const checked = defineModel<boolean>()
if (checked.value === undefined) checked.value = !!props.defaultChecked
</script>

<template>
  <label class="fsp-check">
    <input v-model="checked" type="checkbox">
    <span class="fsp-check-box" aria-hidden="true"><FspIcon name="check" :stroke-width="3" /></span>
    <span v-if="swatch" class="fsp-check-swatch" :style="{ background: `var(--disc-${swatch})` }" />
    <span class="fsp-check-label">{{ label }}<slot /></span>
    <span v-if="count != null" class="fsp-check-count">{{ count }}</span>
  </label>
</template>
