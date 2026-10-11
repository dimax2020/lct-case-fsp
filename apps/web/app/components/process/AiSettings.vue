<script setup lang="ts">
const apiKey = ref('')
const provider = ref<'deepseek' | 'local'>('deepseek')
const hasApiKey = ref(false)
const keyHint = ref('')
const localModel = ref('qwen2.5-coder:0.5b')
const localInstalled = ref(false)
const pull = ref({ running: false, percent: null as number | null, status: '', error: '', done: false })
const message = ref('')
const messageKind = ref<'ok' | 'bad'>('ok')
const saving = ref(false)
let timer: ReturnType<typeof setInterval> | undefined

function explain(e: unknown, fallback: string) {
  if (e && typeof e === 'object' && 'data' in e) {
    const data = (e as { data?: { error?: { message?: string } } }).data
    if (data?.error?.message) return data.error.message
  }
  if (e instanceof Error && e.message && !/^\[(GET|PUT|POST)\]/.test(e.message)) return e.message
  return fallback
}

async function load() {
  const token = sessionStorage.getItem('epa.token')
  if (!token) return
  const data = await $fetch<{
    provider: 'deepseek' | 'local'
    hasApiKey: boolean
    keyHint: string
    localModel: string
    localInstalled: boolean
    pull: { running: boolean; percent: number | null; status: string; error: string; done: boolean }
  }>('/v1/ai/settings', { headers: { authorization: `Bearer ${token}` } })
  provider.value = data.provider
  hasApiKey.value = data.hasApiKey
  keyHint.value = data.keyHint
  localModel.value = data.localModel
  localInstalled.value = data.localInstalled
  pull.value = data.pull
  watchPull()
}

async function save() {
  const token = sessionStorage.getItem('epa.token')
  if (!token) return
  saving.value = true
  message.value = ''
  try {
    await $fetch('/v1/ai/settings', {
      method: 'PUT',
      headers: { authorization: `Bearer ${token}` },
      body: { apiKey: apiKey.value.trim() || undefined, provider: 'deepseek' },
    })
    apiKey.value = ''
    message.value = 'Ключ DeepSeek сохранён. Разбор идёт через DeepSeek.'
    messageKind.value = 'ok'
    await load()
  } catch (e) {
    message.value = explain(e, 'Не удалось сохранить ключ')
    messageKind.value = 'bad'
  } finally {
    saving.value = false
  }
}

async function useLocal() {
  const token = sessionStorage.getItem('epa.token')
  if (!token) return
  message.value = ''
  try {
    await $fetch('/v1/ai/settings', {
      method: 'PUT',
      headers: { authorization: `Bearer ${token}` },
      body: { provider: 'local' },
    })
    message.value = 'Разбор переключён на локальную модель.'
    messageKind.value = 'ok'
    await load()
  } catch (e) {
    message.value = explain(e, 'Локальная модель ещё не скачана')
    messageKind.value = 'bad'
  }
}

async function useDeepseek() {
  const token = sessionStorage.getItem('epa.token')
  if (!token) return
  await $fetch('/v1/ai/settings', {
    method: 'PUT',
    headers: { authorization: `Bearer ${token}` },
    body: { provider: 'deepseek' },
  })
  message.value = 'Разбор снова идёт через DeepSeek.'
  messageKind.value = 'ok'
  await load()
}

async function download() {
  const token = sessionStorage.getItem('epa.token')
  if (!token) return
  message.value = ''
  try {
    await $fetch('/v1/ai/local-model', { method: 'POST', headers: { authorization: `Bearer ${token}` } })
    await load()
  } catch (e) {
    message.value = explain(e, 'Не удалось начать скачивание')
    messageKind.value = 'bad'
  }
}

const downloadLabel = computed(() => {
  if (pull.value.running) {
    const pct = pull.value.percent == null ? '' : ` ${pull.value.percent}%`
    return `Скачивается${pct}`
  }
  if (localInstalled.value) return 'Скачана'
  return 'Скачать'
})

function watchPull() {
  if (pull.value.running && !timer) timer = setInterval(() => { void load() }, 2000)
  if (!pull.value.running && timer) {
    clearInterval(timer)
    timer = undefined
  }
}

onMounted(() => { void load().then(watchPull) })
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<template>
  <section class="fsp-plate fsp-cut" style="--cut: var(--cut-m); --fill: var(--gray-bright); --edge: var(--line-strong); --bw: 1px; padding: 24px; margin-bottom: 28px;">
    <h2 class="fsp-display" style="font-size: 22px; line-height: 26px; margin-bottom: 8px;">Модель разбора</h2>
    <p style="margin: 0 0 20px; color: var(--text-muted);">Разбор тестового задания идёт через DeepSeek. Вставьте API-ключ. Локальную модель можно скачать отдельно и переключиться на неё.</p>
    <div style="display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end;">
      <FspInput v-model="apiKey" label="API-ключ DeepSeek" type="password" autocomplete="off" :placeholder="hasApiKey ? `Сохранён ${keyHint}` : 'sk-...'" style="flex: 1; min-width: 260px;" />
      <FspButton :disabled="saving || !apiKey.trim()" @click="save">Сохранить ключ</FspButton>
      <FspButton variant="outline" :disabled="pull.running || localInstalled" @click="download">{{ downloadLabel }}</FspButton>
    </div>
    <p v-if="pull.status && pull.running" style="margin: 12px 0 0; color: var(--text-muted);">{{ pull.status }}</p>
    <p v-if="pull.error" style="margin: 12px 0 0; color: var(--danger);">{{ pull.error }}</p>
    <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px;">
      <FspButton size="sm" :variant="provider === 'deepseek' ? 'primary' : 'outline'" @click="useDeepseek">DeepSeek</FspButton>
      <FspButton size="sm" :variant="provider === 'local' ? 'primary' : 'outline'" :disabled="!localInstalled" @click="useLocal">Локальная · {{ localModel }}</FspButton>
    </div>
    <p v-if="message" :style="{ margin: '12px 0 0', color: messageKind === 'bad' ? 'var(--danger)' : 'var(--success)' }">{{ message }}</p>
  </section>
</template>
