<script setup lang="ts">
useHead({ title: 'Описание потребности — Карьера ФСП' })

const v = reactive((() => {
  return {
      yes: true, dots: 6,
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
const stack = ref(['Go', 'PostgreSQL', 'Kafka', 'Конкурентность'])
const tech = ref('')
function addTech() {
  const t = tech.value.trim()
  if (t && !stack.value.includes(t)) stack.value.push(t)
  tech.value = ''
}
function build() {
  show('Подборка сформирована: 24 кандидата из 3 категорий')
  navigateTo('/employer/pool')
}
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Для компаний" user="Код Сибири" :links="v.links" logo-dark="/brand/championship-logo-white.svg" logo-light="/brand/championship-logo-navy.svg" />

    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px;">
      <h1 class="fsp-display" style="font-size: 40px; line-height: 44px; margin-bottom: 8px;">Кого ищем</h1>
      <p style="margin: 0 0 32px; font-size: 16px; color: var(--text-muted);">Опишите потребность — соберём подборку из уже проверенных кандидатов. Вакансию публиковать не обязательно.</p>

      <div style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
        <form @submit.prevent="build" style="flex: 999 1 620px; min-width: 0; display: flex; flex-direction: column; gap: 28px;">
          <FspInput label="Название роли" default-value="Backend-разработчик в процессинг платежей" />

          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Специализация</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip :selected="v.yes">Backend</FspChip>
              <FspChip>Frontend</FspChip>
              <FspChip>Fullstack</FspChip>
              <FspChip>Mobile</FspChip>
              <FspChip>Data / ML</FspChip>
              <FspChip>DevOps</FspChip>
              <FspChip>QA</FspChip>
              <FspChip>Инфобез</FspChip>
            </div>
          </div>

          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Грейд</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspChip>Intern</FspChip>
              <FspChip>Junior</FspChip>
              <FspChip :selected="v.yes">Middle</FspChip>
              <FspChip :selected="v.yes">Senior</FspChip>
              <FspChip>Lead</FspChip>
            </div>
          </div>

          <div>
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Стек</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px;">
              <button v-for="t in stack" :key="t" type="button" :aria-label="'Убрать ' + t" style="all: unset; cursor: pointer;" @click="stack = stack.filter(x => x !== t)"><FspTag>{{ t }} ×</FspTag></button>
            </div>
            <FspInput v-model="tech" icon="search" placeholder="Добавить технологию — Enter" aria-label="Добавить технологию" @keydown.enter.prevent="addTech" />
          </div>

          <label style="display: flex; flex-direction: column; gap: 6px;">
            <span style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Чем занимается команда</span>
            <textarea rows="4" style="font: 400 16px/24px var(--font-sans); color: var(--text); background: var(--field); border: 1px solid var(--line-strong); padding: 12px 16px; resize: vertical;">Перестраиваем процессинг платежей: 3 тыс. транзакций в секунду, 6 разработчиков, релиз раз в неделю. Нужен человек, который возьмёт на себя антифрод-сервис.</textarea>
          </label>

          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 16px;">
            <FspInput label="Зарплата от" default-value="250 000" suffix="₽" />
            <FspInput label="Зарплата до" default-value="320 000" suffix="₽" />
            <div>
              <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 6px;">Формат</div>
              <div style="display: flex; flex-wrap: wrap; gap: 8px;"><FspChip :selected="v.yes">Удалённо</FspChip><FspChip>Гибрид</FspChip></div>
            </div>
          </div>
          <p style="margin: -12px 0 0; font-size: 13px; color: var(--text-muted);">Вилка обязательна: кандидат видит её до начала общения.</p>

          <FspCheckbox label="Поднимать выше кандидатов с достижениями ФСП" :default-checked="v.yes" />

          <div style="display: flex; flex-wrap: wrap; gap: 8px; padding-top: 20px; box-shadow: inset 0 1px 0 var(--line);">
            <FspButton size="lg" icon-right="arrow-right" type="submit">Сформировать подборку</FspButton>
            <FspButton size="lg" variant="ghost" toast="Черновик сохранён">Сохранить черновик</FspButton>
          </div>
        </form>

        <aside style="flex: 1 1 340px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
          <FspPlate :dots="v.dots">
            <div class="fsp-display" style="font-size: 18px; line-height: 22px;">Подходящие категории</div>
            <div style="font-size: 13px; color: var(--on-plate-muted); margin: 6px 0 20px;">Обновляется по мере заполнения</div>
            <div style="display: flex; flex-direction: column; gap: 16px;">
              <div style="display: flex; justify-content: space-between; gap: 12px; padding-bottom: 14px; box-shadow: inset 0 -1px 0 var(--on-plate-muted);"><div><div style="font-weight: 600;">Backend · Middle</div><div style="font-size: 13px; color: var(--on-plate-muted);">62 с достижениями ФСП</div></div><b class="fsp-display" style="font-size: 22px;">340</b></div>
              <div style="display: flex; justify-content: space-between; gap: 12px; padding-bottom: 14px; box-shadow: inset 0 -1px 0 var(--on-plate-muted);"><div><div style="font-weight: 600;">Backend · Senior</div><div style="font-size: 13px; color: var(--on-plate-muted);">27 с достижениями ФСП</div></div><b class="fsp-display" style="font-size: 22px;">118</b></div>
              <div style="display: flex; justify-content: space-between; gap: 12px;"><div><div style="font-weight: 600;">Fullstack · Middle</div><div style="font-size: 13px; color: var(--on-plate-muted);">смежная · 40% стека совпадает</div></div><b class="fsp-display" style="font-size: 22px;">205</b></div>
            </div>
          </FspPlate>
          <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line); font-size: 14px; line-height: 20px; color: var(--text-muted);">
            <div class="fsp-display" style="font-size: 16px; line-height: 20px; color: var(--text); margin-bottom: 10px;">Как строится подборка</div>
            Кандидаты попадают в категорию только по результатам опроса и теста — не по тексту резюме. Внутри категории выше те, у кого сильнее тест, свежее задания и есть подтверждённые достижения ФСП.
          </div>
        </aside>
      </div>
    </main>
  </div>
</template>
