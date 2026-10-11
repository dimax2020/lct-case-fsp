<script setup lang="ts">
import { read } from '~/utils/read'
useHead({ title: 'Профиль компании — Карьера ФСП' })

const v = { dots: 6, logo: 80, small: 52 }

const { show } = useToast()
const api = useApi()
const screen = useScreen(async () => read(api.GET('/api/v1/companies/me')))
const logoSrc = ref<string>()
const name = ref('')
const city = ref('')
const size = ref<string | number>('')
const about = ref('')
const contactName = ref('')
const contactEmail = ref('')
const contactPhone = ref('')
const website = ref('')
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
  website.value = company.website ?? ''
  logoSrc.value = company.logo ?? undefined
  for (const key of Object.keys(industries)) industries[key] = key === (company.industry ?? '')
}, { immediate: true })
const industryText = computed(() => Object.entries(industries).filter(([, on]) => on).map(([k]) => k).join(', ') || 'Направление не указано')
const logoInput = ref<HTMLInputElement>()

// Логотип уменьшается в браузере до 256 px и хранится в профиле компании как data URL.
async function onLogo(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  input.value = ''
  if (!f) return
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(f.type)) { show('Логотип — картинка PNG, JPEG или WebP'); return }
  try {
    const bitmap = await createImageBitmap(f)
    const scale = Math.min(1, 256 / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * scale))
    canvas.height = Math.max(1, Math.round(bitmap.height * scale))
    canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const data = canvas.toDataURL('image/png')
    if (data.length > 400_000) { show('Логотип слишком большой даже после сжатия'); return }
    logoSrc.value = data
    show('Логотип добавлен — не забудьте сохранить профиль')
  } catch {
    show('Не удалось прочитать картинку')
  }
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
        website: website.value.trim() || null,
        logo: logoSrc.value ?? null,
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
  <div class="fsp-shell">
    <FspHeader product="Для компаний" :user="name || 'Компания'" :links="employerLinks" />

    <main class="fsp-page">
      <h1 class="fsp-display fsp-title">Профиль компании</h1>
      <p style="margin: 0 0 32px; font-size: 16px; color: var(--text-muted);">Эти данные кандидат видит в каждом приглашении и вакансии.</p>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
      <div class="fsp-columns">
        <form @submit.prevent="save" style="flex: 999 1 620px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
          <div style="display: flex; flex-wrap: wrap; gap: 20px; align-items: center;">
            <FspCompanyLogo :name="name || '?'" :src="logoSrc" :size="v.logo" />
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <FspButton size="sm" variant="outline" @click="logoInput?.click()">Загрузить логотип</FspButton>
              <input ref="logoInput" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="onLogo">
              <span class="u-small">SVG или PNG, от 256×256</span>
            </div>
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 16px;">
            <FspInput v-model="name" label="Название" />
            <FspInput v-model="website" label="Сайт" placeholder="company.ru" inputmode="url" />
            <FspInput v-model="city" label="Город" icon="pin" />
            <FspInput v-model="size" label="Сотрудников" inputmode="numeric" />
          </div>
          <div>
            <div class="fsp-eyebrow u-mb-10">Направление деятельности</div>
            <div class="u-row-wrap">
              <FspChip v-for="(_, k) in industries" :key="k" v-model:selected="industries[k]">{{ k }}</FspChip>
            </div>
          </div>
          <label style="display: flex; flex-direction: column; gap: 6px;">
            <span class="fsp-eyebrow">О компании</span>
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
          <div class="fsp-eyebrow">Так вас видит кандидат</div>
          <FspPlate :dots="v.dots">
            <div style="display: flex; gap: 14px; align-items: center;">
              <FspCompanyLogo :name="name || '?'" :src="logoSrc" :size="v.small" />
              <div><div class="u-lead">{{ name }}</div><div style="font-size: 14px; color: var(--on-plate-muted);">{{ industryText }} · {{ city }} · {{ size }} человек</div></div>
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
