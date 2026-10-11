<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'
import { readPracticeHash } from '~/utils/epa'

type Inv = components['schemas']['InvitationOut']

useHead({ title: 'Тестовые задания — Карьера ФСП' })
const cabinetUser = useCabinetUser('Кандидат')
const api = useApi()
const screen = useScreen(async () => ({
  list: await read(api.GET('/api/v1/invitations', { params: { query: { role: 'candidate' } } })),
}))

const hashId = ref('')
const items = computed(() => screen.data.value?.list.items ?? [])
const assigned = computed(() => items.value.filter(item => item.practice_id))
const ready = computed(() => assigned.value.filter(item => item.status === 'accepted'))
const waiting = computed(() => assigned.value.filter(item => item.status === 'sent' || item.status === 'viewed'))
const selected = computed(() =>
  ready.value.find(item => item.practice_id === hashId.value)
  ?? waiting.value.find(item => item.practice_id === hashId.value)
  ?? ready.value[0]
  ?? null,
)
const deskId = computed(() => selected.value?.status === 'accepted' ? selected.value.practice_id ?? '' : '')

function syncHash() {
  hashId.value = readPracticeHash(window.location.hash)
}

function openTask(inv: Inv) {
  if (!inv.practice_id || inv.status !== 'accepted') return
  hashId.value = inv.practice_id
  if (import.meta.client) location.hash = `practice=${encodeURIComponent(inv.practice_id)}`
}

onMounted(() => {
  syncHash()
  if (!hashId.value && ready.value.length === 1 && ready.value[0].practice_id) {
    openTask(ready.value[0])
  }
  window.addEventListener('hashchange', syncHash)
})
onBeforeUnmount(() => window.removeEventListener('hashchange', syncHash))

watch(ready, (rows) => {
  if (hashId.value || rows.length !== 1 || !rows[0].practice_id) return
  openTask(rows[0])
})

const cardStyle = (on: boolean) => on
  ? '--cut: var(--cut-m); padding: 20px; display: flex; gap: 14px; text-align: left; font: inherit; border: 0; cursor: pointer; width: 100%;'
  : '--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px; display: flex; gap: 14px; text-align: left; font: inherit; border: 0; background: none; cursor: pointer; width: 100%;'
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Карьера" :user="cabinetUser" :links="candidateLinks" />
    <main class="fsp-page">
      <h1 class="fsp-display fsp-title">Тестовые задания</h1>
      <p class="u-note" style="margin: 0 0 24px;">Задание приходит вместе с приглашением. После принятия оно открывается здесь — своя копия, не общий шаблон.</p>
      <div class="u-row-wrap" style="margin: 0 0 28px; gap: 16px;">
        <div style="display: flex; gap: 10px; align-items: flex-start; flex: 1 1 180px;">
          <span class="fsp-step-num">1</span>
          <div><div class="u-strong">Приглашение</div><div class="u-note">Компания может приложить тест</div></div>
        </div>
        <div style="display: flex; gap: 10px; align-items: flex-start; flex: 1 1 180px;">
          <span class="fsp-step-num">2</span>
          <div><div class="u-strong">Принять</div><div class="u-note">Контакты откроются компании</div></div>
        </div>
        <div style="display: flex; gap: 10px; align-items: flex-start; flex: 1 1 180px;">
          <span class="fsp-step-num">3</span>
          <div><div class="u-strong">Выполнить</div><div class="u-note">VS Code и сдача в этом кабинете</div></div>
        </div>
      </div>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <p v-if="!assigned.length" class="u-muted" style="margin: 0 0 16px;">Пока нет заданий. Они появятся, когда вы примете приглашение с тестом.</p>
        <div v-if="!assigned.length"><FspButton href="/candidate/invites">К приглашениям</FspButton></div>
        <div v-else class="fsp-columns">
          <section style="flex: 1 1 340px; min-width: 0; display: flex; flex-direction: column; gap: 8px;">
            <button
              v-for="inv in [...ready, ...waiting]"
              :key="inv.id"
              type="button"
              :class="['fsp-cut', selected?.id === inv.id && 'fsp-active']"
              :style="cardStyle(selected?.id === inv.id)"
              @click="inv.status === 'accepted' ? openTask(inv) : navigateTo('/candidate/invites')"
            >
              <FspCompanyLogo :name="inv.company_name || 'Компания'" :size="48" />
              <span style="flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; align-items: flex-start;">
                <b>{{ inv.practice_title }}</b>
                <span class="u-note-sm">{{ inv.company_name }} · {{ inv.title }}</span>
                <FspStatusBadge :status="inviteTone(inv.status)">{{ inv.status === 'accepted' ? 'Можно выполнять' : 'Откроется после принятия' }}</FspStatusBadge>
              </span>
            </button>
          </section>
          <article style="flex: 999 1 640px; min-width: 0;">
            <section v-if="selected && selected.status !== 'accepted'" class="fsp-cut fsp-card">
              <div class="fsp-eyebrow">Ещё не открыто</div>
              <h2 class="fsp-display u-h3" style="margin-top: 8px;">{{ selected.practice_title }}</h2>
              <p class="u-note" style="margin: 8px 0 16px;">Примите приглашение «{{ selected.title }}» — задание появится сразу.</p>
              <FspButton href="/candidate/invites">Открыть приглашение</FspButton>
            </section>
            <ProcessDesk v-else-if="deskId" :key="deskId" role="candidate" :practice-id="deskId" />
          </article>
        </div>
      </ScreenState>
    </main>
  </div>
</template>
