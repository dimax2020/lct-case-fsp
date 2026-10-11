<script setup lang="ts">
useHead({ title: 'Переписка с кандидатом — Карьера ФСП' })

const links = [
  { label: 'Подборка', href: '/employer/need' },
  { label: 'Банк кандидатов', href: '/employer/pool' },
  { label: 'Приглашения', href: '/employer/invites' },
  { label: 'Вакансии', href: '#' },
  { label: 'Компания', href: '/employer/company' }
]

type Msg =
  | { kind: 'them' | 'me'; text: string; time: string }
  | { kind: 'system'; text: string }
  | { kind: 'invite'; role: string; salary: string; format: string; date: string }
  | { kind: 'slots'; slots: string[]; picked: string; time: string }

interface Dialog {
  id: number; name: string; cat: string; via: string; preview: string; when: string; unread: boolean
  badge?: { disc: string; text: string }; email: string; phone: string; tg: string
  stage: number // 0 принято, 1 интервью, 2 команда, 3 оффер
  closed?: boolean; msgs: Msg[]
}
const dialogs = ref<Dialog[]>([
  {
    id: 1, name: 'Алексей Кузнецов', cat: 'Backend · Middle · 12 из 340', via: 'по приглашению «Backend-разработчик (Go)»', preview: 'Четверг в 15:00 подходит', when: '14:02', unread: false,
    badge: { disc: 'algo', text: 'ФСП · 2 место ЧР-2025' }, email: 'a.kuznetsov@mail.ru', phone: '+7 913 ··· 42 18', tg: '@a_kuznetsov', stage: 1,
    msgs: [
      { kind: 'invite', role: 'Backend-разработчик (Go)', salary: '250 000 – 320 000 ₽', format: 'удалённо', date: '10.10' },
      { kind: 'system', text: 'Алексей принял приглашение · контакты открыты · 10.10, 18:24' },
      { kind: 'them', text: 'Добрый вечер! Интересно, особенно антифрод. Подскажите, какой у вас процесс отбора и сколько этапов?', time: '10.10, 18:31' },
      { kind: 'me', text: 'Здравствуйте, Алексей! Два этапа: техническое интервью на час с тимлидом и финальная встреча с командой. Тестового не будет — вашего теста и результатов ФСП нам достаточно.', time: '11.10, 10:15' },
      { kind: 'slots', slots: ['Ср 15 окт, 11:00', 'Чт 16 окт, 15:00', 'Пт 17 окт, 12:00'], picked: 'Чт 16 окт, 15:00', time: '11.10, 10:16' },
      { kind: 'them', text: 'Четверг в 15:00 подходит. Ссылку пришлёте сюда?', time: '11.10, 14:02' },
      { kind: 'system', text: 'Интервью назначено на четверг, 16 октября, 15:00' }
    ]
  },
  {
    id: 2, name: 'Дмитрий Орлов', cat: 'Backend · Senior · 8 из 118', via: 'отклик на вакансию «Senior Go»', preview: 'Отклик на вакансию · Senior Go', when: 'вчера', unread: true,
    email: 'd.orlov@mail.ru', phone: '+7 905 ··· 18 40', tg: '@dorlov', stage: 0,
    msgs: [
      { kind: 'system', text: 'Дмитрий откликнулся на вакансию · контакты открыты · 10.10, 21:05' },
      { kind: 'them', text: 'Здравствуйте! Давно смотрю на ваш процессинг, 6 лет пишу на Go, последние 2 — в антифроде банка. Буду рад пообщаться.', time: '10.10, 21:07' }
    ]
  },
  {
    id: 3, name: 'Светлана Ким', cat: 'Backend · Middle · 21 из 340', via: 'по приглашению «Backend-разработчик (Go)»', preview: 'Спасибо, жду оффер', when: '7 окт', unread: false,
    badge: { disc: 'product', text: 'ФСП · финал Кубка-2024' }, email: 's.kim@mail.ru', phone: '+7 913 ··· 77 21', tg: '@svkim', stage: 2,
    msgs: [
      { kind: 'system', text: 'Встреча с командой прошла · 7.10' },
      { kind: 'me', text: 'Светлана, спасибо за встречу! Команде всё понравилось, на этой неделе вернёмся с оффером.', time: '7.10, 17:40' },
      { kind: 'them', text: 'Спасибо, жду оффер', time: '7.10, 18:02' }
    ]
  }
])

const { show } = useToast()
const activeId = ref(1)
const q = ref('')
const draft = ref('Да, пришлю ссылку на встречу за день до интервью.')
const templatesOpen = ref(false)
const feed = ref<HTMLElement>()
const dlg = computed(() => dialogs.value.find(d => d.id === activeId.value)!)
const visible = computed(() => dialogs.value.filter(d => d.name.toLowerCase().includes(q.value.toLowerCase())))
const firstName = computed(() => dlg.value.name.split(' ')[0])
const stages = computed(() => [
  'Приглашение принято · 10.10', `Техническое интервью${dlg.value.stage >= 1 ? ' · 16.10' : ''}`, 'Встреча с командой', 'Оффер'
])
const templates = [
  'Спасибо за интерес! Предлагаю созвониться на 15 минут, когда удобно?',
  'Ссылка на встречу: https://meet.kodsib.ru/interview — подключайтесь за пару минут до начала.',
  'Подготовили оффер, отправим его на почту сегодня до конца дня.'
]

function now() {
  const d = new Date()
  return `${d.getDate()}.${d.getMonth() + 1}, ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
function scrollDown(behavior: ScrollBehavior = 'smooth') { nextTick(() => feed.value?.scrollTo({ top: feed.value.scrollHeight, behavior })) }
onMounted(() => scrollDown('instant'))
watch(activeId, () => scrollDown('instant'))
function open(d: Dialog) { activeId.value = d.id; d.unread = false; draft.value = ''; templatesOpen.value = false }
function send() {
  const text = draft.value.trim()
  if (!text) return
  dlg.value.msgs.push({ kind: 'me', text, time: now() })
  dlg.value.preview = text
  dlg.value.when = 'сейчас'
  draft.value = ''
  scrollDown()
}
function proposeTime() {
  dlg.value.msgs.push({ kind: 'slots', slots: ['Пн 20 окт, 11:00', 'Вт 21 окт, 15:00', 'Ср 22 окт, 12:00'], picked: '', time: now() })
  scrollDown()
  show('Варианты времени отправлены кандидату')
}
function useTemplate(t: string) { draft.value = t; templatesOpen.value = false }
function offer() {
  dlg.value.stage = 3
  dlg.value.msgs.push({ kind: 'system', text: `Оффер отправлен · ${now()}` })
  scrollDown()
  show(`Оффер отправлен: ${dlg.value.name}`)
}
function close() {
  if (!confirm(`Завершить процесс с кандидатом ${dlg.value.name} без оффера?`)) return
  dlg.value.closed = true
  dlg.value.msgs.push({ kind: 'system', text: `Процесс завершён без оффера · ${now()}` })
  scrollDown()
}
const itemStyle = (on: boolean) => on
  ? '--cut: var(--cut-s); padding: 14px; display: flex; gap: 12px; text-decoration: none; color: var(--text); border: 0; font: inherit; text-align: left; cursor: pointer; width: 100%;'
  : '--cut: var(--cut-s); --fill: transparent; padding: 14px; display: flex; gap: 12px; text-decoration: none; color: var(--text); border: 0; background: none; font: inherit; text-align: left; cursor: pointer; width: 100%;'
const dot = (i: number) => (i < dlg.value.stage || dlg.value.stage === 3
  ? 'width: 10px; height: 10px; background: var(--success); flex: none;'
  : i === dlg.value.stage
    ? 'width: 10px; height: 10px; background: var(--warning); transform: rotate(45deg); flex: none;'
    : 'width: 10px; height: 10px; box-shadow: inset 0 0 0 1.5px var(--line-strong); flex: none;')
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Для компаний" user="Код Сибири" :unread="true" :links="links" />

    <main style="max-width: 1240px; margin: 0 auto; padding: 32px 32px 64px;">
      <div style="display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px; margin-bottom: 24px;">
        <NuxtLink to="/employer/invites" style="font-size: 14px; color: var(--text-muted); text-decoration: none;">Приглашения</NuxtLink>
        <span style="color: var(--text-muted);">/</span>
        <h1 class="fsp-display" style="font-size: 32px; line-height: 36px;">Переписка</h1>
      </div>

      <div style="display: flex; flex-wrap: wrap; gap: 16px; align-items: stretch;">

        <aside aria-label="Диалоги" style="flex: 1 1 280px; min-width: 0; padding: 0 16px 0 0; box-shadow: inset -1px 0 0 var(--line); display: flex; flex-direction: column; gap: 8px;">
          <FspInput v-model="q" icon="search" placeholder="Поиск по диалогам" aria-label="Поиск по диалогам" />
          <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin: 8px 4px 0;">Чат открывается после принятия приглашения или отклика</div>
          <button v-for="d in visible" :key="d.id" type="button" :class="['fsp-cut', d.id === activeId && 'fsp-active']" :style="itemStyle(d.id === activeId)" @click="open(d)">
            <FspCompanyLogo :name="d.name" :size="40" />
            <span style="flex: 1; min-width: 0;"><span style="display: flex; justify-content: space-between; gap: 8px;"><b>{{ d.name }}</b><span style="font-size: 12px; color: var(--text-muted);">{{ d.when }}</span></span><span style="display: block; font-size: 13px; color: var(--text-muted); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ d.preview }}</span></span>
            <span v-if="d.unread" style="width: 10px; height: 10px; border-radius: var(--radius-pill); background: var(--accent-mark); align-self: center; flex: none;" aria-label="Непрочитано" />
          </button>
          <p v-if="!visible.length" style="margin: 8px 4px; font-size: 14px; color: var(--text-muted);">Ничего не нашлось</p>
        </aside>

        <section :aria-label="'Диалог: ' + dlg.name" class="fsp-cut" style="flex: 999 1 520px; min-width: 0; --cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); display: flex; flex-direction: column;">
          <div style="padding: 20px 24px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; box-shadow: inset 0 -1px 0 var(--line);">
            <div style="flex: 1 1 240px;"><b style="font-size: 17px;">{{ dlg.name }}</b><div style="font-size: 13px; color: var(--text-muted);">{{ dlg.cat.split(' · ').slice(0, 2).join(' · ') }} · {{ dlg.via }}</div></div>
            <FspStatusBadge v-if="dlg.closed" status="reject">Завершено без оффера</FspStatusBadge>
            <FspStatusBadge v-else-if="dlg.stage === 3" status="offer">Оффер отправлен</FspStatusBadge>
            <FspStatusBadge v-else status="offer">{{ dlg.via.startsWith('отклик') ? 'Отклик' : 'Приглашение принято' }}</FspStatusBadge>
          </div>

          <div ref="feed" style="flex: 1; padding: 24px; display: flex; flex-direction: column; gap: 16px; max-height: 640px; overflow-y: auto;">
            <template v-for="(m, i) in dlg.msgs" :key="dlg.id + '-' + i">
              <div v-if="m.kind === 'invite'" class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--plate); color: var(--on-plate); padding: 16px 20px; display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: center;">
                <span style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Приглашение · {{ m.date }}</span>
                <b>{{ m.role }}</b>
                <span style="font-weight: 700; font-variant-numeric: tabular-nums;">{{ m.salary }}</span>
                <span style="color: var(--on-plate-muted); font-size: 14px;">{{ m.format }}</span>
              </div>
              <div v-else-if="m.kind === 'system'" style="text-align: center; font-size: 13px; color: var(--text-muted);">{{ m.text }}</div>
              <div v-else-if="m.kind === 'them'" style="display: flex; gap: 10px; max-width: 78%;">
                <FspCompanyLogo :name="dlg.name" :size="32" />
                <div>
                  <div class="fsp-cut" style="--cut: var(--cut-s); --fill: var(--surface-hover); padding: 12px 16px; font-size: 15px; line-height: 22px;">{{ m.text }}</div>
                  <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">{{ m.time }}</div>
                </div>
              </div>
              <div v-else-if="m.kind === 'me'" style="display: flex; flex-direction: column; align-items: flex-end; align-self: flex-end; max-width: 78%;">
                <div class="fsp-cut" style="--cut: var(--cut-s); --fill: var(--accent-mark); color: #ffffff; padding: 12px 16px; font-size: 15px; line-height: 22px; white-space: pre-wrap;">{{ m.text }}</div>
                <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Анна Морозова, HR · {{ m.time }}</div>
              </div>
              <div v-else-if="m.kind === 'slots'" style="display: flex; flex-direction: column; align-items: flex-end; align-self: flex-end; max-width: 78%;">
                <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--bg); --edge: var(--line-strong); --bw: 1px; padding: 16px 18px;">
                  <div style="display: flex; gap: 8px; align-items: center; font-weight: 600; margin-bottom: 12px;"><FspIcon name="clock" />Техническое интервью · 60 минут</div>
                  <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                    <FspChip v-for="s in m.slots" :key="s" :selected="m.picked === s" locked @click="m.picked = m.picked === s ? '' : s">{{ s }}</FspChip>
                  </div>
                </div>
                <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Предложение времени · {{ m.time }}</div>
              </div>
            </template>
          </div>

          <form style="padding: 16px 24px 24px; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-direction: column; gap: 12px;" @submit.prevent="send">
            <label style="display: flex; flex-direction: column; gap: 6px;">
              <span style="position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0);">Сообщение</span>
              <textarea v-model="draft" rows="3" :placeholder="'Напишите ' + firstName + '… (Ctrl+Enter — отправить)'" style="font: 400 15px/22px var(--font-sans); color: var(--text); background: var(--field); border: 1px solid var(--line-strong); padding: 12px 14px; resize: vertical;" @keydown.enter.ctrl.prevent="send" @keydown.enter.meta.prevent="send" />
            </label>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between;">
              <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                <FspButton variant="outline" size="sm" icon="clock" @click="proposeTime">Предложить время</FspButton>
                <span class="fsp-menu-anchor">
                  <FspButton variant="ghost" size="sm" icon="briefcase" :aria-expanded="templatesOpen" @click="templatesOpen = !templatesOpen">Шаблоны</FspButton>
                  <div v-if="templatesOpen" class="fsp-menu fsp-cut" role="menu" style="left: 0; right: auto; top: auto; bottom: calc(100% + 8px); min-width: 360px;">
                    <div class="fsp-menu-title">Шаблоны сообщений</div>
                    <button v-for="t in templates" :key="t" type="button" class="fsp-menu-item" role="menuitem" style="all: unset; padding: 10px 16px; font: 500 14px/20px var(--font-sans); cursor: pointer;" @click="useTemplate(t)">{{ t }}</button>
                  </div>
                </span>
              </div>
              <FspButton icon-right="arrow-right" type="submit">Отправить</FspButton>
            </div>
          </form>
        </section>

        <aside aria-label="Карточка кандидата" style="flex: 1 1 280px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
          <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-direction: column; gap: 16px;">
            <div style="display: flex; gap: 12px; align-items: center;">
              <FspCompanyLogo :name="dlg.name" :size="52" />
              <div><b style="font-size: 17px;">{{ dlg.name }}</b><div style="font-size: 13px; color: var(--text-muted);">{{ dlg.cat }}</div></div>
            </div>
            <FspDisciplineBadge v-if="dlg.badge" :discipline="dlg.badge.disc">{{ dlg.badge.text }}</FspDisciplineBadge>
            <div style="display: flex; flex-direction: column; gap: 8px; font-size: 14px; padding-top: 16px; box-shadow: inset 0 1px 0 var(--line);">
              <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Контакты открыты</div>
              <span>{{ dlg.email }}</span>
              <span>{{ dlg.phone }}</span>
              <span>{{ dlg.tg }}</span>
            </div>
            <FspButton variant="outline" size="sm" :block="true" href="/employer/candidate">Открыть профиль</FspButton>
          </div>

          <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <div class="fsp-display" style="font-size: 16px; line-height: 20px; margin-bottom: 16px;">Этап найма</div>
            <ol style="list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; font-size: 14px;">
              <li v-for="(s, i) in stages" :key="i" :style="{ display: 'flex', gap: '10px', alignItems: 'center', fontWeight: i === dlg.stage && dlg.stage < 3 ? 600 : 400, color: i > dlg.stage ? 'var(--text-muted)' : undefined }"><span :style="dot(i)" />{{ s }}</li>
            </ol>
            <div v-if="!dlg.closed && dlg.stage < 3" style="display: flex; flex-direction: column; gap: 8px; margin-top: 20px;">
              <FspButton size="sm" variant="accept" :block="true" @click="offer">Сделать оффер</FspButton>
              <FspButton size="sm" variant="ghost" :block="true" @click="close">Завершить без оффера</FspButton>
            </div>
          </div>
        </aside>
      </div>
    </main>
  </div>
</template>
