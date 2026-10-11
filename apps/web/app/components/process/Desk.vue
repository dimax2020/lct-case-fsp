<script setup lang="ts">
import AiSettings from './AiSettings.vue'

const props = defineProps<{ role: 'employer' | 'candidate' }>()

const frame = ref<HTMLIFrameElement | null>(null)
const frameSrc = ref('')
let frameObserver: ResizeObserver | undefined
let frameTimer: ReturnType<typeof setInterval> | undefined

function fitFrame() {
  const el = frame.value
  const doc = el?.contentDocument
  if (!el || !doc?.body) return
  const next = Math.ceil(Math.max(doc.documentElement.scrollHeight, doc.body.scrollHeight))
  if (Math.abs(el.offsetHeight - next) > 2) el.style.height = `${next}px`
}

function stopFit() {
  frameObserver?.disconnect()
  frameObserver = undefined
  if (frameTimer) clearInterval(frameTimer)
  frameTimer = undefined
}

function startFit() {
  stopFit()
  const doc = frame.value?.contentDocument
  if (!doc?.body) return
  fitFrame()
  frameObserver = new ResizeObserver(() => fitFrame())
  frameObserver.observe(doc.body)
  frameTimer = setInterval(fitFrame, 800)
}

onBeforeUnmount(stopFit)
const error = ref('')
const offline = ref(false)
const down = ref(false)

function loginError(e: unknown): string {
  if (!e || typeof e !== 'object' || !('data' in e)) return ''
  const data = (e as { data?: { error?: { message?: string } } }).data
  const message = data?.error?.message
  return typeof message === 'string' ? message.trim() : ''
}

onMounted(async () => {
  const fallback = props.role === 'employer' ? 'Работодатель' : 'Кандидат'
  let name = fallback
  try {
    const me = await $fetch<{ name?: string | null }>('/api/bff/session')
    if (me.name) name = me.name
  } catch { /* the process service still accepts the cabinet fallback */ }
  sessionStorage.setItem('epa.displayName', name)
  try {
    const session = await $fetch<{ token: string; role: string }>('/v1/auth/login', {
      method: 'POST',
      body: { name, role: props.role },
    })
    sessionStorage.setItem('epa.token', session.token)
    sessionStorage.setItem('epa.role', session.role)
    const page = props.role === 'employer' ? 'employer.html' : 'candidate.html'
    frameSrc.value = `/epa/${page}${window.location.hash || ''}`
  } catch (e) {
    offline.value = true
    const message = loginError(e)
    if (message) error.value = message
    else {
      down.value = true
      error.value = 'Сервис тестовых заданий ещё не отвечает. Обновите страницу через несколько секунд.'
    }
  }
})
</script>

<template>
  <div>
    <AiSettings v-if="frameSrc && role === 'employer'" />
    <section v-if="offline" class="fsp-plate fsp-cut" style="--cut: var(--cut-m); --fill: var(--gray-bright); --edge: var(--line-strong); --bw: 1px; padding: 24px;">
      <p style="margin: 0 0 8px;">{{ error }}</p>
      <p v-if="down" style="margin: 0; color: var(--text-muted);">Он запускается вместе со стендом командой make up.</p>
    </section>
    <iframe v-if="frameSrc" ref="frame" :src="frameSrc" title="Тестовые задания" class="fsp-desk-frame" @load="startFit" />
  </div>
</template>
