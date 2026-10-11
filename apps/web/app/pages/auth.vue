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
    <header class="u-between" style="padding: 16px var(--page-x); box-shadow: inset 0 -1px 0 var(--line);">
      <NuxtLink to="/"><img src="/brand/championship-logo-white.svg" alt="Чемпионат России — на главную" style="height: 36px; display: block;" class="fsp-only-dark"><img src="/brand/championship-logo-navy.svg" alt="Чемпионат России — на главную" style="height: 36px; display: block;" class="fsp-only-light"></NuxtLink>
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
