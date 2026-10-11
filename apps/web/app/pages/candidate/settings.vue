<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'
useHead({ title: 'Настройки и приватность — Карьера ФСП' })

const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => {
  const [settings, profile, me] = await Promise.all([
    read(api.GET('/api/v1/candidates/me/settings')),
    read(api.GET('/api/v1/candidates/me')),
    read(api.GET('/api/v1/me')),
  ])
  return { settings, profile, me }
})
const section = ref('privacy')
const sections = [
  { id: 'privacy', label: 'Приватность' }, { id: 'fspid', label: 'ФСП ID' },
  { id: 'consent', label: 'Согласия' }, { id: 'account', label: 'Аккаунт' }
]
const navStyle = (on: boolean) => on
  ? 'padding: 12px 16px; font-weight: 600; text-decoration: none; color: var(--text); box-shadow: inset 3px 0 0 var(--accent-mark); background: var(--surface-hover);'
  : 'padding: 12px 16px; text-decoration: none; color: var(--text-muted);'
const hideQuery = ref('')
const hidden = ref<string[]>([])
const fspLinked = ref(false)
const published = ref(true)
const consentProcessing = ref(false)
const consentPublication = ref(false)
const email = ref('')

watch(screen.data, (bundle) => {
  if (!bundle) return
  published.value = bundle.settings.visible
  hidden.value = [...(bundle.settings.hidden_company_ids ?? [])]
  const consents = bundle.settings as typeof bundle.settings & { consent_processing?: boolean; consent_publication?: boolean }
  if ('consent_processing' in bundle.settings) consentProcessing.value = !!consents.consent_processing
  if ('consent_publication' in bundle.settings) consentPublication.value = !!consents.consent_publication
  fspLinked.value = (bundle.profile.fsp_achievements?.length ?? 0) > 0
  email.value = bundle.me.email || bundle.profile.contact_email || ''
}, { immediate: true })

function addHidden() {
  const q = hideQuery.value.trim()
  if (!q) return
  if (!hidden.value.includes(q)) hidden.value.push(q)
  hideQuery.value = ''
}
async function toggleFsp() {
  if (fspLinked.value) {
    show('Отвязка ФСП ID ещё не реализована в рамках MVP')
    return
  }
  try {
    const next = await read(api.POST('/api/v1/candidates/me/fsp-link'))
    if (screen.data.value) screen.data.value.profile = next
    fspLinked.value = (next.fsp_achievements?.length ?? 0) > 0
    show(fspLinked.value ? `ФСП ID связан — достижений: ${next.fsp_achievements?.length ?? 0}` : 'Новых достижений нет')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось связать ФСП ID')
  }
}
async function saveSettings() {
  try {
    const body = {
      visible: published.value,
      hidden_company_ids: hidden.value,
      consent_processing: consentProcessing.value,
      consent_publication: consentPublication.value,
    } as components['schemas']['CandidateSettings']
    const next = await read(api.PUT('/api/v1/candidates/me/settings', {
      body,
    }))
    if (screen.data.value) screen.data.value.settings = next
    show(next.visible ? 'Профиль виден работодателям' : 'Профиль скрыт из подборок')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось сохранить настройки')
  }
}
async function togglePublish() {
  published.value = !published.value
  await saveSettings()
}
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Карьера" :user="screen.data.value?.profile.display_name || 'Кандидат'" :links="candidateLinks" logo-dark="/brand/championship-logo-white.svg" logo-light="/brand/championship-logo-navy.svg" />

    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px;">
      <h1 class="fsp-display" style="font-size: 40px; line-height: 44px; margin-bottom: 32px;">Настройки</h1>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
      <div style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
        <nav aria-label="Разделы настроек" style="flex: 1 1 220px; display: flex; flex-direction: column; gap: 4px;">
          <a v-for="sct in sections" :key="sct.id" :href="'#' + sct.id" :style="navStyle(section === sct.id)" @click="section = sct.id">{{ sct.label }}</a>
        </nav>

        <div style="flex: 999 1 640px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
          <section id="privacy" style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 8px;">Что видит работодатель</h2>
            <p style="margin: 0 0 20px; font-size: 14px; line-height: 20px; color: var(--text-muted);">Категория, грейд и результаты тестов видны всегда — по ним вас находят. Остальное — на ваше усмотрение.</p>
            <div style="display: flex; flex-direction: column; gap: 4px;">
              <FspCheckbox v-model="published" label="Показывать профиль в банке кандидатов" />
              <FspCheckbox label="Полное имя (иначе — «Алексей К.»)" />
              <FspCheckbox label="Текущее место работы" />
              <FspCheckbox label="Достижения ФСП" />
              <FspCheckbox label="Стандартизированный PDF-профиль" />
            </div>
            <div class="fsp-cut" style="--cut: var(--cut-s); --fill: var(--surface-hover); padding: 16px 20px; margin-top: 20px; display: flex; gap: 12px; align-items: flex-start; font-size: 14px; line-height: 20px;">
              <FspIcon name="user" />
              <span>Телефон и почта скрыты от всех работодателей. Компания увидит их, только если вы примете её приглашение или откликнетесь сами.</span>
            </div>
            <div style="margin-top: 20px;">
              <form @submit.prevent="addHidden">
                <FspInput v-model="hideQuery" label="Скрыть профиль от компаний" icon="search" placeholder="UUID компании — Enter, чтобы добавить" />
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
                <div style="margin-top: 6px;"><FspStatusBadge v-if="fspLinked" status="new">Связан</FspStatusBadge><FspStatusBadge v-else status="archived">Не привязан</FspStatusBadge></div>
                <div style="font-size: 14px; line-height: 20px; color: var(--text-muted); margin-top: 8px;">{{ fspLinked ? `Подтянуто достижений: ${screen.data.value?.profile.fsp_achievements?.length ?? 0}` : 'Привяжите ФСП ID, чтобы результаты соревнований поднимали вас в выдаче.' }}</div>
              </div>
              <div style="display: flex; gap: 8px;">
                <FspButton v-if="fspLinked" size="sm" variant="outline" @click="toggleFsp">Обновить</FspButton>
                <FspButton size="sm" :variant="fspLinked ? 'ghost' : 'primary'" @click="toggleFsp">{{ fspLinked ? 'Отвязать' : 'Привязать ФСП ID' }}</FspButton>
              </div>
            </div>
          </section>

          <section id="consent" style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 20px;">Согласия</h2>
            <div style="display: flex; flex-direction: column; gap: 16px;">
              <FspCheckbox v-model="consentProcessing" label="Согласие на обработку персональных данных" />
              <FspCheckbox v-model="consentPublication" label="Согласие на публикацию профиля работодателям" />
              <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; padding-bottom: 16px; box-shadow: inset 0 -1px 0 var(--line);">
                <div style="flex: 1 1 360px;"><div style="font-weight: 600;">Обработка персональных данных (152-ФЗ)</div><div style="font-size: 14px; color: var(--text-muted); margin-top: 4px;">Обязательно для работы сервиса · дано 10.10.2026</div></div>
                <span style="font-size: 14px; color: var(--text-muted);">Текст согласия ещё не реализован в рамках MVP</span>
              </div>
              <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; padding-bottom: 16px; box-shadow: inset 0 -1px 0 var(--line);">
                <div style="flex: 1 1 360px;"><div style="font-weight: 600;">Публикация профиля для работодателей</div><div style="font-size: 14px; color: var(--text-muted); margin-top: 4px;">{{ published ? 'Профиль участвует в подборках' : 'Отозвано — профиль не участвует в подборках' }}</div></div>
                <FspButton size="sm" :variant="published ? 'ghost' : 'primary'" @click="togglePublish">{{ published ? 'Отозвать' : 'Дать согласие' }}</FspButton>
              </div>
              <p style="margin: 0; font-size: 14px; color: var(--text-muted);">Письма о приглашениях ещё не реализованы в рамках MVP</p>
            </div>
          </section>

          <section id="account" style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 20px;">Аккаунт</h2>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 16px; align-items: end;">
              <FspInput v-model="email" label="Почта" hint="Из аккаунта" />
              <div style="display: flex; gap: 8px; flex-wrap: wrap; padding-bottom: 22px;">
                <FspButton size="sm" variant="ghost" disabled>Удалить аккаунт</FspButton>
                <span style="font-size: 14px; color: var(--text-muted); align-self: center;">Ещё не реализовано в рамках MVP</span>
              </div>
            </div>
          </section>

          <div style="display: flex; justify-content: flex-end; gap: 8px;">
            <FspButton variant="ghost" href="/candidate/profile">Отменить</FspButton>
            <FspButton @click="saveSettings">Сохранить</FspButton>
          </div>
        </div>
      </div>
      </ScreenState>
    </main>
  </div>
</template>
