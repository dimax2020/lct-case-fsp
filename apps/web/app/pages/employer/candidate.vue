<script setup lang="ts">
useHead({ title: 'Профиль кандидата для работодателя — Карьера ФСП' })

const v = reactive((() => {
  return {
      yes: true, av: 80, ic: 28,
      links: [
        { label: 'Подборка', href: '/employer/need', active: true },
        { label: 'Банк кандидатов', href: '/employer/pool' },
        { label: 'Приглашения', href: '/employer/invites' },
        { label: 'Вакансии', href: '#' },
        { label: 'Компания', href: '/employer/company' }
      ]
    };
})())

const { show } = useToast()
const salaryFrom = ref('250 000')
const salaryTo = ref('320 000')
const channel = ref('Telegram')
const contacts: Record<string, string> = { Telegram: '@kodsib_hr', 'Почта': 'hr@kodsib.ru', 'Телефон': '+7 383 000-00-00' }
const contact = ref(contacts.Telegram)
watch(channel, c => { contact.value = contacts[c] ?? '' })
const err = ref('')
function send() {
  if (!salaryFrom.value || !salaryTo.value) { err.value = 'Вилка обязательна — кандидат видит её до начала общения'; return }
  err.value = ''
  show('Приглашение отправлено Алексею К.')
  navigateTo('/employer/invites')
}
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Для компаний" user="Код Сибири" :links="v.links" logo-dark="/brand/championship-logo-white.svg" logo-light="/brand/championship-logo-navy.svg" />

    <main style="max-width: 1240px; margin: 0 auto; padding: 32px 32px 64px;">
      <NuxtLink to="/employer/pool" style="display: inline-block; font-size: 14px; color: var(--text-muted); text-decoration: none; margin-bottom: 20px;">← Подборка «Backend в процессинг платежей»</NuxtLink>

      <div style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
        <div style="flex: 999 1 600px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
          <section style="display: flex; flex-wrap: wrap; gap: 20px; align-items: center;">
            <FspCompanyLogo name="Алексей Кузнецов" :size="v.av" />
            <div style="flex: 1 1 300px; min-width: 0;">
              <h1 style="margin: 0; font-size: 30px; line-height: 38px; font-weight: 700;">Алексей К.</h1>
              <div style="font-size: 15px; color: var(--text-muted); margin-top: 4px;">Опыт 4 года · Новосибирск · готов к удалёнке · ожидания от 240 000 ₽</div>
            </div>
          </section>

          <section style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 12px;">
            <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--plate); color: var(--on-plate); padding: 20px;"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Категория</div><div class="fsp-display" style="font-size: 20px; line-height: 24px; margin-top: 8px;">Backend · Middle</div></div>
            <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px;"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Соответствие</div><div class="fsp-display" style="font-size: 20px; line-height: 24px; margin-top: 8px;">94%</div></div>
            <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 20px;"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">В категории</div><div class="fsp-display" style="font-size: 20px; line-height: 24px; margin-top: 8px;">12 из 340</div></div>
          </section>

          <section class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); --edge: var(--accent-mark); --bw: var(--border-card); padding: 28px;">
            <h2 class="fsp-display" style="font-size: 18px; line-height: 22px; margin-bottom: 14px;">Почему в подборке</h2>
            <ul style="margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 10px; font-size: 15px; line-height: 22px;">
              <li style="display: flex; gap: 10px;"><FspIcon name="check" /><span>Грейд Middle подтверждён тестом 10.10.2026: 82/100</span></li>
              <li style="display: flex; gap: 10px;"><FspIcon name="check" /><span>Совпадает весь требуемый стек: Go, PostgreSQL, Kafka, конкурентность</span></li>
              <li style="display: flex; gap: 10px;"><FspIcon name="check" /><span>2 место на Чемпионате России 2025 по алгоритмическому программированию</span></li>
              <li style="display: flex; gap: 10px;"><FspIcon name="check" /><span>Ожидания по зарплате попадают в вашу вилку</span></li>
            </ul>
          </section>

          <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <h2 class="fsp-display" style="font-size: 18px; line-height: 22px; margin-bottom: 18px;">Результаты теста по темам</h2>
            <div style="display: flex; flex-direction: column; gap: 12px;">
              <div style="display: grid; grid-template-columns: 180px 1fr 40px; gap: 16px; align-items: center; font-size: 15px;"><span>Алгоритмы</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 91%; height: 8px; background: var(--success);"></div></div><b>91</b></div>
              <div style="display: grid; grid-template-columns: 180px 1fr 40px; gap: 16px; align-items: center; font-size: 15px;"><span>Go</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 88%; height: 8px; background: var(--success);"></div></div><b>88</b></div>
              <div style="display: grid; grid-template-columns: 180px 1fr 40px; gap: 16px; align-items: center; font-size: 15px;"><span>PostgreSQL</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 81%; height: 8px; background: var(--success);"></div></div><b>81</b></div>
              <div style="display: grid; grid-template-columns: 180px 1fr 40px; gap: 16px; align-items: center; font-size: 15px;"><span>Конкурентность</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 76%; height: 8px; background: var(--warning);"></div></div><b>76</b></div>
              <div style="display: grid; grid-template-columns: 180px 1fr 40px; gap: 16px; align-items: center; font-size: 15px;"><span>Проектирование API</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 69%; height: 8px; background: var(--warning);"></div></div><b>69</b></div>
            </div>
            <div style="font-size: 13px; color: var(--text-muted); margin-top: 16px;">Последнее задание работодателя: 15.09.2026 · подход принят</div>
          </section>

          <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <h2 class="fsp-display" style="font-size: 18px; line-height: 22px; margin-bottom: 18px;">Достижения ФСП</h2>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 12px;">
              <div style="display: flex; flex-direction: column; gap: 6px; padding: 16px; background: var(--surface-hover);"><FspDisciplineBadge discipline="algo" /><b style="margin-top: 4px;">Чемпионат России 2025 — 2 место</b><span style="font-size: 13px; color: var(--text-muted);">командный зачёт · 214 команд</span></div>
              <div style="display: flex; flex-direction: column; gap: 6px; padding: 16px; background: var(--surface-hover);"><FspDisciplineBadge discipline="product" /><b style="margin-top: 4px;">Кубок России 2024 — финалист</b><span style="font-size: 13px; color: var(--text-muted);">хакатон 48 часов</span></div>
            </div>
          </section>

          <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line); display: flex; gap: 16px; align-items: center; flex-wrap: wrap;">
            <FspIcon name="user" :size="v.ic" />
            <div style="flex: 1 1 320px;"><b>Контакты скрыты</b><div style="font-size: 14px; line-height: 20px; color: var(--text-muted); margin-top: 4px;">Телефон, почта и полное имя откроются, когда кандидат примет приглашение.</div></div>
            <FspButton variant="outline" size="sm" toast="PDF-профиль кандидата скачивается">Скачать PDF-профиль</FspButton>
          </section>
        </div>

        <aside class="fsp-cut fsp-active" style="flex: 1 1 380px; min-width: 0; --cut: var(--cut-l); padding: 28px; display: flex; flex-direction: column; gap: 18px;">
          <h2 class="fsp-display" style="font-size: 20px; line-height: 24px;">Приглашение</h2>
          <FspInput label="Вакансия" default-value="Без привязки к вакансии" hint="Можно выбрать опубликованную вакансию" />
          <FspInput label="Должность" default-value="Backend-разработчик (Go)" />
          <label style="display: flex; flex-direction: column; gap: 6px;">
            <span style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Предложение</span>
            <textarea rows="5" style="font: 400 15px/22px var(--font-sans); color: var(--text); background: var(--field); border: 1px solid var(--line-strong); padding: 12px 14px; resize: vertical;">Перестраиваем процессинг платежей и ищем человека в антифрод. Ваш результат по алгоритмам и опыт соревнований — то, что нужно. Команда 6 человек, релиз раз в неделю.</textarea>
          </label>
          <div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px;">
            <FspInput v-model="salaryFrom" label="Зарплата от" suffix="₽" :error="err && !salaryFrom ? ' ' : undefined" />
            <FspInput v-model="salaryTo" label="до" suffix="₽" :error="err && !salaryTo ? ' ' : undefined" />
          </div>
          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">Способ связи</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px;"><FspChip v-for="c in ['Telegram', 'Почта', 'Телефон']" :key="c" :selected="channel === c" locked @click="channel = c">{{ c }}</FspChip></div>
            <FspInput v-model="contact" aria-label="Контакт рекрутера" />
          </div>
          <FspInput label="Ответить до" default-value="24.10.2026" icon="clock" />
          <div v-if="err" style="font-size: 13px; color: var(--danger);">{{ err }}</div>
          <FspButton size="lg" :block="v.yes" @click="send">Отправить приглашение</FspButton>
          <p style="margin: 0; font-size: 13px; line-height: 18px; color: var(--text-muted);">Кандидат сразу увидит вилку, описание и компанию. Статус приглашения — в разделе «Приглашения».</p>
        </aside>
      </div>
    </main>
  </div>
</template>
