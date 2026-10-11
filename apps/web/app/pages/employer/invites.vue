<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'

type Inv = components['schemas']['InvitationOut']

useHead({ title: 'Приглашения работодателя — Карьера ФСП' })
const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => {
  const [list, company] = await Promise.all([
    read(api.GET('/api/v1/invitations', { params: { query: { role: 'employer' } } })),
    read(api.GET('/api/v1/companies/me')),
  ])
  return { list, company }
})

const tab = ref('all')
const items = computed(() => screen.data.value?.list.items ?? [])
const waiting = (i: Inv) => i.status === 'sent' || i.status === 'viewed'
const tabs = computed(() => [
  { value: 'all', label: 'Все', count: items.value.length },
  { value: 'wait', label: 'Ждут ответа', count: items.value.filter(waiting).length },
  { value: 'ok', label: 'Принятые', count: items.value.filter(i => i.status === 'accepted').length },
])
const list = computed(() => {
  if (tab.value === 'wait') return items.value.filter(waiting)
  if (tab.value === 'ok') return items.value.filter(i => i.status === 'accepted')
  return items.value
})
const counts = computed(() => screen.data.value?.list.counts ?? {})
const kpis = ['sent', 'viewed', 'accepted', 'declined'] as const

function replace(next: Inv) {
  const rows = screen.data.value?.list.items
  if (!rows) return
  const idx = rows.findIndex(i => i.id === next.id)
  if (idx >= 0) rows[idx] = next
}

async function remind(inv: Inv) {
  try {
    replace(await read(api.POST('/api/v1/invitations/{id}/remind', { params: { path: { id: inv.id } } })))
    show(`Напоминание отправлено: ${inv.candidate_display_name}`)
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось напомнить')
  }
}

async function revoke(inv: Inv) {
  try {
    replace(await read(api.POST('/api/v1/invitations/{id}/revoke', { params: { path: { id: inv.id } } })))
    show('Приглашение отозвано')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось отозвать')
  }
}
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Для компаний" :user="screen.data.value?.company.name || 'Компания'" :links="employerLinks" />
    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px; display: flex; flex-direction: column; gap: 24px;">
      <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 16px; align-items: flex-end;">
        <h1 class="fsp-display" style="font-size: 40px; line-height: 44px;">Приглашения</h1>
        <FspButton size="sm" href="/employer/pool" icon="search">Найти кандидатов</FspButton>
      </div>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <section style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 12px;">
          <div v-for="s in kpis" :key="s" class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px;">
            <FspStatusBadge :status="inviteTone(s)">{{ inviteLabel(s) }}</FspStatusBadge>
            <div class="fsp-display" style="font-size: 36px; line-height: 40px; margin-top: 10px;">{{ counts[s] ?? 0 }}</div>
          </div>
        </section>
        <FspTabs v-model="tab" :items="tabs" />
        <div style="overflow-x: auto;">
          <table style="width: 100%; min-width: 980px; border-collapse: collapse; font-size: 15px;">
            <thead>
              <tr style="text-align: left; color: var(--text-muted); font-size: 12px; letter-spacing: .06em; text-transform: uppercase;">
                <th style="padding: 16px 16px 12px 0; font-weight: 600;">Кандидат</th>
                <th style="padding: 16px 16px 12px 0; font-weight: 600;">Должность</th>
                <th style="padding: 16px 16px 12px 0; font-weight: 600;">Вилка</th>
                <th style="padding: 16px 16px 12px 0; font-weight: 600;">Отправлено</th>
                <th style="padding: 16px 16px 12px 0; font-weight: 600;">Статус</th>
                <th style="padding: 16px 0 12px; font-weight: 600;">Контакты</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!list.length"><td colspan="6" style="padding: 24px 0; color: var(--text-muted);">Здесь пока пусто.</td></tr>
              <tr v-for="r in list" :key="r.id" style="box-shadow: inset 0 1px 0 var(--line);">
                <td style="padding: 16px 16px 16px 0;">
                  <NuxtLink :to="`/employer/candidate?need=${r.need_id}&candidate=${r.candidate_id}`" style="display: flex; gap: 12px; align-items: center; text-decoration: none; color: inherit;">
                    <FspCompanyLogo :name="r.candidate_display_name || 'Кандидат'" :size="40" />
                    <b>{{ r.candidate_display_name }}</b>
                  </NuxtLink>
                </td>
                <td style="padding: 16px 16px 16px 0;">{{ r.title }}</td>
                <td style="padding: 16px 16px 16px 0; font-weight: 600; white-space: nowrap;">{{ salaryRange(r.salary_from, r.salary_to) }}</td>
                <td style="padding: 16px 16px 16px 0; color: var(--text-muted);">{{ shortDate(r.created_at) }}</td>
                <td style="padding: 16px 16px 16px 0;"><FspStatusBadge :status="inviteTone(r.status)">{{ inviteLabel(r.status) }}</FspStatusBadge></td>
                <td style="padding: 16px 0;">
                  <template v-if="r.status === 'accepted'">
                    <div>{{ r.candidate_email || '—' }}</div>
                    <div>{{ r.candidate_phone || '—' }}</div>
                    <NuxtLink :to="`/employer/chat?invitation=${r.id}`" class="fsp-link" style="display: inline-block; margin-top: 6px; font-weight: 600;">Открыть переписку</NuxtLink>
                  </template>
                  <template v-else-if="r.status === 'sent' || r.status === 'viewed'">
                    <div style="color: var(--text-muted);">Скрыты до принятия</div>
                    <div style="display: flex; gap: 12px; margin-top: 6px;">
                      <a href="#" class="fsp-link" @click.prevent="remind(r)">Напомнить</a>
                      <a href="#" class="fsp-link" @click.prevent="revoke(r)">Отозвать</a>
                    </div>
                  </template>
                  <span v-else style="color: var(--text-muted);">Скрыты</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </ScreenState>
    </main>
  </div>
</template>
