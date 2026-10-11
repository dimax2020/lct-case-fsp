<script setup lang="ts">
const props = withDefaults(defineProps<{
  variant?: 'primary' | 'plate' | 'outline' | 'ghost' | 'accept' | 'decline'
  size?: 'sm' | 'md' | 'lg'
  icon?: string
  iconRight?: string
  block?: boolean
  href?: string
  type?: 'button' | 'submit' | 'reset'
  toast?: string
  disabled?: boolean
}>(), { variant: 'primary', size: 'md', type: 'button', disabled: false })

const slots = useSlots()
const { show } = useToast()
const iconOnly = computed(() => !slots.default && (props.icon || props.iconRight))
const cls = computed(() => [
  'fsp-btn fsp-cut', 'fsp-btn-' + props.variant,
  props.size !== 'md' && 'fsp-btn-' + props.size,
  props.block && 'fsp-btn-block', iconOnly.value && 'fsp-btn-icononly',
  props.disabled && 'fsp-btn-disabled'
])
const internal = computed(() => !!props.href && props.href.startsWith('/') && !props.href.startsWith('/auth/') && !props.disabled)
function onClick(event: MouseEvent) {
  if (props.disabled) {
    event.preventDefault()
    return
  }
  if (props.toast) show(props.toast)
}
</script>

<template>
  <NuxtLink v-if="internal" :to="href!" :class="cls" @click="onClick">
    <FspIcon v-if="icon" :name="icon" /><slot /><FspIcon v-if="iconRight" :name="iconRight" />
  </NuxtLink>
  <a v-else-if="href" :href="href" :class="cls" @click="onClick">
    <FspIcon v-if="icon" :name="icon" /><slot /><FspIcon v-if="iconRight" :name="iconRight" />
  </a>
  <button v-else :type="type" :class="cls" :disabled="disabled" @click="onClick">
    <FspIcon v-if="icon" :name="icon" /><slot /><FspIcon v-if="iconRight" :name="iconRight" />
  </button>
</template>
