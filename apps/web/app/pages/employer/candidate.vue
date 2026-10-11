<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'

type Channel = components['schemas']['ContactChannel']

useHead({ title: 'Профиль кандидата для работодателя — Карьера ФСП' })
const route = useRoute()
const { show } = useToast()
const api = useApi()
const needId = computed(() => String(route.query.need || rememberedNeed() || ''))
const candidateId = computed(() => String(route.query.candidate || ''))

const screen = useScreen(async () => {
  if (!needId.value || !candidateId.value) return { card: null, need: null, company: null }
  const [card, need, company] = await Promise.all([
    read(api.GET('/api/v1/needs/{id}/candidates/{candidate_id}', { params: { path: { id: needId.value, candidate_id: candidateId.value } } })),
    read(api.GET('/api/v1/needs/{id}', { params: { path: { id: needId.value } } })),
    read(api.GET('/api/v1/companies/me')),
  ])
  return { card, need, company }
})

const title = ref('')
const message = ref('')
const salaryFrom = ref<string | number>('')
const salaryTo = ref<string | number>('')
const channel = ref<Channel>('email')
const contact = ref('')
const deadline = ref('')
const err = ref('')

watch(screen.data, (bundle) => {
  if (!bundle?.need) return
  title.value = bundle.need.title
  salaryFrom.value = bundle.need.salary_from
  salaryTo.value = bundle.need.salary_to
  message.value = bundle.need.description.slice(0, 400)
  contact.value = bundle.company?.recruiter_contact?.email || ''
}, { immediate: true })

const card = computed(() => screen.data.value?.card ?? null)
const companyName = computed(() => screen.data.value?.company?.name || 'Компания')

async function send() {
  err.value = ''
  const from = parseMoney(salaryFrom.value)
  const to = parseMoney(salaryTo.value)
  if (!Number.isFinite(from) || !Number.isFinite(to) || !from || !to) {
    err.value = 'Вилка обязательна — кандидат видит её до начала общения'
    return
  }
  if (!contact.value.trim()) { err.value = 'Укажите контакт'; return }
  if (!card.value || !needId.value) return
  try {
    await read(api.POST('/api/v1/invitations', {
      body: {
        need_id: needId.value,
        candidate_id: card.value.candidate_id,
        title: title.value.trim() || 'Приглашение',
        message: message.value,
        salary_from: from,
        salary_to: to,
        contact_channel: channel.value,
        contact_value: contact.value.trim(),
        deadline: deadline.value ? new Date(deadline.value).toISOString() : null,
      },
    }))
    show(`Приглашение отправлено: ${card.value.display_name}`)
    await navigateTo('/employer/invites')
  } catch (e) {
    err.value = e instanceof Error ? e.message : 'Не удалось отправить'
  }
}
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Для компаний" :user="companyName" :links="employerLinks" logo-dark="/brand/championship-logo-white.svg" logo-light="/brand/championship-logo-navy.svg" />
    <main style="max-width: 1240px; margin: 0 auto; padding: 32px 32px 64px;">
      <NuxtLink to="/employer/pool" style="display: inline-block; font-size: 14px; color: var(--text-muted); text-decoration: none; margin-bottom: 20px;">← Подборка</NuxtLink>
      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <p v-if="!needId || !candidateId" style="color: var(--text-muted);">Откройте кандидата из подборки.</p>
        <div v-else-if="card" style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
          <div style="flex: 999 1 600px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
            <section style="display: flex; flex-wrap: wrap; gap: 20px; align-items: center;">
              <FspCompanyLogo :name="card.display_name" :size="80" />
              <div>
                <h1 style="margin: 0; font-size: 30px; line-height: 38px;">{{ card.display_name }}</h1>
                <div style="font-size: 15px; color: var(--text-muted); margin-top: 4px;">{{ card.category }}<template v-if="card.experience_years != null"> · опыт {{ card.experience_years }}</template><template v-if="card.city"> · {{ card.city }}</template></div>
              </div>
            </section>
            <section style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 12px;">
              <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--plate); color: var(--on-plate); padding: 20px;"><div style="font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Категория</div><div class="fsp-display" style="font-size: 20px; margin-top: 8px;">{{ card.category }}</div></div>
              <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px;"><div style="font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Соответствие</div><div class="fsp-display" style="font-size: 20px; margin-top: 8px;">{{ card.match }}%</div></div>
              <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px;"><div style="font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Тест</div><div class="fsp-display" style="font-size: 20px; margin-top: 8px;">{{ card.test_score ?? '—' }}</div></div>
            </section>
            <section class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--accent-mark); --bw: var(--border-card); padding: 28px;">
              <h2 class="fsp-display" style="font-size: 18px; margin-bottom: 14px;">Почему в подборке</h2>
              <ul style="margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 10px;">
                <li v-for="line in card.explanations ?? []" :key="line" style="display: flex; gap: 10px;"><FspIcon name="check" /><span>{{ line }}</span></li>
              </ul>
            </section>
            <section v-if="card.skills?.length" style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspTag v-for="s in card.skills" :key="s">{{ skillLabel(s) }}</FspTag>
            </section>
            <section v-if="card.fsp_badge" style="display: flex; gap: 8px; align-items: center;">
              <FspDisciplineBadge :discipline="card.fsp_badge.discipline">{{ card.fsp_badge.text }}</FspDisciplineBadge>
            </section>
            <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line); display: flex; gap: 16px; align-items: center;">
              <FspIcon name="user" :size="28" />
              <div v-if="card.contacts_revealed"><b>{{ card.email }}</b><div style="font-size: 14px; color: var(--text-muted);">{{ card.phone }}</div></div>
              <div v-else><b>Контакты скрыты</b><div style="font-size: 14px; color: var(--text-muted); margin-top: 4px;">Телефон и почта откроются, когда кандидат примет приглашение.</div></div>
            </section>
          </div>
          <aside class="fsp-cut fsp-active" style="flex: 1 1 380px; min-width: 0; --cut: var(--cut-l); padding: 28px; display: flex; flex-direction: column; gap: 18px;">
            <h2 class="fsp-display" style="font-size: 20px;">Приглашение</h2>
            <FspStatusBadge v-if="card.invitation_status" :status="inviteTone(card.invitation_status)">{{ inviteLabel(card.invitation_status) }}</FspStatusBadge>
            <FspInput v-model="title" label="Должность" />
            <label style="display: flex; flex-direction: column; gap: 6px;">
              <span style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Предложение</span>
              <textarea v-model="message" rows="5" style="font: 400 15px/22px var(--font-sans); color: var(--text); background: var(--field); border: 1px solid var(--line-strong); padding: 12px 14px; resize: vertical;" />
            </label>
            <div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px;">
              <FspInput v-model="salaryFrom" label="Зарплата от" suffix="₽" />
              <FspInput v-model="salaryTo" label="до" suffix="₽" />
            </div>
            <div>
              <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">Способ связи</div>
              <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px;">
                <FspChip v-for="c in (['email', 'phone', 'telegram'] as Channel[])" :key="c" :selected="channel === c" locked @click="channel = c">{{ c === 'email' ? 'Почта' : c === 'phone' ? 'Телефон' : 'Telegram' }}</FspChip>
              </div>
              <FspInput v-model="contact" aria-label="Контакт рекрутера" />
            </div>
            <FspInput v-model="deadline" label="Ответить до" type="date" icon="clock" />
            <div v-if="err" style="font-size: 13px; color: var(--danger);">{{ err }}</div>
            <FspButton size="lg" :block="true" :disabled="!!card.invitation_status && card.invitation_status !== 'declined'" @click="send">Отправить приглашение</FspButton>
          </aside>
        </div>
      </ScreenState>
    </main>
  </div>
</template>
