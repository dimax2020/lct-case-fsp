<script setup lang="ts">
import { read } from '~/utils/read'
useHead({ title: 'Профиль компании — Карьера ФСП' })

const v = reactive((() => {
  return {
      yes: true, dots: 6, logo: 80, small: 52,
      links: [
        { label: 'Подборка', href: '/employer/need' },
        { label: 'Банк кандидатов', href: '/employer/pool' },
        { label: 'Приглашения', href: '/employer/invites' },
        { label: 'Вакансии', href: '#' },
        { label: 'Компания', href: '/employer/company', active: true }
      ]
    };
})())

const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => read(api.GET('/api/v1/companies/me')))
const name = ref('')
const city = ref('')
const size = ref<string | number>('')
const about = ref('')
const contactName = ref('')
const contactEmail = ref('')
const contactPhone = ref('')
const industries = reactive<Record<string, boolean>>({ 'Финтех': false, 'E-commerce': false, 'Госсектор': false, 'Промышленность': false, 'Игры': false, 'Кибербезопасность': false })
watch(screen.data, (company) => {
  if (!company) return
  name.value = company.name
  city.value = company.city ?? ''
  size.value = company.size ?? ''
  about.value = company.about ?? ''
  contactName.value = company.recruiter_contact?.name ?? ''
  contactEmail.value = company.recruiter_contact?.email ?? ''
  contactPhone.value = company.recruiter_contact?.phone ?? ''
  for (const key of Object.keys(industries)) industries[key] = key === (company.industry ?? '')
}, { immediate: true })
const industryText = computed(() => Object.entries(industries).filter(([, on]) => on).map(([k]) => k).join(', ') || 'Направление не указано')
const logoSrc = ref<string>()
const logoInput = ref<HTMLInputElement>()
function onLogo(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  logoSrc.value = URL.createObjectURL(f)
  show('Логотип загружен')
}
async function save() {
  if (!name.value.trim()) { show('Укажите название компании'); return }
  const picked = Object.entries(industries).filter(([, on]) => on).map(([k]) => k).join(', ')
  try {
    const next = await read(api.PUT('/api/v1/companies/me', {
      body: {
        name: name.value.trim(),
        city: city.value || null,
        size: String(size.value || '') || null,
        industry: picked || null,
        about: about.value || null,
        recruiter_contact: { name: contactName.value || null, email: contactEmail.value || null, phone: contactPhone.value || null },
        benefits: screen.data.value?.benefits ?? [],
      },
    }))
    if (screen.data.value) screen.data.value = next
    show('Профиль компании сохранён')
  } catch (e) {
    show(e instanceof Error ? e.message : 'Не удалось сохранить компанию')
  }
}
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Для компаний" :user="name || 'Компания'" :links="employerLinks" logo-dark="/brand/championship-logo-white.svg" logo-light="/brand/championship-logo-navy.svg" />

    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px;">
      <h1 class="fsp-display" style="font-size: 40px; line-height: 44px; margin-bottom: 8px;">Профиль компании</h1>
      <p style="margin: 0 0 32px; font-size: 16px; color: var(--text-muted);">Эти данные кандидат видит в каждом приглашении и вакансии.</p>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
      <div style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
        <form @submit.prevent="save" style="flex: 999 1 620px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
          <div style="display: flex; flex-wrap: wrap; gap: 20px; align-items: center;">
            <FspCompanyLogo :name="name || '?'" :src="logoSrc" :size="v.logo" />
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <FspButton size="sm" variant="outline" @click="logoInput?.click()">Загрузить логотип</FspButton>
              <input ref="logoInput" type="file" accept="image/svg+xml,image/png" hidden @change="onLogo">
              <span style="font-size: 13px; color: var(--text-muted);">SVG или PNG, от 256×256</span>
            </div>
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 16px;">
            <FspInput v-model="name" label="Название" />
            <FspInput label="Сайт" default-value="kodsib.ru" />
            <FspInput v-model="city" label="Город" icon="pin" />
            <FspInput v-model="size" label="Сотрудников" inputmode="numeric" />
          </div>
          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Направление деятельности</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip v-for="(_, k) in industries" :key="k" v-model:selected="industries[k]">{{ k }}</FspChip>
            </div>
          </div>
          <label style="display: flex; flex-direction: column; gap: 6px;">
            <span style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">О компании</span>
            <textarea rows="4" style="font: 400 16px/24px var(--font-sans); color: var(--text); background: var(--field); border: 1px solid var(--line-strong); padding: 12px 16px; resize: vertical;" v-model="about" />
          </label>
          <div style="padding-top: 20px; box-shadow: inset 0 1px 0 var(--line);">
            <div class="fsp-display" style="font-size: 16px; line-height: 20px; margin-bottom: 16px;">Контакты для кандидатов</div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 16px;">
              <FspInput v-model="contactName" label="Контактное лицо" />
              <FspInput v-model="contactEmail" label="Почта" />
              <FspInput v-model="contactPhone" label="Телефон" />
            </div>
          </div>
          <div style="display: flex; gap: 8px; justify-content: flex-end;">
            <FspButton variant="ghost" href="/employer/need">Отменить</FspButton>
            <FspButton type="submit">Сохранить</FspButton>
          </div>
        </form>

        <aside style="flex: 1 1 340px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
          <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Так вас видит кандидат</div>
          <FspPlate :dots="v.dots">
            <div style="display: flex; gap: 14px; align-items: center;">
              <FspCompanyLogo :name="name || '?'" :src="logoSrc" :size="v.small" />
              <div><div style="font-size: 18px; font-weight: 600;">{{ name }}</div><div style="font-size: 14px; color: var(--on-plate-muted);">{{ industryText }} · {{ city }} · {{ size }} человек</div></div>
            </div>
            <p style="margin: 16px 0 0; font-size: 14px; line-height: 20px;">{{ about }}</p>
          </FspPlate>
          <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line); font-size: 14px; line-height: 20px; color: var(--text-muted);">
            <div class="fsp-display" style="font-size: 16px; line-height: 20px; color: var(--text); margin-bottom: 8px;">Проверенная компания</div>
            Скоро: подтверждение по ИНН и отметка «Проверено ФСП» — защита кандидатов от фиктивных вакансий.
          </div>
        </aside>
      </div>
      </ScreenState>
    </main>
  </div>
</template>
