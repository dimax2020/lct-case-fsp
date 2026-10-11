<script setup lang="ts">
const props = defineProps<{ language: string; modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()

function onInput(event: Event) {
  const target = event.target
  if (target instanceof HTMLTextAreaElement) emit('update:modelValue', target.value)
}
</script>

<template>
  <textarea
    :value="props.modelValue"
    :aria-label="props.language === 'go' ? 'Код на Go' : 'Код на Python'"
    spellcheck="false"
    autocomplete="off"
    style="box-sizing: border-box; width: 100%; min-height: 280px; margin: 0; padding: 16px; resize: vertical; border: 1px solid var(--line-strong); background: var(--plate); color: var(--on-plate); font: 14px/22px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;"
    @input="onInput"
  />
</template>
