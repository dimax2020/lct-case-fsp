<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'

type Inv = components['schemas']['InvitationOut']
type Msg = components['schemas']['MessageOut']
type Stage = components['schemas']['HiringStage']

useHead({ title: 'Переписка с кандидатом — Карьера ФСП' })
const cabinetUser = useCabinetUser('Компания')
const route = useRoute()
const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => {
  const [list, me] = await Promise.all([
    read(api.GET('/api/v1/invitations', { params: { query: { role: 'employer' } } })),
    read(api.GET('/api/v1/me')),
  ])
  return { items: list.items.filter(i => i.status === 'accepted'), me }
})

const q = ref('')
const activeId = ref(String(route.query.invitation || ''))
const messages = ref<Msg[]>([])
const draft = ref('')
const templatesOpen = ref(false)
const feed = ref<HTMLElement>()
const stage = ref<Stage | null>(null)
const closed = ref(false)
let pollTimer: ReturnType<typeof setInterval> | undefined

const dialogs = computed(() => (screen.data.value?.items ?? []).filter(d => (d.candidate_display_name || '').toLowerCase().includes(q.value.toLowerCase())))
const dlg = computed(() => dialogs.value.find(d => d.id === activeId.value) ?? dialogs.value[0] ?? null)
const mine = computed(() => screen.data.value?.me.user_id || '')
const firstName = computed(() => (dlg.value?.candidate_display_name || 'кандидат').split(' ')[0])
const stages = ['Приглашение принято', 'Интервью', 'Встреча с командой', 'Оффер']
const stageIndex = computed(() => stage.value === 'interview' ? 1 : stage.value === 'team' ? 2 : stage.value === 'offer' ? 3 : 0)
const templates = [
  'Спасибо за интерес! Предлагаю созвониться на 15 минут, когда удобно?',
  'Ссылка на встречу придёт отдельно — подключайтесь за пару минут до начала.',
  'Подготовили оффер, отправим его на почту сегодня до конца дня.',
]

watch(dlg, (inv) => {
  if (inv) void refresh(inv.id)
}, { immediate: true })

async function refresh(id: string) {
  const list = await read(api.GET('/api/v1/invitations/{id}/messages', { params: { path: { id } } }))
  messages.value = list.items ?? []
  const last = [...messages.value].reverse().find(m => m.hiring_stage)
  stage.value = last?.hiring_stage ?? null
  closed.value = stage.value === 'closed'
  await nextTick()
  feed.value?.scrollTo({ top: feed.value.scrollHeight })
}

function startPoll() {
  clearInterval(pollTimer)
  pollTimer = setInterval(() => {
    if (dlg.value) refresh(dlg.value.id).catch(() => {})
  }, 5000)
}
onMounted(startPoll)
onBeforeUnmount(() => clearInterval(pollTimer))

function open(inv: Inv) {
  activeId.value = inv.id
  draft.value = ''
  templatesOpen.value = false
}
function time(iso: string) {
  return new Date(iso).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
function mineMsg(m: Msg) {
  return m.author_user_id === mine.value
}
async function send(body = draft.value, extra: { kind?: Msg['kind']; hiring_stage?: Stage | null; slots?: { start: string; end: string }[] | null } = {}) {
  const text = body.trim()
  if (!dlg.value || (!text && extra.kind !== 'slots')) return
  try {
    await read(api.POST('/api/v1/invitations/{id}/messages', {
      params: { path: { id: dlg.value.id } },
      body: { kind: extra.kind ?? 'text', body: text, hiring_stage: extra.hiring_stage ?? null, slots: extra.slots ?? null },
    }))
    draft.value = ''
    await refresh(dlg.value.id)
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось отправить')
  }
}
function proposeTime() {
  const slots = [1, 2, 3].map((n) => {
    const start = new Date(Date.now() + n * 864e5)
    start.setHours(11, 0, 0, 0)
    const end = new Date(start.getTime() + 60 * 60 * 1000)
    return { start: start.toISOString(), end: end.toISOString() }
  })
  void send('Предлагаю время интервью', { kind: 'slots', hiring_stage: 'interview', slots })
  show('Варианты времени отправлены')
}
function offer() { void send('Оффер отправлен', { kind: 'system', hiring_stage: 'offer' }); show('Оффер отмечен') }
function closeTalk() {
  if (!dlg.value || !confirm(`Завершить процесс с кандидатом ${dlg.value.candidate_display_name}?`)) return
  void send('Процесс завершён без оффера', { kind: 'system', hiring_stage: 'closed' })
}
const itemStyle = (on: boolean) => on
  ? '--cut: var(--cut-s); padding: 14px; display: flex; gap: 12px; text-align: left; font: inherit; border: 0; cursor: pointer; width: 100%;'
  : '--cut: var(--cut-s); --fill: transparent; padding: 14px; display: flex; gap: 12px; text-align: left; font: inherit; border: 0; background: none; cursor: pointer; width: 100%;'
const dot = (i: number) => (i < stageIndex.value || stage.value === 'offer'
  ? 'width: 10px; height: 10px; background: var(--success); flex: none;'
  : i === stageIndex.value
    ? 'width: 10px; height: 10px; background: var(--warning); transform: rotate(45deg); flex: none;'
    : 'width: 10px; height: 10px; box-shadow: inset 0 0 0 1.5px var(--line-strong); flex: none;')
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Для компаний" :user="cabinetUser" :links="employerLinks" />
    <main class="fsp-page">
      <div style="display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px; margin-bottom: 24px;">
        <NuxtLink to="/employer/invites" style="font-size: 14px; color: var(--text-muted); text-decoration: none;">Приглашения</NuxtLink>
        <span class="u-muted">/</span>
        <h1 class="fsp-display u-h2">Переписка</h1>
      </div>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <p v-if="!dialogs.length" class="u-muted">Чат открывается после принятия приглашения. Таких диалогов пока нет.</p>
        <div v-else style="display: flex; flex-wrap: wrap; gap: 16px; align-items: stretch;">
          <aside style="flex: 1 1 280px; min-width: 0; padding: 0 16px 0 0; box-shadow: inset -1px 0 0 var(--line); display: flex; flex-direction: column; gap: 8px;">
            <FspInput v-model="q" icon="search" placeholder="Поиск по диалогам" aria-label="Поиск по диалогам" />
            <button v-for="d in dialogs" :key="d.id" type="button" :class="['fsp-cut', dlg?.id === d.id && 'fsp-active']" :style="itemStyle(dlg?.id === d.id)" @click="open(d)">
              <FspCompanyLogo :name="d.candidate_display_name || 'Кандидат'" :size="40" />
              <span style="flex: 1; min-width: 0;"><b>{{ d.candidate_display_name }}</b><span style="display: block; font-size: 13px; color: var(--text-muted);">{{ d.title }}</span></span>
            </button>
          </aside>
          <section v-if="dlg" class="fsp-cut" style="flex: 999 1 520px; min-width: 0; --cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); display: flex; flex-direction: column;">
            <div style="padding: 20px 24px; box-shadow: inset 0 -1px 0 var(--line);">
              <b style="font-size: 17px;">{{ dlg.candidate_display_name }}</b>
              <div class="u-small">{{ dlg.title }} · {{ salaryRange(dlg.salary_from, dlg.salary_to) }}</div>
            </div>
            <div ref="feed" style="flex: 1; padding: 24px; display: flex; flex-direction: column; gap: 16px; max-height: 640px; overflow-y: auto;">
              <template v-for="m in messages" :key="m.id">
                <div v-if="m.kind === 'system'" style="text-align: center; font-size: 13px; color: var(--text-muted);">{{ m.body }} · {{ time(m.created_at) }}</div>
                <div v-else-if="m.kind === 'slots'" style="align-self: flex-end; max-width: 78%;">
                  <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--bg); --edge: var(--line-strong); --bw: 1px; padding: 16px;">
                    <div style="font-weight: 600; margin-bottom: 8px;">Слоты</div>
                    <div class="u-row-wrap">
                      <FspTag v-for="(s, i) in m.slots ?? []" :key="i">{{ time(s.start) }}</FspTag>
                    </div>
                  </div>
                </div>
                <div v-else-if="mineMsg(m)" style="align-self: flex-end; max-width: 78%;">
                  <div class="fsp-cut" style="--cut: var(--cut-s); --fill: var(--accent-mark); color: #ffffff; padding: 12px 16px;">{{ m.body }}</div>
                  <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">{{ time(m.created_at) }}</div>
                </div>
                <div v-else style="max-width: 78%;">
                  <div class="fsp-cut" style="--cut: var(--cut-s); --fill: var(--surface-hover); padding: 12px 16px;">{{ m.body }}</div>
                  <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">{{ time(m.created_at) }}</div>
                </div>
              </template>
              <p v-if="!messages.length" class="u-muted-p">Сообщений пока нет. Новые подтягиваются каждые 5 секунд.</p>
            </div>
            <form style="padding: 16px 24px 24px; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-direction: column; gap: 12px;" @submit.prevent="send()">
              <textarea v-model="draft" rows="3" :placeholder="'Напишите ' + firstName" style="font: 400 15px/22px var(--font-sans); color: var(--text); background: var(--field); border: 1px solid var(--line-strong); padding: 12px 14px; resize: vertical;" />
              <div style="display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between;">
                <div class="u-row-wrap">
                  <FspButton variant="outline" size="sm" icon="clock" type="button" @click="proposeTime">Предложить время</FspButton>
                  <FspButton variant="ghost" size="sm" type="button" @click="templatesOpen = !templatesOpen">Шаблоны</FspButton>
                </div>
                <FspButton icon-right="arrow-right" type="submit">Отправить</FspButton>
              </div>
              <div v-if="templatesOpen" style="display: flex; flex-direction: column; gap: 8px;">
                <button v-for="t in templates" :key="t" type="button" style="all: unset; cursor: pointer; font-size: 14px;" @click="draft = t; templatesOpen = false">{{ t }}</button>
              </div>
            </form>
          </section>
          <aside v-if="dlg" style="flex: 1 1 280px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
            <div style="padding-top: 20px; box-shadow: inset 0 1px 0 var(--line);">
              <b>{{ dlg.candidate_display_name }}</b>
              <div style="font-size: 14px; margin-top: 8px;">{{ dlg.candidate_email || 'Почта скрыта' }}</div>
              <div style="font-size: 14px;">{{ dlg.candidate_phone || 'Телефон скрыт' }}</div>
              <FspButton variant="outline" size="sm" :block="true" :href="`/employer/candidate?need=${dlg.need_id}&candidate=${dlg.candidate_id}`" class="u-mt-12">Открыть профиль</FspButton>
            </div>
            <div style="padding-top: 20px; box-shadow: inset 0 1px 0 var(--line);">
              <div class="fsp-display" style="font-size: 16px; margin-bottom: 16px;">Этап найма</div>
              <ol style="list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; font-size: 14px;">
                <li v-for="(s, i) in stages" :key="s" style="display: flex; gap: 10px; align-items: center;"><span :style="dot(i)" />{{ s }}</li>
              </ol>
              <div v-if="!closed && stage !== 'offer'" style="display: flex; flex-direction: column; gap: 8px; margin-top: 20px;">
                <FspButton size="sm" variant="accept" :block="true" @click="offer">Сделать оффер</FspButton>
                <FspButton size="sm" variant="ghost" :block="true" @click="closeTalk">Завершить без оффера</FspButton>
              </div>
              <FspStatusBadge v-else-if="closed" status="reject">Завершено</FspStatusBadge>
              <FspStatusBadge v-else status="offer">Оффер</FspStatusBadge>
            </div>
          </aside>
        </div>
      </ScreenState>
    </main>
  </div>
</template>
