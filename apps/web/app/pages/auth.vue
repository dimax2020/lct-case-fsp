<script setup lang="ts">
useHead({ title: 'Регистрация — Карьера ФСП' })

const v = reactive((() => {
  return { yes: true, dots: 6 };
})())

const route = useRoute()
const { show } = useToast()
const role = ref<'candidate' | 'employer'>(route.query.role === 'employer' ? 'employer' : 'candidate')
const mode = ref<'register' | 'login'>(route.query.mode === 'login' ? 'login' : 'register')
const email = ref('')
const password = ref('')
const agree = ref(false)
const errors = reactive({ email: '', password: '', agree: '' })

const cardStyle = (on: boolean) => on
  ? '--cut: var(--cut-m); padding: 20px; display: flex; gap: 14px; cursor: pointer;'
  : '--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px; display: flex; gap: 14px; cursor: pointer;'

function submit() {
  errors.email = /.+@.+\..+/.test(email.value) ? '' : 'Введите корректную почту'
  errors.password = mode.value === 'login' || password.value.length >= 10 ? '' : 'Пароль — не менее 10 символов'
  if (mode.value === 'login' && !password.value) errors.password = 'Введите пароль'
  errors.agree = mode.value === 'register' && !agree.value ? 'Нужно согласие на обработку данных' : ''
  if (errors.email || errors.password || errors.agree) return
  if (import.meta.client) sessionStorage.setItem('fsp-mock-role', role.value)
  show(mode.value === 'register' ? 'Аккаунт создан — письмо отправлено на ' + email.value : 'С возвращением!')
  navigateTo(role.value === 'employer' ? (mode.value === 'register' ? '/employer/company' : '/employer/need') : (mode.value === 'register' ? '/candidate/onboarding' : '/candidate/profile'))
}
function fspId() {
  if (import.meta.client) sessionStorage.setItem('fsp-mock-role', role.value)
  show('Вход через ФСП ID: результаты соревнований подтянуты')
  navigateTo(role.value === 'employer' ? '/employer/need' : '/candidate/onboarding')
}
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh; display: flex; flex-direction: column;">
    <header style="display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 32px; box-shadow: inset 0 -1px 0 var(--line);">
      <NuxtLink to="/"><img src="/brand/championship-logo-white.svg" alt="Чемпионат России — на главную" style="height: 36px; display: block;"></NuxtLink>
      <div style="font-size: 14px; color: var(--text-muted);"><template v-if="mode === 'register'">Уже есть аккаунт? <a href="#" class="fsp-link" @click.prevent="mode = 'login'">Войти</a></template><template v-else>Нет аккаунта? <a href="#" class="fsp-link" @click.prevent="mode = 'register'">Зарегистрироваться</a></template></div>
    </header>

    <main style="flex: 1; max-width: 1240px; width: 100%; box-sizing: border-box; margin: 0 auto; padding: 56px 32px; display: flex; flex-wrap: wrap; gap: 48px; align-items: flex-start;">
      <section style="flex: 999 1 520px; min-width: 0; max-width: 620px;">
        <h1 class="fsp-display" style="font-size: 40px; line-height: 44px;">{{ mode === 'register' ? 'Регистрация' : 'Вход' }}</h1>
        <p style="margin: 12px 0 32px; font-size: 16px; line-height: 24px; color: var(--text-muted);">{{ mode === 'register' ? 'Один аккаунт — одна роль. Сменить её позже можно через поддержку.' : 'Выберите роль и войдите по почте или через ФСП ID.' }}</p>

        <fieldset style="border: 0; margin: 0 0 24px; padding: 0;">
          <legend style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 12px;">Кто вы</legend>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); gap: 12px;">
            <label :class="['fsp-cut', role === 'candidate' && 'fsp-active']" :style="cardStyle(role === 'candidate')">
              <input v-model="role" type="radio" name="role" value="candidate" style="accent-color: var(--primary); width: 18px; height: 18px; margin: 2px 0 0;">
              <span><span style="display: block; font-weight: 600; font-size: 16px;">Я кандидат</span><span style="display: block; font-size: 14px; line-height: 20px; color: var(--text-muted); margin-top: 4px;">Пройду тест на грейд и буду получать приглашения</span></span>
            </label>
            <label :class="['fsp-cut', role === 'employer' && 'fsp-active']" :style="cardStyle(role === 'employer')">
              <input v-model="role" type="radio" name="role" value="employer" style="accent-color: var(--primary); width: 18px; height: 18px; margin: 2px 0 0;">
              <span><span style="display: block; font-weight: 600; font-size: 16px;">Я работодатель</span><span style="display: block; font-size: 14px; line-height: 20px; color: var(--text-muted); margin-top: 4px;">Ищу специалистов и отправляю приглашения</span></span>
            </label>
          </div>
        </fieldset>

        <form style="display: flex; flex-direction: column; gap: 16px;" novalidate @submit.prevent="submit">
          <FspInput v-model="email" label="Электронная почта" type="email" placeholder="name@mail.ru" :hint="mode === 'register' ? 'Пришлём письмо для подтверждения адреса' : undefined" :error="errors.email || undefined" autocomplete="email" />
          <FspInput v-model="password" label="Пароль" type="password" :placeholder="mode === 'register' ? 'Не менее 10 символов' : 'Ваш пароль'" :error="errors.password || undefined" :autocomplete="mode === 'register' ? 'new-password' : 'current-password'" />
          <template v-if="mode === 'register'">
            <FspCheckbox v-model="agree" label="Согласен на обработку персональных данных по 152-ФЗ и с условиями публикации профиля" />
            <div v-if="errors.agree" style="margin-top: -8px; font-size: 13px; color: var(--danger);">{{ errors.agree }}</div>
          </template>
          <a v-else href="#" class="fsp-link" style="font-size: 14px; align-self: flex-start;" @click.prevent="show('Ссылка для восстановления отправлена на почту')">Забыли пароль?</a>
          <FspButton size="lg" :block="v.yes" type="submit">{{ mode === 'register' ? 'Создать аккаунт' : 'Войти' }}</FspButton>
        </form>

        <div style="display: flex; align-items: center; gap: 16px; margin: 24px 0; color: var(--text-muted); font-size: 14px;">
          <span style="flex: 1; height: 1px; background: var(--line);"></span>или<span style="flex: 1; height: 1px; background: var(--line);"></span>
        </div>
        <FspButton size="lg" variant="outline" :block="v.yes" @click="fspId">Войти через ФСП ID</FspButton>
        <p style="margin: 12px 0 0; font-size: 13px; line-height: 18px; color: var(--text-muted);">Вход через ФСП ID сразу подтянет ваши результаты соревнований в профиль.</p>
      </section>

      <aside style="flex: 1 1 360px; min-width: 0;">
        <FspPlate :dots="v.dots">
          <div class="fsp-display" style="font-size: 20px; line-height: 24px;">Что дальше</div>
          <ol style="margin: 20px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 16px;">
            <li style="display: flex; gap: 14px;"><span style="font-family: var(--font-display); font-size: 16px; width: 28px; flex: none;">1</span><span style="font-size: 15px; line-height: 22px;">Подтвердите почту по ссылке из письма</span></li>
            <li style="display: flex; gap: 14px;"><span style="font-family: var(--font-display); font-size: 16px; width: 28px; flex: none;">2</span><span style="font-size: 15px; line-height: 22px;">Загрузите резюме или заполните профиль по форме</span></li>
            <li style="display: flex; gap: 14px;"><span style="font-family: var(--font-display); font-size: 16px; width: 28px; flex: none;">3</span><span style="font-size: 15px; line-height: 22px;">Пройдите опрос и тест — около 40 минут</span></li>
            <li style="display: flex; gap: 14px;"><span style="font-family: var(--font-display); font-size: 16px; width: 28px; flex: none;">4</span><span style="font-size: 15px; line-height: 22px;">Получите категорию и ждите приглашений</span></li>
          </ol>
        </FspPlate>
      </aside>
    </main>
  </div>
</template>
