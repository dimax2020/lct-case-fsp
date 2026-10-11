<script setup lang="ts">
useHead({ title: 'Регистрация и вход — Карьера ФСП' })

// Почта и пароль вводятся один раз — на странице ФСП ID (Keycloak). Здесь человек выбирает роль
// и даёт согласие; роль передаётся в /auth/role?pick=…, поэтому отдельный экран «Кто вы?» не нужен.
const route = useRoute()
const role = ref<'candidate' | 'employer'>(route.query.role === 'employer' ? 'employer' : 'candidate')
const mode = ref<'register' | 'login'>(route.query.mode === 'login' ? 'login' : 'register')
const agree = ref(false)
const error = ref('')
const going = ref(false)

const cardStyle = (on: boolean) => on
  ? '--cut: var(--cut-m); padding: 20px; display: flex; gap: 14px; cursor: pointer;'
  : '--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px; display: flex; gap: 14px; cursor: pointer;'

function target() {
  if (mode.value === 'login') return '/auth/role?next=/cabinet'
  const next = role.value === 'employer' ? '/employer/company' : '/candidate/onboarding?consent=1'
  return `/auth/role?pick=${role.value}&next=${encodeURIComponent(next)}`
}

// Демо-аккаунты из infra/keycloak/realm-export.json; профили заполняет `make seed`.
const DEMO = [
  {
    role: 'candidate' as const,
    title: 'Кандидат',
    who: 'Алексей Кузнецов · Backend · Middle',
    about: 'Заполненный профиль: тест на грейд, опыт, проекты, 1 место на хакатоне ФСП, резюме PDF',
    email: 'candidate@demo.fsp',
    password: 'candidate-demo',
  },
  {
    role: 'employer' as const,
    title: 'Работодатель',
    who: '«Северная Лампа» · финтех, Новосибирск',
    about: '5 открытых потребностей (Backend, Frontend, DevOps), подборка с объяснениями, приглашения и чат',
    email: 'employer@demo.fsp',
    password: 'employer-demo',
  },
]
const copied = ref('')

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = text
    setTimeout(() => { if (copied.value === text) copied.value = '' }, 1500)
  } catch {
    copied.value = ''
  }
}

function demoLogin(email: string) {
  going.value = true
  location.href = `/auth/keycloak/login?callbackRedirectUrl=${encodeURIComponent('/auth/role?next=/cabinet')}&login_hint=${encodeURIComponent(email)}`
}

function go() {
  error.value = ''
  if (mode.value === 'register' && !agree.value) {
    error.value = 'Нужно согласие на обработку персональных данных'
    return
  }
  going.value = true
  location.href = `/auth/keycloak/login?callbackRedirectUrl=${encodeURIComponent(target())}`
}
</script>

<template>
  <div class="fsp-shell" style="display: flex; flex-direction: column;">
    <header class="fsp-topbar u-between" style="padding: 16px var(--page-x); box-shadow: inset 0 -1px 0 var(--line);">
      <NuxtLink to="/"><img src="/brand/fsp-star-dark.svg" alt="ФСП — на главную" style="width: 36px; height: 36px; display: block; object-fit: contain;" class="fsp-only-dark"><img src="/brand/fsp-star-light.svg" alt="ФСП — на главную" style="width: 36px; height: 36px; display: block; object-fit: contain;" class="fsp-only-light"></NuxtLink>
      <div class="u-note-sm">
        <template v-if="mode === 'register'">Уже есть аккаунт? <a href="#" class="fsp-link" @click.prevent="mode = 'login'">Войти</a></template>
        <template v-else>Нет аккаунта? <a href="#" class="fsp-link" @click.prevent="mode = 'register'">Зарегистрироваться</a></template>
      </div>
    </header>

    <main class="fsp-page fsp-columns" style="flex: 1; width: 100%; padding-top: 56px; gap: 48px;">
      <section style="flex: 999 1 520px; min-width: 0; max-width: 620px;">
        <h1 class="fsp-display fsp-title">{{ mode === 'register' ? 'Регистрация' : 'Вход' }}</h1>
        <p class="u-muted-p" style="margin: 12px 0 32px; font-size: 16px; line-height: 24px;">
          {{ mode === 'register'
            ? 'Выберите роль и дайте согласие. Почту и пароль вы зададите на странице ФСП ID — туда же придёт письмо для подтверждения адреса.'
            : 'Вход через ФСП ID: почта и пароль, которые вы указали при регистрации. Кабинет откроется по вашей роли.' }}
        </p>

        <fieldset v-if="mode === 'register'" style="border: 0; margin: 0 0 24px; padding: 0;">
          <legend class="fsp-eyebrow u-mb-10">Кто вы</legend>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); gap: 12px;">
            <label :class="['fsp-cut', role === 'candidate' && 'fsp-active']" :style="cardStyle(role === 'candidate')">
              <input v-model="role" type="radio" name="role" value="candidate" style="accent-color: var(--primary); width: 18px; height: 18px; margin: 2px 0 0;">
              <span><span class="u-strong-16" style="display: block;">Я кандидат</span><span class="u-note u-mt-4" style="display: block;">Пройду опрос и тест на грейд и буду получать приглашения с вилкой</span></span>
            </label>
            <label :class="['fsp-cut', role === 'employer' && 'fsp-active']" :style="cardStyle(role === 'employer')">
              <input v-model="role" type="radio" name="role" value="employer" style="accent-color: var(--primary); width: 18px; height: 18px; margin: 2px 0 0;">
              <span><span class="u-strong-16" style="display: block;">Я работодатель</span><span class="u-note u-mt-4" style="display: block;">Опишу потребность, получу подборку и сам приглашу кандидата</span></span>
            </label>
          </div>
        </fieldset>

        <form class="fsp-stack-16" novalidate @submit.prevent="go">
          <template v-if="mode === 'register'">
            <FspCheckbox v-model="agree">
              Согласен(на) на обработку персональных данных по 152-ФЗ и с <NuxtLink to="/legal/privacy" class="fsp-link" target="_blank">политикой обработки данных</NuxtLink>
            </FspCheckbox>
            <p class="u-small" style="margin: 0;">Публикацию профиля для работодателей кандидат включает отдельно — в настройках приватности.</p>
          </template>
          <p v-if="error" role="alert" class="u-danger" style="margin: 0; font-size: 14px;">{{ error }}</p>
          <FspButton size="lg" :block="true" type="submit" icon-right="arrow-right" :disabled="going">
            {{ mode === 'register' ? 'Продолжить в ФСП ID' : 'Войти через ФСП ID' }}
          </FspButton>
        </form>
        <section class="fsp-cut demo-box" aria-labelledby="demo-title">
          <div class="u-between" style="gap: 12px; flex-wrap: wrap;">
            <h2 id="demo-title" class="fsp-display" style="font-size: 18px;">Демо-доступ</h2>
            <span class="u-small">Тестовые аккаунты с заполненными профилями</span>
          </div>
          <div class="demo-grid">
            <div v-for="d in DEMO" :key="d.email" class="demo-card">
              <div class="fsp-eyebrow">{{ d.title }}</div>
              <div class="u-strong-16">{{ d.who }}</div>
              <p class="u-note" style="margin: 0;">{{ d.about }}</p>
              <dl class="demo-cred">
                <dt>Почта</dt>
                <dd><code>{{ d.email }}</code><button type="button" class="demo-copy" :aria-label="`Скопировать почту ${d.email}`" @click="copy(d.email)">{{ copied === d.email ? 'Скопировано' : 'Копировать' }}</button></dd>
                <dt>Пароль</dt>
                <dd><code>{{ d.password }}</code><button type="button" class="demo-copy" :aria-label="`Скопировать пароль для ${d.email}`" @click="copy(d.password)">{{ copied === d.password ? 'Скопировано' : 'Копировать' }}</button></dd>
              </dl>
              <FspButton size="sm" :block="true" variant="outline" icon-right="arrow-right" :disabled="going" @click="demoLogin(d.email)">Войти</FspButton>
            </div>
          </div>
          <p class="u-small" style="margin: 0;">Почта подставится на странице ФСП ID — останется ввести пароль.</p>
        </section>

        <p class="u-note" style="margin: 20px 0 0;">
          ФСП ID работает на Keycloak. На его странице можно создать аккаунт, восстановить пароль и подтвердить почту.
          Связать результаты соревнований ФСП можно потом в профиле.
        </p>
      </section>

      <aside style="flex: 1 1 360px; min-width: 0;">
        <FspPlate :dots="6">
          <div class="fsp-display u-h3">Что дальше</div>
          <ol style="margin: 20px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 16px;">
            <li class="u-row-16"><span class="fsp-display" style="font-size: 16px; width: 28px; flex: none;">1</span><span style="font-size: 15px; line-height: 22px;">Подтвердите почту по ссылке из письма</span></li>
            <li class="u-row-16"><span class="fsp-display" style="font-size: 16px; width: 28px; flex: none;">2</span><span style="font-size: 15px; line-height: 22px;">Пройдите опрос: отрасль, специализация и грейд</span></li>
            <li class="u-row-16"><span class="fsp-display" style="font-size: 16px; width: 28px; flex: none;">3</span><span style="font-size: 15px; line-height: 22px;">Решите тест на грейд — около 40 минут — и получите категорию</span></li>
            <li class="u-row-16"><span class="fsp-display" style="font-size: 16px; width: 28px; flex: none;">4</span><span style="font-size: 15px; line-height: 22px;">По желанию пройдите тест рабочего стиля и загрузите резюме</span></li>
          </ol>
        </FspPlate>
      </aside>
    </main>
  </div>
</template>

<style>
.demo-box { --cut: var(--cut-l); --fill: var(--surface); --edge: var(--accent-mark); --bw: 2px; margin-top: 28px; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.demo-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); gap: 12px; }
.demo-card { padding: 16px; background: var(--surface-hover); display: flex; flex-direction: column; gap: 8px; }
.demo-cred { margin: 4px 0; display: grid; grid-template-columns: auto 1fr; gap: 6px 12px; align-items: center; font-size: 14px; }
.demo-cred dt { color: var(--text-muted); }
.demo-cred dd { margin: 0; display: flex; gap: 8px; align-items: center; justify-content: space-between; min-width: 0; }
.demo-cred code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; overflow-wrap: anywhere; }
.demo-copy { border: 0; background: none; padding: 2px 0; font: inherit; font-size: 12px; color: var(--link); cursor: pointer; text-decoration: underline; text-underline-offset: 3px; flex: none; }
</style>
