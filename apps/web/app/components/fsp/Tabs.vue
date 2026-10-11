<script setup lang="ts">
export interface TabItem { value: string; label: string; count?: number | string }
const props = defineProps<{ items: TabItem[]; defaultValue?: string }>()
const value = defineModel<string>()
if (value.value === undefined) value.value = props.defaultValue ?? props.items[0]?.value
</script>

<template>
  <div class="fsp-tabs" role="tablist">
    <button v-for="it in items" :key="it.value" type="button" role="tab" class="fsp-tab"
      :aria-selected="value === it.value" @click="value = it.value">
      {{ it.label }}<span v-if="it.count != null" class="fsp-tab-count">{{ it.count }}</span>
    </button>
  </div>
</template>
