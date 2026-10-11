<script setup lang="ts">
useHead({ title: 'Приглашения кандидата — Карьера ФСП' })

const links = [
  { label: 'Профиль', href: '/candidate/profile' },
  { label: 'Приглашения', href: '/candidate/invites' },
  { label: 'Грейд и тесты', href: '/candidate/grade' },
  { label: 'Вакансии', href: '/candidate/vacancy' },
  { label: 'Настройки', href: '/candidate/settings' }
]

type St = 'new' | 'review' | 'ok' | 'no' | 'resp'
interface Invite {
  id: number; company: string; about: string; title: string; when: string; salary: string; status: St
  format: string; bound: string; text: string; stack: string; contact: string; deadline: string; disc?: string; reason?: string
}
const invites = ref<Invite[]>([
  {
    id: 1, company: 'Код Сибири', about: 'финтех · 120 сотрудников', title: 'Backend-разработчик (Go)', when: 'сегодня', salary: '250 000 – 320 000 ₽', status: 'new',
    format: 'Удалённо · полный день', bound: 'Без привязки к вакансии', disc: 'algo',
    text: 'Мы перестраиваем процессинг платежей и ищем человека, который уверенно чувствует себя в конкурентном Go. Ваш результат 91 по алгоритмам и 2 место на Чемпионате России — ровно то, что нам нужно. Команда 6 человек, релиз раз в неделю.',
    stack: 'Go, PostgreSQL, Kafka', contact: 'Telegram рекрутера @kodsib_hr', deadline: '24 октября'
  },
  {
    id: 2, company: 'Полярный Бит', about: 'e-commerce · 300 сотрудников', title: 'Go-разработчик в платёжную команду', when: 'вчера', salary: '220 000 – 280 000 ₽', status: 'new',
    format: 'Гибрид · Новосибирск', bound: 'Вакансия «Go-разработчик»',
    text: 'Делаем платёжный шлюз для маркетплейса. Нравится, что вы решаете наши задания — профиль на 92% актуален. Будем рады познакомиться на коротком созвоне.',
    stack: 'Go, ClickHouse, Kafka', contact: 'Почта hr@polarbit.ru', deadline: '20 октября'
  },
  {
    id: 3, company: 'Дрон Лаб', about: 'БАС · 45 сотрудников', title: 'Разработчик телеметрии', when: '3 окт', salary: '200 000 – 240 000 ₽', status: 'review',
    format: 'Офис · Томск', bound: 'Без привязки к вакансии', disc: 'uav',
    text: 'Собираем телеметрию с беспилотников в реальном времени. Ищем бэкендера, который не боится потоков данных и протоколов.',
    stack: 'Go, gRPC, TimescaleDB', contact: 'Telegram @dronelab_team', deadline: '17 октября'
  },
  {
    id: 4, company: 'Сфера Данных', about: 'аналитика · 80 сотрудников', title: 'Backend-разработчик', when: '28 сен', salary: '230 000 – 260 000 ₽', status: 'ok',
    format: 'Удалённо', bound: 'Без привязки к вакансии',
    text: 'Приглашение принято — рекрутер свяжется с вами.', stack: 'Go, PostgreSQL', contact: 'Telegram @sfera_hr', deadline: '—'
  },
  {
    id: 5, company: 'Банк Восток', about: 'банк · 2000 сотрудников', title: 'Java-разработчик', when: '20 сен', salary: '210 000 – 250 000 ₽', status: 'no',
    format: 'Офис · Москва', bound: 'Вакансия «Java-разработчик»', reason: 'Не мой стек',
    text: 'Вы отклонили приглашение.', stack: 'Java, Spring', contact: 'скрыт', deadline: '—'
  },
  {
    id: 6, company: 'Тайга Софт', about: 'госсектор · 150 сотрудников', title: 'Go-разработчик', when: '15 сен', salary: '180 000 – 220 000 ₽', status: 'no',
    format: 'Офис · Новосибирск', bound: 'Без привязки к вакансии', reason: 'Низкая вилка',
    text: 'Вы отклонили приглашение.', stack: 'Go, Oracle', contact: 'скрыт', deadline: '—'
  },
  {
    id: 7, company: 'Северный Код', about: 'финтех · 90 сотрудников', title: 'Backend-разработчик (Go)', when: '12 окт', salary: '240 000 – 280 000 ₽', status: 'resp',
    format: 'Удалённо', bound: 'Ваш отклик на вакансию',
    text: 'Вы откликнулись на вакансию. Компания видит ваш профиль и контакты.', stack: 'Go, Redis', contact: 'Ожидаем ответа компании', deadline: '—'
  }
])

const { show } = useToast()
const tab = ref('in')
const inTab = (i: Invite, t: string) => (t === 'in' ? i.status === 'new' || i.status === 'review' : t === 'ok' ? i.status === 'ok' : t === 'no' ? i.status === 'no' : i.status === 'resp')
const tabs = computed(() => [
  { value: 'in', label: 'Входящие', count: invites.value.filter(i => inTab(i, 'in')).length },
  { value: 'ok', label: 'Принятые', count: invites.value.filter(i => inTab(i, 'ok')).length },
  { value: 'no', label: 'Отклонённые', count: invites.value.filter(i => inTab(i, 'no')).length },
  { value: 'resp', label: 'Мои отклики', count: invites.value.filter(i => inTab(i, 'resp')).length }
])
const list = computed(() => invites.value.filter(i => inTab(i, tab.value)))
const selectedId = ref(1)
const current = computed(() => invites.value.find(i => i.id === selectedId.value) ?? list.value[0])
watch(tab, () => { selectedId.value = list.value[0]?.id ?? 0; declining.value = false })

function select(i: Invite) {
  selectedId.value = i.id
  declining.value = false
  if (i.status === 'new') i.status = 'review'
}
const declining = ref(false)
const reasons = ['Не подходит вилка', 'Не мой стек', 'Неудобный формат', 'Уже нашёл работу', 'Другое']
const reason = ref('')
function accept() {
  if (!current.value) return
  current.value.status = 'ok'
  show(`Приглашение принято — ${current.value.company} увидит ваши контакты`)
}
function decline() {
  if (!current.value) return
  if (!reason.value) { show('Выберите причину — компания получит обратную связь'); return }
  current.value.status = 'no'
  current.value.reason = reason.value
  declining.value = false
  reason.value = ''
  show('Приглашение отклонено, компания получила причину')
}
const badge = (s: St) => ({ new: ['new', 'Новое'], review: ['review', 'Просмотрено'], ok: ['offer', 'Принято'], no: ['reject', 'Отклонено'], resp: ['review', 'Отклик отправлен'] } as const)[s]
const cardStyle = (on: boolean) => on
  ? '--cut: var(--cut-m); padding: 20px; display: flex; gap: 14px; text-decoration: none; color: var(--text); text-align: left; font: inherit; border: 0; cursor: pointer; width: 100%;'
  : '--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px; display: flex; gap: 14px; text-decoration: none; color: var(--text); text-align: left; font: inherit; border: 0; background: none; cursor: pointer; width: 100%;'
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Карьера" user="Алексей К." :unread="true" :links="links" />

    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px;">
      <h1 class="fsp-display" style="font-size: 40px; line-height: 44px; margin-bottom: 8px;">Приглашения</h1>
      <p style="margin: 0 0 24px; font-size: 16px; color: var(--text-muted);">Компании, которые нашли вас в категории Backend · Middle. Ваши контакты они увидят только после того, как вы примете приглашение.</p>
      <FspTabs v-model="tab" :items="tabs" />

      <div style="display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; margin-top: 24px;">
        <section aria-label="Список приглашений" style="flex: 1 1 380px; min-width: 0; display: flex; flex-direction: column; gap: 8px;">
          <p v-if="!list.length" style="margin: 0; padding: 24px 0; font-size: 15px; color: var(--text-muted);">Здесь пока пусто.</p>
          <button v-for="i in list" :key="i.id" type="button" :class="['fsp-cut', current?.id === i.id && 'fsp-active']" :style="cardStyle(current?.id === i.id)" @click="select(i)">
            <FspCompanyLogo :name="i.company" :size="48" />
            <span style="flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; align-items: flex-start;">
              <span style="display: flex; justify-content: space-between; gap: 8px; width: 100%;"><b>{{ i.title }}</b><span style="font-size: 12px; color: var(--text-muted); white-space: nowrap;">{{ i.when }}</span></span>
              <span style="font-size: 14px; color: var(--text-muted);">{{ i.company }}</span>
              <span style="font-weight: 700; font-variant-numeric: tabular-nums;">{{ i.salary }}</span>
              <FspStatusBadge :status="badge(i.status)[0]">{{ badge(i.status)[1] }}</FspStatusBadge>
            </span>
          </button>
        </section>

        <article v-if="current && list.length" style="flex: 999 1 560px; min-width: 0; padding: 4px 0 0 32px; box-shadow: inset 1px 0 0 var(--line); display: flex; flex-direction: column; gap: 24px;">
          <div style="display: flex; flex-wrap: wrap; gap: 16px; align-items: center;">
            <FspCompanyLogo :name="current.company" :size="64" />
            <div style="flex: 1; min-width: 0;">
              <h2 style="margin: 0; font-size: 24px; line-height: 32px; font-weight: 600;">{{ current.title }}</h2>
              <div style="font-size: 15px; color: var(--text-muted);">{{ current.company }} · {{ current.about }}</div>
            </div>
            <FspDisciplineBadge v-if="current.disc" :discipline="current.disc" />
          </div>

          <FspPlate>
            <div style="display: flex; flex-wrap: wrap; gap: 24px 48px; align-items: flex-end;">
              <div><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Зарплата</div><div style="font-size: 30px; line-height: 36px; font-weight: 700; font-variant-numeric: tabular-nums; margin-top: 6px;">{{ current.salary }}</div><div style="font-size: 13px; color: var(--on-plate-muted);">на руки, в месяц</div></div>
              <div style="font-size: 15px; line-height: 24px;"><div>{{ current.format }}</div><div>{{ current.bound }}</div></div>
            </div>
          </FspPlate>

          <section>
            <h3 class="fsp-display" style="font-size: 16px; line-height: 20px; margin-bottom: 10px;">Предложение</h3>
            <p style="margin: 0; font-size: 16px; line-height: 24px;">{{ current.text }}</p>
          </section>

          <section style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 16px; padding: 20px 0; box-shadow: inset 0 1px 0 var(--line), inset 0 -1px 0 var(--line);">
            <div><div style="font-size: 13px; color: var(--text-muted);">Стек</div><div style="font-weight: 600; margin-top: 4px;">{{ current.stack }}</div></div>
            <div><div style="font-size: 13px; color: var(--text-muted);">Способ связи</div><div style="font-weight: 600; margin-top: 4px;">{{ current.status === 'ok' ? current.contact : current.status === 'no' ? 'Скрыт' : 'Откроется после принятия' }}</div></div>
            <div><div style="font-size: 13px; color: var(--text-muted);">{{ current.status === 'no' ? 'Причина отказа' : 'Ответить до' }}</div><div style="font-weight: 600; margin-top: 4px;">{{ current.status === 'no' ? current.reason : current.deadline }}</div></div>
          </section>

          <div v-if="current.status === 'new' || current.status === 'review'">
            <div v-if="!declining" style="display: flex; flex-wrap: wrap; gap: 12px; align-items: center;">
              <FspButton variant="accept" icon="check" @click="accept">Принять</FspButton>
              <FspButton variant="decline" icon="x" @click="declining = true">Отклонить</FspButton>
              <span style="font-size: 13px; line-height: 18px; color: var(--text-muted); flex: 1 1 240px;">Приняв приглашение, вы откроете компании телефон и почту из профиля.</span>
            </div>
            <div v-else style="display: flex; flex-direction: column; gap: 12px;">
              <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Почему отказываетесь</div>
              <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                <FspChip v-for="r in reasons" :key="r" :selected="reason === r" locked @click="reason = r">{{ r }}</FspChip>
              </div>
              <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                <FspButton variant="decline" @click="decline">Отправить отказ</FspButton>
                <FspButton variant="ghost" @click="declining = false; reason = ''">Отмена</FspButton>
              </div>
            </div>
          </div>
          <div v-else-if="current.status === 'ok'" style="display: flex; flex-wrap: wrap; gap: 12px; align-items: center;">
            <FspStatusBadge status="offer">Вы приняли приглашение</FspStatusBadge>
            <span style="font-size: 14px; color: var(--text-muted);">Компания видит ваши контакты и скоро напишет.</span>
          </div>
        </article>
      </div>
    </main>
  </div>
</template>
