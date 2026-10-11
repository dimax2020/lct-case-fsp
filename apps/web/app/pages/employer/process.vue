<script setup lang="ts">
import type { components } from '~/api/schema'
import { read } from '~/utils/read'
import {
  createEmployerPractice,
  listEmployerPractices,
  localDeadline,
  localToIso,
  readPracticeHash,
  safeReturnPath,
  withQuery,
  type EpaPractice,
} from '~/utils/epa'

type Inv = components['schemas']['InvitationOut']

useHead({ title: 'Тестовые задания — Карьера ФСП' })
const cabinetUser = useCabinetUser('Компания')
const route = useRoute()
const { show } = useToast()
const api = useApi()
const back = computed(() => safeReturnPath(route.query.return))

const title = ref('')
const deadline = ref('')
const creating = ref(false)
const createError = ref('')
const openId = ref('')

const screen = useScreen(async () => {
  const [list, session] = await Promise.all([
    read(api.GET('/api/v1/invitations', { params: { query: { role: 'employer' } } })),
    $fetch<{ name?: string | null }>('/api/bff/session'),
  ])
  const name = session.name || ''
  let templates: EpaPractice[] = []
  let practicesError = ''
  try {
    if (name) templates = await listEmployerPractices(name)
  } catch {
    practicesError = 'Сервис заданий не ответил. Обновите страницу.'
  }
  return { list, name, templates, practicesError }
})

const templates = computed(() => screen.data.value?.templates ?? [])
const invitations = computed(() => screen.data.value?.list.items ?? [])
const usedBy = (id: string) => invitations.value.filter(item => item.practice_id === id)
const backHref = computed(() => openId.value && back.value ? withQuery(back.value, 'practice', openId.value) : back.value)

function openTemplate(id: string) {
  openId.value = id
  if (import.meta.client) location.hash = `practice=${encodeURIComponent(id)}`
}

onMounted(() => {
  deadline.value = localDeadline(7)
  const fromHash = readPracticeHash(window.location.hash)
  if (fromHash) openId.value = fromHash
})

async function create() {
  createError.value = ''
  const name = screen.data.value?.name
  if (!name) {
    createError.value = 'Не удалось определить имя для сервиса заданий'
    return
  }
  if (title.value.trim().length < 3) {
    createError.value = 'Название — минимум 3 символа'
    return
  }
  creating.value = true
  try {
    const created = await createEmployerPractice(name, {
      title: title.value.trim(),
      deadline: localToIso(deadline.value || localDeadline(7)),
    })
    title.value = ''
    deadline.value = localDeadline(7)
    show(`Шаблон «${created.title}» создан`)
    await screen.load()
    openTemplate(created.id)
    if (back.value) show('Задание уже можно прикрепить к приглашению. Ниже можно сразу загрузить zip и ТЗ.')
  } catch (e) {
    createError.value = e instanceof Error ? e.message : 'Не удалось создать задание'
  } finally {
    creating.value = false
  }
}

function inviteLine(inv: Inv) {
  const who = inv.candidate_display_name || 'Кандидат'
  return `${who} · ${inviteLabel(inv.status)}`
}
</script>

<template>
  <div class="fsp-shell">
    <FspHeader product="Для компаний" :user="cabinetUser" :links="employerLinks" />
    <main class="fsp-page">
      <h1 class="fsp-display fsp-title">Тестовые задания</h1>
      <p class="u-note" style="margin: 0 0 24px;">Шаблон создаёте один раз. К приглашению прикрепляете его — кандидат после принятия получает свою копию.</p>
      <div class="u-row-wrap" style="margin: 0 0 28px; gap: 16px;">
        <div style="display: flex; gap: 10px; align-items: flex-start; flex: 1 1 160px;">
          <span class="fsp-step-num">1</span>
          <div><div class="u-strong">Шаблон</div><div class="u-note">Название, дедлайн, zip и ТЗ</div></div>
        </div>
        <div style="display: flex; gap: 10px; align-items: flex-start; flex: 1 1 160px;">
          <span class="fsp-step-num">2</span>
          <div><div class="u-strong">Приглашение</div><div class="u-note">Прикрепляете шаблон кандидату</div></div>
        </div>
        <div style="display: flex; gap: 10px; align-items: flex-start; flex: 1 1 160px;">
          <span class="fsp-step-num">3</span>
          <div><div class="u-strong">Выполнение</div><div class="u-note">Кандидат видит задание после принятия</div></div>
        </div>
        <div style="display: flex; gap: 10px; align-items: flex-start; flex: 1 1 160px;">
          <span class="fsp-step-num">4</span>
          <div><div class="u-strong">Проверка</div><div class="u-note">Открываете шаблон и смотрите копии</div></div>
        </div>
      </div>

      <section v-if="back" class="fsp-cut fsp-card" style="margin-bottom: 24px;">
        <div class="fsp-eyebrow">Возврат к приглашению</div>
        <p class="u-note" style="margin: 8px 0 16px;">Создайте шаблон или выберите готовый — он сразу подставится в шаг 2 на карточке кандидата.</p>
        <FspButton :href="backHref">{{ openId ? 'Прикрепить это задание' : 'Вернуться без задания' }}</FspButton>
      </section>

      <ScreenState :phase="screen.phase.value" :error="screen.error.value" @retry="screen.load">
        <div class="fsp-columns">
          <section style="flex: 1 1 380px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
            <div class="fsp-cut fsp-card">
              <h2 class="fsp-display u-h3">Новый шаблон</h2>
              <p class="u-note" style="margin: 8px 0 16px;">Дальше откроется редактор: zip проекта и текст ТЗ. Приглашение ещё не уходит.</p>
              <div class="fsp-stack-16">
                <FspInput v-model="title" label="Название" placeholder="Kafka consumer без потери сообщений" />
                <FspInput v-model="deadline" label="Дедлайн" type="datetime-local" icon="clock" />
                <p v-if="createError" class="u-danger" style="margin: 0;">{{ createError }}</p>
                <FspButton :disabled="creating" @click="create">{{ creating ? 'Создаём…' : 'Создать и открыть' }}</FspButton>
              </div>
            </div>
            <p v-if="screen.data.value?.practicesError" class="u-note">{{ screen.data.value.practicesError }}</p>
            <p v-else-if="!templates.length" class="u-muted">Готовых шаблонов пока нет.</p>
            <button
              v-for="item in templates"
              :key="item.id"
              type="button"
              :class="['fsp-cut', openId === item.id && 'fsp-active']"
              :style="openId === item.id
                ? '--cut: var(--cut-m); padding: 20px; text-align: left; font: inherit; border: 0; cursor: pointer; width: 100%;'
                : '--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px; text-align: left; font: inherit; border: 0; background: none; cursor: pointer; width: 100%;'"
              @click="openTemplate(item.id)"
            >
              <div class="u-strong">{{ item.title }}</div>
              <div class="u-note-sm u-mt-4">Дедлайн {{ shortDate(item.deadline) }}</div>
              <div v-if="usedBy(item.id).length" class="u-note-sm u-mt-4">
                В приглашениях: {{ usedBy(item.id).map(inviteLine).join('; ') }}
              </div>
              <div v-else class="u-note-sm u-mt-4">Ещё не прикрепляли к приглашению</div>
            </button>
          </section>
          <article style="flex: 999 1 640px; min-width: 0;">
            <p v-if="!openId" class="u-muted">Выберите шаблон слева или создайте новый — здесь откроется ТЗ, архив и кто уже выполняет копию.</p>
            <ProcessDesk v-else :key="openId" role="employer" :practice-id="openId" />
          </article>
        </div>
      </ScreenState>
    </main>
  </div>
</template>
