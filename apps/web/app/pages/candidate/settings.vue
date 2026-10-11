<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'
import { apiFetch } from '~/utils/raw'

type Settings = components['schemas']['CandidateSettings']
type CompanyBrief = { id: string; name: string; city?: string | null }

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
  { id: 'consent', label: 'Согласия' }, { id: 'account', label: 'Аккаунт' },
]
const navStyle = (on: boolean) => on
  ? 'padding: 12px 16px; font-weight: 600; text-decoration: none; color: var(--text); box-shadow: inset 3px 0 0 var(--accent-mark); background: var(--surface-hover);'
  : 'padding: 12px 16px; text-decoration: none; color: var(--text-muted);'

// Все переключатели сохраняются на сервере и применяются в выдаче работодателю.
const form = reactive({
  visible: true,
  show_full_name: false,
  show_current_job: true,
  show_fsp: true,
  show_pdf: true,
  show_psych: false,
  consent_processing: false,
  consent_publication: false,
})
const hidden = ref<CompanyBrief[]>([])
const companyQ = ref('')
const companyHits = ref<CompanyBrief[]>([])
const fspLinked = ref(false)
const email = ref('')
const saving = ref(false)
const dirty = ref(false)
let searchTimer: ReturnType<typeof setTimeout> | undefined

function apply(settings: Settings) {
  form.visible = settings.visible
  form.show_full_name = !!settings.show_full_name
  form.show_current_job = settings.show_current_job ?? true
  form.show_fsp = settings.show_fsp ?? true
  form.show_pdf = settings.show_pdf ?? true
  form.show_psych = !!settings.show_psych
  form.consent_processing = !!settings.consent_processing
  form.consent_publication = !!settings.consent_publication
  hidden.value = (settings.hidden_companies ?? (settings.hidden_company_ids ?? []).map(id => ({ id, name: id }))).map(c => ({ id: c.id, name: c.name }))
  fspLinked.value = settings.fsp_linked ?? false
  // Наблюдатель за формой сработает после этого присваивания — сбрасываем флаг на следующем тике.
  void nextTick(() => { dirty.value = false })
}

watch(screen.data, (bundle) => {
  if (!bundle) return
  apply(bundle.settings)
  if (bundle.settings.fsp_linked === undefined) fspLinked.value = (bundle.profile.fsp_achievements?.length ?? 0) > 0
  email.value = bundle.me.email || bundle.profile.contact_email || ''
}, { immediate: true })

watch(form, () => { dirty.value = true }, { deep: true })

const settings = computed(() => screen.data.value?.settings ?? null)

function onCompanyInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    const q = companyQ.value.trim()
    if (q.length < 2) { companyHits.value = []; return }
    try {
      companyHits.value = (await apiFetch<CompanyBrief[]>('/api/v1/companies', { query: { q } })).filter(c => !hidden.value.some(h => h.id === c.id))
    } catch {
      companyHits.value = []
    }
  }, 250)
}
onBeforeUnmount(() => clearTimeout(searchTimer))

function hideCompany(company: CompanyBrief) {
  if (!hidden.value.some(h => h.id === company.id)) hidden.value = [...hidden.value, company]
  companyQ.value = ''
  companyHits.value = []
  dirty.value = true
}

function unhide(id: string) {
  hidden.value = hidden.value.filter(h => h.id !== id)
  dirty.value = true
}

async function saveSettings(message?: string) {
  if (!settings.value) return
  saving.value = true
  try {
    const body = { ...settings.value, ...form, hidden_company_ids: hidden.value.map(h => h.id) }
    const next = await read(api.PUT('/api/v1/candidates/me/settings', { body }))
    if (screen.data.value) screen.data.value.settings = next
    apply(next)
    show(message ?? (next.visible ? 'Настройки сохранены — профиль виден работодателям' : 'Настройки сохранены — профиль скрыт из подборок'))
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось сохранить настройки')
  } finally {
    saving.value = false
  }
}

async function togglePublication() {
  form.consent_publication = !form.consent_publication
  if (!form.consent_publication) form.visible = false
  await saveSettings(form.consent_publication ? 'Согласие на публикацию дано' : 'Согласие отозвано — профиль скрыт из подборок')
}

async function linkFsp() {
  try {
    const next = await read(api.POST('/api/v1/candidates/me/fsp-link'))
    if (screen.data.value) screen.data.value.profile = next
    fspLinked.value = (next.fsp_achievements?.length ?? 0) > 0
    show(fspLinked.value ? `ФСП ID связан — достижений: ${next.fsp_achievements?.length ?? 0}` : 'Достижений ФСП не найдено')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось связать ФСП ID')
  }
}

async function unlinkFsp() {
  try {
    const next = await apiFetch<components['schemas']['CandidateProfile']>('/api/v1/candidates/me/fsp-link', { method: 'DELETE' })
    if (screen.data.value) screen.data.value.profile = next
    fspLinked.value = false
    show('ФСП ID отвязан — достижения удалены из профиля')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось отвязать ФСП ID')
  }
}
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Карьера" :user="screen.data.value?.profile.display_name || 'Кандидат'" :links="candidateLinks" />

    <main class="fsp-page">
      <h1 class="fsp-display fsp-title" style="margin-bottom: 32px;">Настройки</h1>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <div class="fsp-columns">
          <nav aria-label="Разделы настроек" class="set-nav">
            <a v-for="sct in sections" :key="sct.id" :href="'#' + sct.id" :style="navStyle(section === sct.id)" @click="section = sct.id">{{ sct.label }}</a>
          </nav>

          <div class="fsp-stack-24" style="flex: 999 1 640px; min-width: 0;">
            <section id="privacy" class="fsp-section">
              <h2 class="fsp-display u-h3 u-mb-8">Что видит работодатель</h2>
              <p class="u-note" style="margin: 0 0 20px;">Категория, грейд и результаты теста на грейд видны всегда — по ним вас находят. Остальное — на ваше усмотрение.</p>
              <div class="fsp-stack-12" style="gap: 4px;">
                <FspCheckbox v-model="form.visible" label="Показывать профиль в банке кандидатов и подборках" />
                <FspCheckbox v-model="form.show_full_name" label="Полное имя (иначе — имя и первая буква фамилии)" />
                <FspCheckbox v-model="form.show_current_job" label="Текущее место работы" />
                <FspCheckbox v-model="form.show_fsp" label="Достижения ФСП" />
                <FspCheckbox v-model="form.show_pdf" label="Стандартизированный PDF-профиль (без контактов до принятия приглашения)" />
                <FspCheckbox v-model="form.show_psych" label="Результаты теста рабочего стиля" />
              </div>
              <div class="fsp-cut set-note">
                <FspIcon name="user" />
                <span>Телефон и почта скрыты от всех работодателей. Компания увидит их, только если вы примете её приглашение или откликнетесь сами.</span>
              </div>
              <div style="margin-top: 20px; position: relative;">
                <FspInput v-model="companyQ" label="Скрыть профиль от компаний" icon="search" placeholder="Начните вводить название компании" autocomplete="off" @input="onCompanyInput" />
                <div v-if="companyHits.length" class="set-hits" role="listbox" aria-label="Найденные компании">
                  <button v-for="c in companyHits" :key="c.id" type="button" role="option" @click="hideCompany(c)">
                    {{ c.name }}<span v-if="c.city" class="u-small"> · {{ c.city }}</span>
                  </button>
                </div>
                <p v-else-if="companyQ.trim().length >= 2" class="u-small" style="margin: 8px 0 0;">Компаний с таким названием не найдено.</p>
                <div v-if="hidden.length" class="u-row-wrap u-mt-12">
                  <FspChip v-for="h in hidden" :key="h.id" :selected="true" locked icon="x" :aria-label="'Снова показывать компании ' + h.name" @click="unhide(h.id)">{{ h.name }}</FspChip>
                </div>
                <p class="u-small" style="margin: 8px 0 0;">Скрытые компании не увидят вас ни в подборке, ни в банке и не смогут отправить приглашение.</p>
              </div>
            </section>

            <section id="fspid" class="fsp-section">
              <div class="u-row-center" style="gap: 20px;">
                <img src="/brand/fsp-star-dark.svg" alt="" aria-hidden="true" class="fsp-only-dark" style="width: 56px; height: 56px;"><img src="/brand/fsp-star-light.svg" alt="" aria-hidden="true" class="fsp-only-light" style="width: 56px; height: 56px;">
                <div style="flex: 1 1 280px; min-width: 0;">
                  <h2 class="fsp-display u-h3">ФСП ID</h2>
                  <div class="u-mt-6"><FspStatusBadge v-if="fspLinked" status="new">Связан</FspStatusBadge><FspStatusBadge v-else status="archived">Не привязан</FspStatusBadge></div>
                  <div class="u-note" style="margin-top: 8px;">{{ fspLinked ? `Подтянуто достижений: ${screen.data.value?.profile.fsp_achievements?.length ?? 0}. При отвязке достижения и навыки из реестра ФСП удаляются из профиля.` : 'Привяжите ФСП ID, чтобы результаты соревнований поднимали вас в выдаче. Без истории ФСП профиль строится по тестам.' }}</div>
                </div>
                <div class="u-row-wrap">
                  <FspButton v-if="fspLinked" size="sm" variant="outline" @click="linkFsp">Обновить</FspButton>
                  <FspButton v-if="fspLinked" size="sm" variant="ghost" @click="unlinkFsp">Отвязать</FspButton>
                  <FspButton v-else size="sm" @click="linkFsp">Привязать ФСП ID</FspButton>
                </div>
              </div>
            </section>

            <section id="consent" class="fsp-section">
              <h2 class="fsp-display u-h3 u-mb-20">Согласия</h2>
              <div class="fsp-stack-16">
                <div class="set-consent">
                  <div>
                    <div class="u-strong">Обработка персональных данных (152-ФЗ)</div>
                    <div class="u-small u-mt-4">
                      {{ form.consent_processing ? `Дано ${longDate(settings?.consent_processing_at)}` : 'Не дано — без него сервис не может показывать ваш профиль' }}
                      · <NuxtLink to="/legal/privacy" class="fsp-link">текст согласия</NuxtLink>
                    </div>
                  </div>
                  <FspCheckbox v-model="form.consent_processing" label="Согласен(на)" />
                </div>
                <div class="set-consent">
                  <div>
                    <div class="u-strong">Публикация профиля для работодателей</div>
                    <div class="u-small u-mt-4">
                      {{ form.consent_publication ? `Дано ${longDate(settings?.consent_publication_at)} · профиль участвует в подборках` : 'Не дано — профиль не участвует в подборках' }}
                      · <NuxtLink to="/legal/terms" class="fsp-link">условия публикации</NuxtLink>
                    </div>
                  </div>
                  <FspButton size="sm" :variant="form.consent_publication ? 'ghost' : 'primary'" :disabled="saving" @click="togglePublication">{{ form.consent_publication ? 'Отозвать' : 'Дать согласие' }}</FspButton>
                </div>
                <p class="u-small" style="margin: 0;">О новых приглашениях сообщает колокольчик в шапке кабинета.</p>
              </div>
            </section>

            <section id="account" class="fsp-section">
              <h2 class="fsp-display u-h3 u-mb-20">Аккаунт</h2>
              <div class="fsp-stack-12">
                <FspInput v-model="email" label="Почта" hint="Почта из ФСП ID. Сменить её и пароль можно на странице входа ФСП ID." readonly />
                <p class="u-small" style="margin: 0;">Удалить аккаунт и все данные можно по запросу в поддержку: <a class="fsp-link" href="mailto:support@fsp-career.ru">support@fsp-career.ru</a>.</p>
              </div>
            </section>

            <div class="u-row-wrap set-actions">
              <span v-if="dirty" class="u-small" style="align-self: center;">Есть несохранённые изменения</span>
              <FspButton variant="ghost" href="/candidate/profile">К профилю</FspButton>
              <FspButton :disabled="saving" @click="saveSettings()">Сохранить</FspButton>
            </div>
          </div>
        </div>
      </ScreenState>
    </main>
  </div>
</template>

<style>
.set-nav { flex: 1 1 220px; display: flex; flex-direction: column; gap: 4px; position: sticky; top: 16px; }
.set-note { --cut: var(--cut-s); --fill: var(--surface-hover); padding: 16px 20px; margin-top: 20px; display: flex; gap: 12px; align-items: flex-start; font-size: 14px; line-height: 20px; }
.set-hits { position: absolute; left: 0; right: 0; z-index: 10; margin-top: 4px; background: var(--surface); box-shadow: 0 0 0 1px var(--line-strong); display: flex; flex-direction: column; }
.set-hits button { all: unset; cursor: pointer; padding: 10px 16px; font-size: 15px; }
.set-hits button:hover, .set-hits button:focus-visible { background: var(--surface-hover); }
.set-consent { display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: center; justify-content: space-between; padding: 16px 0; box-shadow: inset 0 1px 0 var(--line); }
.set-actions { justify-content: flex-end; padding-top: 16px; box-shadow: inset 0 1px 0 var(--line); }
@media (max-width: 960px) {
  .set-nav { position: static; flex-direction: row; flex-wrap: wrap; flex-basis: 100%; }
}
</style>
