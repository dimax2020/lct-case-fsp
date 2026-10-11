<script setup lang="ts">
useHead({ title: 'Приглашения работодателя — Карьера ФСП' })

const links = [
  { label: 'Подборка', href: '/employer/need' },
  { label: 'Банк кандидатов', href: '/employer/pool' },
  { label: 'Приглашения', href: '/employer/invites' },
  { label: 'Вакансии', href: '#' },
  { label: 'Компания', href: '/employer/company' }
]

type St = 'new' | 'review' | 'offer' | 'reject'
interface Row {
  id: number; full: string; name: string; cat: string; role: string; salary: string; date: string; status: St
  note?: string; email?: string; phone?: string; response?: boolean
}
const rows = ref<Row[]>([
  { id: 1, full: 'Алексей Кузнецов', name: 'Алексей Кузнецов', cat: 'Backend · Middle', role: 'Backend-разработчик (Go)', salary: '250–320 тыс. ₽', date: '10.10', status: 'offer', email: 'a.kuznetsov@mail.ru', phone: '+7 913 ··· 42 18' },
  { id: 2, full: 'Мария Соколова', name: 'Мария С.', cat: 'Backend · Middle', role: 'Backend-разработчик (Go)', salary: '250–320 тыс. ₽', date: '09.10', status: 'review' },
  { id: 3, full: 'Олег Николаев', name: 'Олег Н.', cat: 'Backend · Senior', role: 'Тимлид антифрода', salary: '380–450 тыс. ₽', date: '08.10', status: 'new' },
  { id: 4, full: 'Дина Рахимова', name: 'Дина Р.', cat: 'Fullstack · Middle', role: 'Backend-разработчик (Go)', salary: '250–320 тыс. ₽', date: '05.10', status: 'reject', note: '«Не рассматриваю финтех»' },
  { id: 5, full: 'Павел Орлов', name: 'Павел Орлов', cat: 'Backend · Middle', role: 'Отклик: Go-разработчик', salary: '250–320 тыс. ₽', date: '11.10', status: 'new', response: true, email: 'p.orlov@yandex.ru', phone: '+7 923 ··· 10 77' },
  { id: 6, full: 'Ксения Белова', name: 'Ксения Белова', cat: 'Backend · Junior', role: 'Отклик: Go-разработчик', salary: '250–320 тыс. ₽', date: '10.10', status: 'review', response: true, email: 'k.belova@mail.ru', phone: '+7 913 ··· 55 02' }
])
const label: Record<St, string> = { new: 'Отправлено', review: 'Просмотрено', offer: 'Принято', reject: 'Отклонено' }
const tab = ref('all')
const invites = computed(() => rows.value.filter(r => !r.response))
const tabs = computed(() => [
  { value: 'all', label: 'Все', count: invites.value.length },
  { value: 'wait', label: 'Ждут ответа', count: invites.value.filter(r => r.status === 'new' || r.status === 'review').length },
  { value: 'ok', label: 'Принятые', count: invites.value.filter(r => r.status === 'offer').length },
  { value: 'resp', label: 'Отклики на вакансии', count: rows.value.filter(r => r.response).length }
])
const list = computed(() => {
  if (tab.value === 'resp') return rows.value.filter(r => r.response)
  if (tab.value === 'wait') return invites.value.filter(r => r.status === 'new' || r.status === 'review')
  if (tab.value === 'ok') return invites.value.filter(r => r.status === 'offer')
  return invites.value
})
const kpi = computed(() => (['new', 'review', 'offer', 'reject'] as St[]).map(s => ({ s, n: invites.value.filter(r => r.status === s).length })))

const { show } = useToast()
function remind(r: Row) { show(`Напоминание отправлено: ${r.name}`) }
function revoke(r: Row) {
  rows.value = rows.value.filter(x => x.id !== r.id)
  show('Приглашение отозвано')
}
function invitePool(r: Row) {
  r.status = 'offer'
  show(`${r.name}: приглашение на интервью отправлено`)
}
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Для компаний" user="Код Сибири" :links="links" />

    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px; display: flex; flex-direction: column; gap: 24px;">
      <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 16px; align-items: flex-end;">
        <h1 class="fsp-display" style="font-size: 40px; line-height: 44px;">Приглашения</h1>
        <FspButton size="sm" href="/employer/pool" icon="search">Найти кандидатов</FspButton>
      </div>

      <section style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 12px;">
        <div v-for="k in kpi" :key="k.s" class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px;">
          <FspStatusBadge :status="k.s">{{ label[k.s] }}</FspStatusBadge>
          <div class="fsp-display" style="font-size: 36px; line-height: 40px; margin-top: 10px;">{{ k.n }}</div>
        </div>
      </section>

      <FspTabs v-model="tab" :items="tabs" />

      <section>
        <div style="overflow-x: auto;">
          <table style="width: 100%; min-width: 980px; border-collapse: collapse; font-size: 15px;">
            <thead>
              <tr style="text-align: left; color: var(--text-muted); font-size: 12px; letter-spacing: .06em; text-transform: uppercase;">
                <th style="padding: 16px 16px 12px 0; font-weight: 600;">Кандидат</th><th style="padding: 16px 16px 12px 0; font-weight: 600;">{{ tab === 'resp' ? 'Вакансия' : 'Должность' }}</th><th style="padding: 16px 16px 12px 0; font-weight: 600;">Вилка</th><th style="padding: 16px 16px 12px 0; font-weight: 600;">{{ tab === 'resp' ? 'Получен' : 'Отправлено' }}</th><th style="padding: 16px 16px 12px 0; font-weight: 600;">Статус</th><th style="padding: 16px 0 12px; font-weight: 600;">Контакты</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!list.length" style="box-shadow: inset 0 1px 0 var(--line);"><td colspan="6" style="padding: 24px 0; color: var(--text-muted);">Здесь пока пусто.</td></tr>
              <tr v-for="r in list" :key="r.id" style="box-shadow: inset 0 1px 0 var(--line);">
                <td style="padding: 16px 16px 16px 0;"><NuxtLink to="/employer/candidate" style="display: flex; gap: 12px; align-items: center; text-decoration: none;"><FspCompanyLogo :name="r.full" :size="40" /><div><b>{{ r.name }}</b><div style="font-size: 13px; color: var(--text-muted);">{{ r.cat }}</div></div></NuxtLink></td>
                <td style="padding: 16px 16px 16px 0;">{{ r.role }}</td>
                <td style="padding: 16px 16px 16px 0; font-weight: 600; white-space: nowrap;">{{ r.salary }}</td>
                <td style="padding: 16px 16px 16px 0; color: var(--text-muted);">{{ r.date }}</td>
                <td style="padding: 16px 16px 16px 0;">
                  <FspStatusBadge :status="r.status">{{ r.response && r.status === 'new' ? 'Новый отклик' : r.response && r.status === 'offer' ? 'Приглашён на интервью' : label[r.status] }}</FspStatusBadge>
                  <div v-if="r.note" style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">{{ r.note }}</div>
                </td>
                <td style="padding: 16px 0;">
                  <template v-if="r.status === 'offer' || r.response">
                    <div style="font-size: 14px;">{{ r.email }}</div>
                    <div style="font-size: 14px;">{{ r.phone }}</div>
                    <NuxtLink v-if="r.id === 1" to="/employer/chat" class="fsp-link" style="display: inline-block; margin-top: 6px; font-size: 14px; font-weight: 600;">Открыть переписку</NuxtLink>
                    <a v-else-if="r.response && r.status !== 'offer'" href="#" class="fsp-link" style="display: inline-block; margin-top: 6px; font-size: 14px; font-weight: 600;" @click.prevent="invitePool(r)">Пригласить на интервью</a>
                  </template>
                  <template v-else-if="r.status === 'reject'"><span style="font-size: 14px; color: var(--text-muted);">Скрыты</span></template>
                  <template v-else>
                    <div style="font-size: 14px; color: var(--text-muted);">Скрыты до принятия</div>
                    <div style="display: flex; gap: 12px; margin-top: 6px; font-size: 14px;">
                      <a href="#" class="fsp-link" @click.prevent="remind(r)">Напомнить</a>
                      <a href="#" class="fsp-link" @click.prevent="revoke(r)">Отозвать</a>
                    </div>
                  </template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
  </div>
</template>
