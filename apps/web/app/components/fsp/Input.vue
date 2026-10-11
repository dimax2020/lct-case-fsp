<script setup lang="ts">
defineOptions({ inheritAttrs: false })
const props = defineProps<{
  label?: string; hint?: string; error?: string; icon?: string; suffix?: string
  id?: string; defaultValue?: string | number
}>()
const model = defineModel<string | number>()
if (model.value === undefined && props.defaultValue !== undefined) model.value = props.defaultValue
const attrs = useAttrs()
const autoId = useId()
const fid = computed(() => props.id || autoId)
const inputAttrs = computed(() => {
  const { class: _c, style: _s, ...rest } = attrs
  return rest
})
const hintText = computed(() => props.error || props.hint)
</script>

<template>
  <div :class="['fsp-field', error && 'fsp-field-error', $attrs.class]" :style="($attrs.style as any)">
    <label v-if="label" class="fsp-field-label" :for="fid">{{ label }}</label>
    <div class="fsp-input fsp-cut">
      <FspIcon v-if="icon" :name="icon" />
      <input :id="fid" v-model="model" v-bind="inputAttrs" :aria-invalid="error ? true : undefined"
        :aria-describedby="hintText ? fid + '-h' : undefined">
      <span v-if="suffix" class="fsp-input-suffix">{{ suffix }}</span>
    </div>
    <div v-if="hintText" :id="fid + '-h'" class="fsp-field-hint">{{ hintText }}</div>
  </div>
</template>
