<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'

type Inv = components['schemas']['InvitationOut']
type Reason = components['schemas']['DeclineReason']

useHead({ title: 'Приглашения кандидата — Карьера ФСП' })
const cabinetUser = useCabinetUser('Кандидат')
const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => {
  const [list, reasons] = await Promise.all([
    read(api.GET('/api/v1/invitations', { params: { query: { role: 'candidate' } } })),
    read(api.GET('/api/v1/taxonomy/decline-reasons')),
  ])
  return { list, reasons }
})

const tab = ref('in')
const selectedId = ref('')
const declining = ref(false)
const reason = ref<Reason | ''>('')

const items = computed(() => screen.data.value?.list.items ?? [])
const incoming = (i: Inv) => i.status === 'sent' || i.status === 'viewed'
const tabs = computed(() => [
  { value: 'in', label: 'Входящие', count: items.value.filter(incoming).length },
  { value: 'ok', label: 'Принятые', count: items.value.filter(i => i.status === 'accepted').length },
  { value: 'no', label: 'Отклонённые', count: items.value.filter(i => i.status === 'declined' || i.status === 'expired' || i.status === 'revoked').length },
])
const list = computed(() => items.value.filter(i => tab.value === 'in' ? incoming(i) : tab.value === 'ok' ? i.status === 'accepted' : i.status === 'declined' || i.status === 'expired' || i.status === 'revoked'))
const current = computed(() => list.value.find(i => i.id === selectedId.value) ?? list.value[0] ?? null)

watch(list, (rows) => {
  if (!rows.some(i => i.id === selectedId.value)) selectedId.value = rows[0]?.id ?? ''
}, { immediate: true })
watch(tab, () => { declining.value = false; reason.value = '' })

function replace(next: Inv) {
  const rows = screen.data.value?.list.items
  if (!rows) return
  const idx = rows.findIndex(i => i.id === next.id)
  if (idx >= 0) rows[idx] = next
}

async function select(inv: Inv) {
  selectedId.value = inv.id
  declining.value = false
  if (inv.status !== 'sent') return
  try {
    replace(await read(api.POST('/api/v1/invitations/{id}/view', { params: { path: { id: inv.id } } })))
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось отметить просмотр')
  }
}

async function accept() {
  if (!current.value) return
  try {
    let inv = current.value
    if (inv.status === 'sent') {
      inv = await read(api.POST('/api/v1/invitations/{id}/view', { params: { path: { id: inv.id } } }))
      replace(inv)
    }
    replace(await read(api.POST('/api/v1/invitations/{id}/accept', { params: { path: { id: inv.id } } })))
    show(inv.practice_title
      ? 'Приглашение принято. Можно открыть тестовое задание.'
      : 'Приглашение принято — компания видит ваши контакты')
    tab.value = 'ok'
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось принять')
  }
}

async function decline() {
  if (!current.value || !reason.value) { show('Выберите причину'); return }
  try {
    replace(await read(api.POST('/api/v1/invitations/{id}/decline', {
      params: { path: { id: current.value.id } },
      body: { reason: reason.value },
    })))
    declining.value = false
    reason.value = ''
    show('Приглашение отклонено')
    tab.value = 'no'
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось отклонить')
  }
}

const cardStyle = (on: boolean) => on
  ? '--cut: var(--cut-m); padding: 20px; display: flex; gap: 14px; text-align: left; font: inherit; border: 0; cursor: pointer; width: 100%;'
  : '--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px; display: flex; gap: 14px; text-align: left; font: inherit; border: 0; background: none; cursor: pointer; width: 100%;'
const reasonName = (id?: string | null) => screen.data.value?.reasons.find(r => r.id === id)?.name ?? id ?? '—'
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Карьера" :user="cabinetUser" :links="candidateLinks" />
    <main class="fsp-page">
      <h1 class="fsp-display fsp-title">Приглашения</h1>
      <p style="margin: 0 0 24px; font-size: 16px; color: var(--text-muted);">Откликнуться на вакансию нельзя. Вы только принимаете или отклоняете предложения компаний. Контакты открываются после принятия.</p>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <FspTabs v-model="tab" :items="tabs" />
        <div style="display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; margin-top: 24px;">
          <section style="flex: 1 1 380px; min-width: 0; display: flex; flex-direction: column; gap: 8px;">
            <p v-if="!list.length" style="margin: 0; padding: 24px 0; color: var(--text-muted);">Здесь пока пусто.</p>
            <button v-for="i in list" :key="i.id" type="button" :class="['fsp-cut', current?.id === i.id && 'fsp-active']" :style="cardStyle(current?.id === i.id)" @click="select(i)">
              <FspCompanyLogo :name="i.company_name || 'Компания'" :size="48" />
              <span style="flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; align-items: flex-start;">
                <span style="display: flex; justify-content: space-between; gap: 8px; width: 100%;"><b>{{ i.title }}</b><span style="font-size: 12px; color: var(--text-muted);">{{ whenLabel(i.created_at) }}</span></span>
                <span class="u-note-sm">{{ i.company_name }}</span>
                <span style="font-weight: 700;">{{ salaryRange(i.salary_from, i.salary_to) }}</span>
                <span v-if="i.practice_title" class="u-note-sm">Задание: {{ i.practice_title }}</span>
                <FspStatusBadge :status="inviteTone(i.status)">{{ i.status === 'sent' ? 'Новое' : inviteLabel(i.status) }}</FspStatusBadge>
              </span>
            </button>
          </section>
          <article v-if="current" style="flex: 999 1 560px; min-width: 0; padding: 4px 0 0 32px; box-shadow: inset 1px 0 0 var(--line); display: flex; flex-direction: column; gap: 24px;">
            <div>
              <h2 style="margin: 0; font-size: 24px; line-height: 32px;">{{ current.title }}</h2>
              <div style="font-size: 15px; color: var(--text-muted);">{{ current.company_name }} · {{ current.need_title }}</div>
            </div>
            <FspPlate>
              <div class="fsp-eyebrow fsp-eyebrow--plate">Зарплата</div>
              <div style="font-size: 30px; line-height: 36px; font-weight: 700; margin-top: 6px;">{{ salaryRange(current.salary_from, current.salary_to) }}</div>
            </FspPlate>
            <p style="margin: 0; font-size: 16px; line-height: 24px;">{{ current.message || 'Без текста предложения' }}</p>
            <section v-if="current.practice_title" class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px;">
              <div class="fsp-eyebrow">Тестовое задание</div>
              <div class="u-strong u-mt-4">{{ current.practice_title }}</div>
              <p class="u-note" style="margin: 8px 0 0;">{{ current.status === 'accepted' ? 'Задание уже открыто в кабинете.' : 'Откроется после принятия приглашения.' }}</p>
              <div v-if="current.status === 'accepted' && current.practice_id" style="margin-top: 12px;">
                <FspButton :href="`/candidate/process#practice=${encodeURIComponent(current.practice_id)}`">Открыть задание</FspButton>
              </div>
            </section>
            <section style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 16px; padding: 20px 0; box-shadow: inset 0 1px 0 var(--line), inset 0 -1px 0 var(--line);">
              <div><div class="u-small">Ответить до</div><div class="u-strong u-mt-4">{{ shortDate(current.deadline) }}</div></div>
              <div><div class="u-small">Связь</div><div class="u-strong u-mt-4">{{ current.status === 'accepted' ? (current.recruiter_contact || 'Контакт не указан') : 'Откроется после принятия' }}</div></div>
              <div v-if="current.status === 'declined'"><div class="u-small">Причина</div><div class="u-strong u-mt-4">{{ reasonName(current.decline_reason) }}</div></div>
            </section>
            <div v-if="current.status === 'sent' || current.status === 'viewed'">
              <div v-if="!declining" style="display: flex; flex-wrap: wrap; gap: 12px;">
                <FspButton variant="accept" icon="check" @click="accept">Принять</FspButton>
                <FspButton variant="decline" icon="x" @click="declining = true">Отклонить</FspButton>
              </div>
              <div v-else style="display: flex; flex-direction: column; gap: 12px;">
                <div class="u-row-wrap">
                  <FspChip v-for="r in screen.data.value?.reasons ?? []" :key="r.id" :selected="reason === r.id" locked @click="reason = r.id as Reason">{{ r.name }}</FspChip>
                </div>
                <div class="u-row">
                  <FspButton variant="decline" @click="decline">Отправить отказ</FspButton>
                  <FspButton variant="ghost" @click="declining = false; reason = ''">Отмена</FspButton>
                </div>
              </div>
            </div>
            <div v-else-if="current.status === 'accepted'" class="fsp-stack-12">
              <FspStatusBadge status="offer">Вы приняли приглашение</FspStatusBadge>
              <FspButton v-if="current.practice_id" variant="outline" :href="`/candidate/process#practice=${encodeURIComponent(current.practice_id)}`">Перейти к заданию</FspButton>
            </div>
          </article>
        </div>
      </ScreenState>
    </main>
  </div>
</template>
