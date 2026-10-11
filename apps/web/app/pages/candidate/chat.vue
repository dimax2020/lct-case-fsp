<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'

type Inv = components['schemas']['InvitationOut']
type Msg = components['schemas']['MessageOut']
type Slot = components['schemas']['Slot']

useHead({ title: 'Переписка — Карьера ФСП' })
const cabinetUser = useCabinetUser('Кандидат')
const route = useRoute()
const { show } = useToast()
const api = useApi()

// Переписка открывается по принятому приглашению. Этап найма задаёт работодатель,
// кандидат видит его, отвечает и выбирает предложенный слот интервью.
const screen = useScreen(async () => {
  const [list, me] = await Promise.all([
    read(api.GET('/api/v1/invitations', { params: { query: { role: 'candidate' } } })),
    read(api.GET('/api/v1/me')),
  ])
  return { items: list.items.filter(i => i.status === 'accepted'), me }
})

const activeId = ref(String(route.query.invitation || ''))
const messages = ref<Msg[]>([])
const draft = ref('')
const sending = ref(false)
const feed = ref<HTMLElement>()
let pollTimer: ReturnType<typeof setInterval> | undefined

const dialogs = computed(() => screen.data.value?.items ?? [])
const dlg = computed(() => dialogs.value.find(d => d.id === activeId.value) ?? dialogs.value[0] ?? null)
const mine = computed(() => screen.data.value?.me.user_id || '')
const stage = computed(() => [...messages.value].reverse().find(m => m.hiring_stage)?.hiring_stage ?? null)
const stageLabel = computed(() => ({
  interview: 'Интервью',
  team: 'Встреча с командой',
  offer: 'Оффер',
  closed: 'Процесс завершён',
} as Record<string, string>)[stage.value ?? ''] ?? 'Приглашение принято')

watch(dlg, (inv) => { if (inv) void refresh(inv.id) }, { immediate: true })

async function refresh(id: string) {
  try {
    const list = await read(api.GET('/api/v1/invitations/{id}/messages', { params: { path: { id } } }))
    const grew = (list.items?.length ?? 0) !== messages.value.length
    messages.value = list.items ?? []
    if (grew) {
      await nextTick()
      feed.value?.scrollTo({ top: feed.value.scrollHeight })
    }
  } catch {
    // Следующий опрос попробует снова.
  }
}

onMounted(() => {
  pollTimer = setInterval(() => { if (dlg.value) void refresh(dlg.value.id) }, 5000)
})
onBeforeUnmount(() => clearInterval(pollTimer))

function open(inv: Inv) {
  activeId.value = inv.id
  draft.value = ''
}

function time(iso: string) {
  return new Date(iso).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

async function send(text = draft.value) {
  const body = text.trim()
  if (!dlg.value || !body || sending.value) return
  sending.value = true
  try {
    await read(api.POST('/api/v1/invitations/{id}/messages', { params: { path: { id: dlg.value.id } }, body: { kind: 'text', body } }))
    if (text === draft.value) draft.value = ''
    await refresh(dlg.value.id)
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось отправить')
  } finally {
    sending.value = false
  }
}

function pickSlot(slot: Slot) {
  void send(`Мне подходит: ${time(slot.start)}`)
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void send()
}

const itemStyle = (on: boolean) => on
  ? '--cut: var(--cut-s); padding: 14px; display: flex; gap: 12px; text-align: left; font: inherit; border: 0; cursor: pointer; width: 100%;'
  : '--cut: var(--cut-s); --fill: transparent; padding: 14px; display: flex; gap: 12px; text-align: left; font: inherit; border: 0; background: none; color: inherit; cursor: pointer; width: 100%;'
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Карьера" :user="cabinetUser" :links="candidateLinks" />
    <main class="fsp-page">
      <h1 class="fsp-display u-h2 u-mb-20">Переписка</h1>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <div v-if="!dialogs.length" class="fsp-stack-12">
          <p class="u-muted-p">Переписка открывается, когда вы принимаете приглашение работодателя. Таких приглашений пока нет.</p>
          <div><FspButton variant="outline" href="/candidate/invites">К приглашениям</FspButton></div>
        </div>
        <div v-else class="chat-layout">
          <aside class="chat-list">
            <button v-for="d in dialogs" :key="d.id" type="button" :class="['fsp-cut', dlg?.id === d.id && 'fsp-active']" :style="itemStyle(dlg?.id === d.id)" @click="open(d)">
              <FspCompanyLogo :name="d.company_name || 'Компания'" :size="40" />
              <span style="flex: 1; min-width: 0;"><b>{{ d.company_name || 'Компания' }}</b><span class="u-small" style="display: block;">{{ d.title }}</span></span>
            </button>
          </aside>
          <section v-if="dlg" class="fsp-cut chat-main">
            <div class="chat-head">
              <b style="font-size: 17px;">{{ dlg.company_name || 'Компания' }}</b>
              <div class="u-small">{{ dlg.title }} · {{ salaryRange(dlg.salary_from, dlg.salary_to) }} · {{ stageLabel }}</div>
            </div>
            <div ref="feed" class="chat-feed" aria-live="polite">
              <template v-for="m in messages" :key="m.id">
                <div v-if="m.kind === 'system'" class="u-small" style="text-align: center;">{{ m.body }} · {{ time(m.created_at) }}</div>
                <div v-else-if="m.kind === 'slots'" style="max-width: 78%;">
                  <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--bg); --edge: var(--line-strong); --bw: 1px; padding: 16px;">
                    <div class="u-strong u-mb-8">{{ m.body || 'Предлагаем время интервью' }}</div>
                    <div class="u-row-wrap">
                      <FspButton v-for="(s, i) in m.slots ?? []" :key="i" size="sm" variant="outline" icon="clock" @click="pickSlot(s)">{{ time(s.start) }}</FspButton>
                    </div>
                    <div class="u-small u-mt-6">Нажмите на удобное время — работодатель получит ответ в чате.</div>
                  </div>
                </div>
                <div v-else-if="m.author_user_id === mine" style="align-self: flex-end; max-width: 78%;">
                  <div class="fsp-cut" style="--cut: var(--cut-s); --fill: var(--accent-mark); color: #ffffff; padding: 12px 16px;">{{ m.body }}</div>
                  <div class="u-small u-mt-4 u-right">{{ time(m.created_at) }}</div>
                </div>
                <div v-else style="max-width: 78%;">
                  <div class="fsp-cut" style="--cut: var(--cut-s); --fill: var(--surface-hover); padding: 12px 16px;">{{ m.body }}</div>
                  <div class="u-small u-mt-4">{{ time(m.created_at) }}</div>
                </div>
              </template>
              <p v-if="!messages.length" class="u-muted-p">Сообщений пока нет. Можно написать первым — новые сообщения подтягиваются каждые 5 секунд.</p>
            </div>
            <form v-if="stage !== 'closed'" class="chat-form" @submit.prevent="send()">
              <textarea v-model="draft" rows="3" class="fsp-textarea" placeholder="Сообщение работодателю · Ctrl+Enter — отправить" aria-label="Сообщение" @keydown="onKey" />
              <div class="u-between">
                <span class="u-small">Ваши контакты компания уже видит — вы приняли приглашение.</span>
                <FspButton icon-right="arrow-right" type="submit" :disabled="sending">Отправить</FspButton>
              </div>
            </form>
            <p v-else class="chat-form u-muted-p">Работодатель завершил процесс. Переписка доступна только для чтения.</p>
          </section>
        </div>
      </ScreenState>
    </main>
  </div>
</template>

<style>
.chat-layout { display: flex; flex-wrap: wrap; gap: 16px; align-items: stretch; }
.chat-list { flex: 1 1 260px; min-width: 0; padding-right: 16px; box-shadow: inset -1px 0 0 var(--line); display: flex; flex-direction: column; gap: 8px; }
.chat-main { flex: 999 1 520px; min-width: 0; --cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); display: flex; flex-direction: column; }
.chat-head { padding: 20px 24px; box-shadow: inset 0 -1px 0 var(--line); }
.chat-feed { flex: 1; padding: 24px; display: flex; flex-direction: column; gap: 16px; max-height: 600px; min-height: 280px; overflow-y: auto; }
.chat-form { padding: 16px 24px 24px; margin: 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-direction: column; gap: 12px; }
@media (max-width: 640px) {
  .chat-list { padding-right: 0; box-shadow: none; }
  .chat-feed, .chat-head, .chat-form { padding-left: 16px; padding-right: 16px; }
}
</style>
