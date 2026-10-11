<script setup lang="ts">
useHead({ title: 'Настройки и приватность — Карьера ФСП' })

const v = reactive((() => {
  return {
      yes: true,
      links: [
        { label: 'Профиль', href: '/candidate/profile' },
        { label: 'Приглашения', href: '/candidate/invites' },
        { label: 'Грейд и тесты', href: '/candidate/grade' },
        { label: 'Вакансии', href: '/candidate/vacancy' },
        { label: 'Настройки', href: '/candidate/settings', active: true }
      ]
    };
})())

const { show } = useToast()
const section = ref('privacy')
const sections = [
  { id: 'privacy', label: 'Приватность' }, { id: 'fspid', label: 'ФСП ID' },
  { id: 'consent', label: 'Согласия' }, { id: 'account', label: 'Аккаунт' }
]
const navStyle = (on: boolean) => on
  ? 'padding: 12px 16px; font-weight: 600; text-decoration: none; color: var(--text); box-shadow: inset 3px 0 0 var(--accent-mark); background: var(--surface-hover);'
  : 'padding: 12px 16px; text-decoration: none; color: var(--text-muted);'
const hideQuery = ref('')
const hidden = ref<string[]>(['Сибирь Телеком'])
function addHidden() {
  const q = hideQuery.value.trim()
  if (!q) return
  if (!hidden.value.includes(q)) hidden.value.push(q)
  hideQuery.value = ''
}
const fspLinked = ref(true)
const published = ref(true)
function toggleFsp() {
  fspLinked.value = !fspLinked.value
  show(fspLinked.value ? 'ФСП ID привязан — достижения подтянуты' : 'ФСП ID отвязан, достижения скрыты из профиля')
}
function togglePublish() {
  published.value = !published.value
  show(published.value ? 'Профиль снова виден работодателям' : 'Профиль скрыт из подборок')
}
function removeAccount() {
  if (confirm('Удалить аккаунт? Профиль, тесты и приглашения будут удалены без возможности восстановления.')) {
    show('Аккаунт удалён')
    navigateTo('/')
  }
}
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Карьера" user="Алексей К." :unread="v.yes" :links="v.links" logo-dark="/brand/championship-logo-white.svg" logo-light="/brand/championship-logo-navy.svg" />

    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px;">
      <h1 class="fsp-display" style="font-size: 40px; line-height: 44px; margin-bottom: 32px;">Настройки</h1>
      <div style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
        <nav aria-label="Разделы настроек" style="flex: 1 1 220px; display: flex; flex-direction: column; gap: 4px;">
          <a v-for="sct in sections" :key="sct.id" :href="'#' + sct.id" :style="navStyle(section === sct.id)" @click="section = sct.id">{{ sct.label }}</a>
        </nav>

        <div style="flex: 999 1 640px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
          <section id="privacy" style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 8px;">Что видит работодатель</h2>
            <p style="margin: 0 0 20px; font-size: 14px; line-height: 20px; color: var(--text-muted);">Категория, грейд и результаты тестов видны всегда — по ним вас находят. Остальное — на ваше усмотрение.</p>
            <div style="display: flex; flex-direction: column; gap: 4px;">
              <FspCheckbox label="Показывать профиль в банке кандидатов" :default-checked="v.yes" />
              <FspCheckbox label="Полное имя (иначе — «Алексей К.»)" />
              <FspCheckbox label="Текущее место работы" :default-checked="v.yes" />
              <FspCheckbox label="Достижения ФСП" :default-checked="v.yes" />
              <FspCheckbox label="Стандартизированный PDF-профиль" :default-checked="v.yes" />
            </div>
            <div class="fsp-cut" style="--cut: var(--cut-s); --fill: var(--surface-hover); padding: 16px 20px; margin-top: 20px; display: flex; gap: 12px; align-items: flex-start; font-size: 14px; line-height: 20px;">
              <FspIcon name="user" />
              <span>Телефон и почта скрыты от всех работодателей. Компания увидит их, только если вы примете её приглашение или откликнетесь сами.</span>
            </div>
            <div style="margin-top: 20px;">
              <form @submit.prevent="addHidden">
                <FspInput v-model="hideQuery" label="Скрыть профиль от компаний" icon="search" placeholder="Например, текущий работодатель — Enter, чтобы добавить" />
              </form>
              <div v-if="hidden.length" style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px;">
                <FspChip v-for="h in hidden" :key="h" :selected="true" locked icon="x" :aria-label="'Убрать ' + h" @click="hidden = hidden.filter(x => x !== h)">{{ h }}</FspChip>
              </div>
            </div>
          </section>

          <section id="fspid" style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <div style="display: flex; flex-wrap: wrap; gap: 20px; align-items: center;">
              <img src="/brand/fsp-star-dark.svg" alt="" aria-hidden="true" style="width: 56px; height: 56px;">
              <div style="flex: 1 1 280px; min-width: 0;">
                <h2 class="fsp-display" style="font-size: 20px; line-height: 24px;">ФСП ID</h2>
                <div style="margin-top: 6px;"><FspStatusBadge v-if="fspLinked" status="new">Связан · ID 0482-1193</FspStatusBadge><FspStatusBadge v-else status="archived">Не привязан</FspStatusBadge></div>
                <div style="font-size: 14px; line-height: 20px; color: var(--text-muted); margin-top: 8px;">{{ fspLinked ? 'Подтянуто 2 достижения и разряд КМС. Данные обновляются раз в сутки.' : 'Привяжите ФСП ID, чтобы результаты соревнований поднимали вас в выдаче.' }}</div>
              </div>
              <div style="display: flex; gap: 8px;">
                <FspButton v-if="fspLinked" size="sm" variant="outline" toast="Данные ФСП обновлены — новых результатов нет">Обновить</FspButton>
                <FspButton size="sm" :variant="fspLinked ? 'ghost' : 'primary'" @click="toggleFsp">{{ fspLinked ? 'Отвязать' : 'Привязать ФСП ID' }}</FspButton>
              </div>
            </div>
          </section>

          <section id="consent" style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 20px;">Согласия</h2>
            <div style="display: flex; flex-direction: column; gap: 16px;">
              <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; padding-bottom: 16px; box-shadow: inset 0 -1px 0 var(--line);">
                <div style="flex: 1 1 360px;"><div style="font-weight: 600;">Обработка персональных данных (152-ФЗ)</div><div style="font-size: 14px; color: var(--text-muted); margin-top: 4px;">Обязательно для работы сервиса · дано 10.10.2026</div></div>
                <a href="#" class="fsp-link" style="font-size: 14px;" @click.prevent="show('Текст согласия откроется в PDF')">Текст согласия</a>
              </div>
              <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; padding-bottom: 16px; box-shadow: inset 0 -1px 0 var(--line);">
                <div style="flex: 1 1 360px;"><div style="font-weight: 600;">Публикация профиля для работодателей</div><div style="font-size: 14px; color: var(--text-muted); margin-top: 4px;">{{ published ? 'Без него вас не найдут в подборках · дано 10.10.2026' : 'Отозвано — профиль не участвует в подборках' }}</div></div>
                <FspButton size="sm" :variant="published ? 'ghost' : 'primary'" @click="togglePublish">{{ published ? 'Отозвать' : 'Дать согласие' }}</FspButton>
              </div>
              <FspCheckbox label="Получать письма о новых приглашениях и заданиях" :default-checked="v.yes" />
            </div>
          </section>

          <section id="account" style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 20px;">Аккаунт</h2>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 16px; align-items: end;">
              <FspInput label="Почта" default-value="a.kuznetsov@mail.ru" hint="Подтверждена" />
              <div style="display: flex; gap: 8px; flex-wrap: wrap; padding-bottom: 22px;">
                <FspButton size="sm" variant="outline" toast="Ссылка для смены пароля отправлена на почту">Сменить пароль</FspButton>
                <FspButton size="sm" variant="ghost" @click="removeAccount">Удалить аккаунт</FspButton>
              </div>
            </div>
          </section>

          <div style="display: flex; justify-content: flex-end; gap: 8px;">
            <FspButton variant="ghost" href="/candidate/profile">Отменить</FspButton>
            <FspButton toast="Настройки сохранены">Сохранить</FspButton>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
