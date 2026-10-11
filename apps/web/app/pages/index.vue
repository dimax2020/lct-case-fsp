<script setup lang="ts">
useHead({ title: 'Лендинг платформы — Карьера ФСП' })

const v = reactive((() => {
  return { dots: 6 };
})())
const { show } = useToast()
const mvp = () => show('Ещё не реализовано в рамках MVP')
const { data: sessionData, refresh: refreshSession } = await useFetch('/api/bff/session', {
  default: () => ({ authenticated: false as boolean, role: null as string | null, name: null as string | null }),
  credentials: 'include',
})
const session = computed(() => sessionData.value ?? { authenticated: false, role: null, name: null })
onMounted(() => { void refreshSession() })
const cabinetHref = computed(() => {
  if (session.value.role === 'employer') return '/employer/need'
  if (session.value.role === 'candidate') return '/candidate/profile'
  return '/auth/role?next=/candidate/profile'
})
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">

    <header style="display: flex; flex-wrap: wrap; align-items: center; gap: 24px; padding: 16px 32px; box-shadow: inset 0 -1px 0 var(--line);">
      <NuxtLink to="/" style="display: flex; align-items: center; gap: 16px; text-decoration: none; color: var(--text);">
        <img src="/brand/championship-logo-white.svg" alt="Чемпионат России" style="height: 36px; display: block;">
        <span style="font-family: var(--font-display); font-weight: 700; font-size: 13px; letter-spacing: .04em; text-transform: uppercase; padding-left: 16px; box-shadow: inset 1px 0 0 var(--line-strong); line-height: 28px;">Карьера</span>
      </NuxtLink>
      <nav aria-label="Разделы" style="display: flex; flex-wrap: wrap; gap: 24px; flex: 1 1 320px;">
        <a href="#problem" style="font-size: 15px; font-weight: 500; color: var(--text-muted); text-decoration: none;">Проблема</a>
        <a href="#match" style="font-size: 15px; font-weight: 500; color: var(--text-muted); text-decoration: none;">Матчинг</a>
        <a href="#how" style="font-size: 15px; font-weight: 500; color: var(--text-muted); text-decoration: none;">Как это работает</a>
        <a href="#fsp" style="font-size: 15px; font-weight: 500; color: var(--text-muted); text-decoration: none;">Достижения ФСП</a>
      </nav>
      <div style="display: flex; gap: 8px;">
        <template v-if="session.authenticated">
          <FspButton variant="ghost" size="sm" :href="cabinetHref">В кабинет</FspButton>
          <FspButton size="sm" href="/auth/keycloak/logout">Выйти</FspButton>
        </template>
        <template v-else>
          <FspButton variant="ghost" size="sm" href="/auth?mode=login">Войти</FspButton>
          <FspButton size="sm" href="/auth">Регистрация</FspButton>
        </template>
      </div>
    </header>

    <main style="max-width: 1240px; margin: 0 auto; padding: 0 32px;">

      <!-- Герой -->
      <section style="display: flex; flex-wrap: wrap; gap: 48px; align-items: center; padding: 72px 0 64px;">
        <div style="flex: 999 1 560px; min-width: 0;">
          <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 16px;">Платформа подбора ИТ-специалистов Федерации спортивного программирования</div>
          <h1 class="fsp-display" style="font-size: 64px; line-height: 66px;">Покажи, что ты лучший</h1>
          <p style="margin: 24px 0 32px; font-size: 18px; line-height: 28px; color: var(--text-muted); max-width: 640px;">Здесь решает не резюме, а результат. Подтверди грейд тестом, добавь победы на соревнованиях ФСП — и поднимайся в рейтинге своей категории. Компании видят лучших первыми и сами приходят с предложением и вилкой.</p>
          <div style="display: flex; flex-wrap: wrap; gap: 12px;">
            <FspButton v-if="session.authenticated" size="lg" icon-right="arrow-right" :href="cabinetHref">В кабинет</FspButton>
            <template v-else>
              <FspButton size="lg" icon-right="arrow-right" href="/auth">Пройти тест на грейд</FspButton>
              <FspButton size="lg" variant="plate" href="/auth?role=employer">Я нанимаю</FspButton>
            </template>
          </div>
        </div>
        <div style="flex: 1 1 380px; min-width: 0;">
          <FspPlate :dots="v.dots">
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Твой рейтинг в категории</div>
            <div class="fsp-display" style="font-size: 24px; line-height: 28px; margin-top: 10px;">Backend · Middle</div>
            <div style="display: flex; align-items: baseline; gap: 12px; margin: 18px 0 20px;">
              <span class="fsp-display" style="font-size: 64px; line-height: 60px;">№3</span>
              <span style="font-size: 15px; color: var(--on-plate-muted);">из 340 кандидатов</span>
            </div>
            <div style="display: flex; flex-direction: column; gap: 10px; font-size: 14px;">
              <div style="display: grid; grid-template-columns: 120px 1fr 36px; gap: 12px; align-items: center;"><span style="color: var(--on-plate-muted);">Тест на грейд</span><div style="height: 8px; background: var(--active-raised);"><div style="width: 91%; height: 8px; background: var(--active-success);"></div></div><b>91</b></div>
              <div style="display: grid; grid-template-columns: 120px 1fr 36px; gap: 12px; align-items: center;"><span style="color: var(--on-plate-muted);">Актуальность</span><div style="height: 8px; background: var(--active-raised);"><div style="width: 100%; height: 8px; background: var(--active-success);"></div></div><b>100</b></div>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 20px;">
              <FspDisciplineBadge discipline="algo">Призёр ЧР-2025</FspDisciplineBadge>
              <span style="font-size: 14px; color: var(--on-plate-muted);">4 приглашения за неделю</span>
            </div>
          </FspPlate>
        </div>
      </section>

      <!-- Проблема -->
      <section id="problem" style="padding: 56px 0; box-shadow: inset 0 1px 0 var(--line);">
        <div style="max-width: 760px; margin-bottom: 36px;">
          <h2 class="fsp-display" style="font-size: 32px; line-height: 36px;">Почему поиск работы в ИТ сломан</h2>
          <p style="margin: 14px 0 0; font-size: 17px; line-height: 26px; color: var(--text-muted);">Универсальные площадки рассчитаны сразу на все отрасли и уже не решают задачу ни одной из сторон. Издержки несут и компании, и кандидаты, а результат подбора остаётся минимальным.</p>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 270px), 1fr)); gap: 32px 24px;">
          <div style="padding-top: 20px; box-shadow: inset 0 1px 0 var(--line-strong); display: flex; flex-direction: column; gap: 10px;">
            <span class="fsp-display" style="font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 36px; height: 26px; display: inline-grid; place-items: center;">01</span>
            <h3 style="margin: 4px 0 0; font-size: 18px; line-height: 24px; font-weight: 600;">Сотни нерелевантных откликов</h3>
            <p style="margin: 0; font-size: 15px; line-height: 22px; color: var(--text-muted);">Работодатель вручную разбирает поток резюме силами дорогих технических специалистов.</p>
            <p style="margin: auto 0 0; padding-top: 8px; font-size: 14px; line-height: 20px;"><b>У нас:</b> компания получает готовую подборку из проверенной категории.</p>
          </div>
          <div style="padding-top: 20px; box-shadow: inset 0 1px 0 var(--line-strong); display: flex; flex-direction: column; gap: 10px;">
            <span class="fsp-display" style="font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 36px; height: 26px; display: inline-grid; place-items: center;">02</span>
            <h3 style="margin: 4px 0 0; font-size: 18px; line-height: 24px; font-weight: 600;">Отклики вслепую</h3>
            <p style="margin: 0; font-size: 15px; line-height: 22px; color: var(--text-muted);">Кандидат рассылает резюме и не получает обратной связи — ни ответа, ни понимания условий.</p>
            <p style="margin: auto 0 0; padding-top: 8px; font-size: 14px; line-height: 20px;"><b>У нас:</b> приглашение приходит само, вилка видна до начала общения.</p>
          </div>
          <div style="padding-top: 20px; box-shadow: inset 0 1px 0 var(--line-strong); display: flex; flex-direction: column; gap: 10px;">
            <span class="fsp-display" style="font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 36px; height: 26px; display: inline-grid; place-items: center;">03</span>
            <h3 style="margin: 4px 0 0; font-size: 18px; line-height: 24px; font-weight: 600;">Резюме ничего не доказывает</h3>
            <p style="margin: 0; font-size: 15px; line-height: 22px; color: var(--text-muted);">Стек и места работы не подтверждают практические навыки — отбор сводится к совпадению ключевых слов.</p>
            <p style="margin: auto 0 0; padding-top: 8px; font-size: 14px; line-height: 20px;"><b>У нас:</b> грейд подтверждается тестом, навыки — баллами и победами ФСП.</p>
          </div>
          <div style="padding-top: 20px; box-shadow: inset 0 1px 0 var(--line-strong); display: flex; flex-direction: column; gap: 10px;">
            <span class="fsp-display" style="font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 36px; height: 26px; display: inline-grid; place-items: center;">04</span>
            <h3 style="margin: 4px 0 0; font-size: 18px; line-height: 24px; font-weight: 600;">ИТ-специфика не учтена</h3>
            <p style="margin: 0; font-size: 15px; line-height: 22px; color: var(--text-muted);">Стек, грейд, роль в команде и формат работы не формализованы — выдача нерелевантна обеим сторонам.</p>
            <p style="margin: auto 0 0; padding-top: 8px; font-size: 14px; line-height: 20px;"><b>У нас:</b> сервис говорит на профессиональном языке ИТ.</p>
          </div>
        </div>
      </section>

      <!-- Матчинг -->
      <section id="match" style="padding: 56px 0; box-shadow: inset 0 1px 0 var(--line);">
        <div style="max-width: 760px; margin-bottom: 36px;">
          <h2 class="fsp-display" style="font-size: 32px; line-height: 36px;">Сложный матчинг вместо поиска по словам</h2>
          <p style="margin: 14px 0 0; font-size: 17px; line-height: 26px; color: var(--text-muted);">Мы сопоставляем десятки подтверждённых сигналов, чтобы компания точнее всего нашла сотрудника, а сотрудник — свою компанию. Каждое попадание в подборку объяснено.</p>
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 48px; align-items: flex-start;">
          <div style="flex: 999 1 560px; min-width: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr)); gap: 28px 24px;">
            <div style="padding-top: 16px; box-shadow: inset 0 1px 0 var(--line);"><div style="font-weight: 600; font-size: 16px;">Категория по тесту</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted); margin-top: 6px;">Специализация и грейд подтверждены тестированием, а не самоописанием в резюме.</div></div>
            <div style="padding-top: 16px; box-shadow: inset 0 1px 0 var(--line);"><div style="font-weight: 600; font-size: 16px;">Подтверждённый стек</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted); margin-top: 6px;">Навыки с баллами за задачи сравниваются с требованиями команды.</div></div>
            <div style="padding-top: 16px; box-shadow: inset 0 1px 0 var(--line);"><div style="font-weight: 600; font-size: 16px;">Достижения ФСП</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted); margin-top: 6px;">Результаты соревнований поднимают кандидата выше внутри категории.</div></div>
            <div style="padding-top: 16px; box-shadow: inset 0 1px 0 var(--line);"><div style="font-weight: 600; font-size: 16px;">Свежесть профиля</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted); margin-top: 6px;">Регулярные задания от работодателей дают актуальный сигнал о форме кандидата.</div></div>
            <div style="padding-top: 16px; box-shadow: inset 0 1px 0 var(--line);"><div style="font-weight: 600; font-size: 16px;">Задачи команды</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted); margin-top: 6px;">Описание потребности разбирает языковая модель и сопоставляет с опытом и ролями кандидата.</div></div>
            <div style="padding-top: 16px; box-shadow: inset 0 1px 0 var(--line);"><div style="font-weight: 600; font-size: 16px;">Условия обеих сторон</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted); margin-top: 6px;">Вилка, формат, город и ожидания совпадают ещё до первого сообщения.</div></div>
          </div>

          <div class="fsp-cut fsp-active" style="flex: 1 1 380px; min-width: 0; --cut: var(--cut-l); padding: 28px;">
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Пример объяснения подборки</div>
            <div style="display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin: 10px 0 18px;">
              <div style="font-size: 18px; font-weight: 600;">Алексей К. → Backend в процессинг</div>
              <span class="fsp-display" style="font-size: 28px;">94%</span>
            </div>
            <div style="display: flex; flex-direction: column; gap: 12px; font-size: 14px;">
              <div style="display: grid; grid-template-columns: 130px 1fr 52px; gap: 12px; align-items: center;"><span>Категория</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 100%; height: 8px; background: var(--success);"></div></div><b style="text-align: right;">✓</b></div>
              <div style="display: grid; grid-template-columns: 130px 1fr 52px; gap: 12px; align-items: center;"><span>Стек</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 100%; height: 8px; background: var(--success);"></div></div><b style="text-align: right;">4 / 4</b></div>
              <div style="display: grid; grid-template-columns: 130px 1fr 52px; gap: 12px; align-items: center;"><span>Тест</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 82%; height: 8px; background: var(--success);"></div></div><b style="text-align: right;">82</b></div>
              <div style="display: grid; grid-template-columns: 130px 1fr 52px; gap: 12px; align-items: center;"><span>Задачи команды</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 71%; height: 8px; background: var(--warning);"></div></div><b style="text-align: right;">71</b></div>
              <div style="display: grid; grid-template-columns: 130px 1fr 52px; gap: 12px; align-items: center;"><span>Условия</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 100%; height: 8px; background: var(--success);"></div></div><b style="text-align: right;">✓</b></div>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 20px; padding-top: 16px; box-shadow: inset 0 1px 0 var(--line);">
              <FspDisciplineBadge discipline="algo">ФСП · 2 место ЧР</FspDisciplineBadge>
              <span style="font-size: 13px; color: var(--text-muted);">+ поднят выше в категории</span>
            </div>
          </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr)); gap: 24px; margin-top: 48px;">
          <div style="padding-top: 20px; box-shadow: inset 0 2px 0 var(--accent-mark);">
            <div class="fsp-display" style="font-size: 16px; line-height: 20px;">Компании</div>
            <p style="margin: 10px 0 0; font-size: 15px; line-height: 22px; color: var(--text-muted);">Подборка ранжирована по силе подтверждённого профиля и совпадению с потребностью. Уточняйте фильтры, не теряя исходную выдачу.</p>
          </div>
          <div style="padding-top: 20px; box-shadow: inset 0 2px 0 var(--accent-mark);">
            <div class="fsp-display" style="font-size: 16px; line-height: 20px;">Кандидату</div>
            <p style="margin: 10px 0 0; font-size: 15px; line-height: 22px; color: var(--text-muted);">Приглашения — только от компаний, которым подходит твой профиль. Подсказки покажут, что улучшить, чтобы попасть в больше подборок.</p>
          </div>
        </div>
      </section>

      <!-- Как это работает -->
      <section id="how" style="padding: 56px 0; box-shadow: inset 0 1px 0 var(--line);">
        <h2 class="fsp-display" style="font-size: 32px; line-height: 36px; margin-bottom: 32px;">Как это работает</h2>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 520px), 1fr)); gap: 24px;">

          <div id="cand" class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 32px;">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 24px;">
              <h3 class="fsp-display" style="font-size: 20px; line-height: 24px;">Кандидату</h3>
              <FspButton size="sm" variant="outline" href="/auth">Начать</FspButton>
            </div>
            <ol style="list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 20px;">
              <li style="display: flex; gap: 16px;"><span style="font-family: var(--font-display); font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 36px; height: 26px; flex: none; display: inline-grid; place-items: center;">01</span><div><div style="font-weight: 600;">Профиль за 2 минуты</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Загрузи PDF-резюме — стек, роли и стаж распознаются автоматически.</div></div></li>
              <li style="display: flex; gap: 16px;"><span style="font-family: var(--font-display); font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 36px; height: 26px; flex: none; display: inline-grid; place-items: center;">02</span><div><div style="font-weight: 600;">Опрос и тест на грейд</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Выбираешь специализацию и уровень, решаешь задачи под свой грейд.</div></div></li>
              <li style="display: flex; gap: 16px;"><span style="font-family: var(--font-display); font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 36px; height: 26px; flex: none; display: inline-grid; place-items: center;">03</span><div><div style="font-weight: 600;">Место в рейтинге категории</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Чем сильнее результат и достижения ФСП, тем выше ты в выдаче.</div></div></li>
              <li style="display: flex; gap: 16px;"><span style="font-family: var(--font-display); font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 36px; height: 26px; flex: none; display: inline-grid; place-items: center;">04</span><div><div style="font-weight: 600;">Приглашения с вилкой</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Принимаешь или отклоняешь. Контакты открываются только после «да».</div></div></li>
            </ol>
          </div>

          <div id="emp" class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 32px;">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 24px;">
              <h3 class="fsp-display" style="font-size: 20px; line-height: 24px;">Работодателю</h3>
              <FspButton size="sm" variant="outline" href="/auth?role=employer">Найти команду</FspButton>
            </div>
            <ol style="list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 20px;">
              <li style="display: flex; gap: 16px;"><span style="font-family: var(--font-display); font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 36px; height: 26px; flex: none; display: inline-grid; place-items: center;">01</span><div><div style="font-weight: 600;">Опиши потребность</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Специализация, грейд, стек и чем занимается команда.</div></div></li>
              <li style="display: flex; gap: 16px;"><span style="font-family: var(--font-display); font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 36px; height: 26px; flex: none; display: inline-grid; place-items: center;">02</span><div><div style="font-weight: 600;">Получи подборку лучших</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Подходящие категории и кандидаты, отсортированные по силе подтверждённого профиля.</div></div></li>
              <li style="display: flex; gap: 16px;"><span style="font-family: var(--font-display); font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 36px; height: 26px; flex: none; display: inline-grid; place-items: center;">03</span><div><div style="font-weight: 600;">Смотри, почему кандидат в топе</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Результаты тестов, совпадение стека и достижения ФСП — с пояснением.</div></div></li>
              <li style="display: flex; gap: 16px;"><span style="font-family: var(--font-display); font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 36px; height: 26px; flex: none; display: inline-grid; place-items: center;">04</span><div><div style="font-weight: 600;">Пригласи с вилкой</div><div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Без обязательной вакансии. Статус приглашения видно сразу.</div></div></li>
            </ol>
          </div>
        </div>
      </section>

      <!-- ФСП -->
      <section id="fsp" style="padding: 24px 0 56px;">
        <div class="fsp-cut" style="--cut: var(--cut-xl); --fill: var(--plate); color: var(--on-plate); padding: 48px; display: flex; flex-wrap: wrap; gap: 32px; align-items: center;">
          <div style="flex: 999 1 480px; min-width: 0;">
            <h2 class="fsp-display" style="font-size: 28px; line-height: 32px;">Спортивный опыт — в карьерное преимущество</h2>
            <p style="margin: 16px 0 24px; font-size: 16px; line-height: 24px; color: var(--on-plate-muted); max-width: 640px;">Свяжи профиль с ФСП ID — результаты соревнований подтянутся автоматически и станут объективным подтверждением навыков. Нет истории ФСП? Профиль строится по тестам, ты не теряешь в выдаче.</p>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspDisciplineBadge discipline="product" />
              <FspDisciplineBadge discipline="algo" />
              <FspDisciplineBadge discipline="uav" />
              <FspDisciplineBadge discipline="robot" />
              <FspDisciplineBadge discipline="infosec" />
            </div>
          </div>
          <img src="/brand/fsp-star-dark.svg" alt="" aria-hidden="true" style="width: 160px; height: 160px; flex: none;">
        </div>
      </section>

      <!-- Принципы -->
      <section style="padding: 0 0 64px; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 24px;">
        <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line);">
          <div class="fsp-display" style="font-size: 16px; line-height: 20px; margin-bottom: 8px;">Вилка всегда видна</div>
          <div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Зарплата «от–до» в рублях обязательна в каждой вакансии и каждом приглашении.</div>
        </div>
        <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line);">
          <div class="fsp-display" style="font-size: 16px; line-height: 20px; margin-bottom: 8px;">Контакты — с твоего согласия</div>
          <div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Работодатель видит телефон и почту, только когда ты принял приглашение или откликнулся сам.</div>
        </div>
        <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line);">
          <div class="fsp-display" style="font-size: 16px; line-height: 20px; margin-bottom: 8px;">Грейд не понижают</div>
          <div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Не прошёл тест — пробуешь уровень ниже. Справился уверенно — повышаешь. Не чаще раза в 3 месяца.</div>
        </div>
      </section>
    </main>

    <footer style="box-shadow: inset 0 1px 0 var(--line); padding: 32px;">
      <div style="max-width: 1240px; margin: 0 auto; display: flex; flex-wrap: wrap; gap: 24px; align-items: center; justify-content: space-between;">
        <img src="/brand/fsp-logo-full-dark.svg" alt="Федерация спортивного программирования России" style="height: 36px;">
        <div style="display: flex; flex-wrap: wrap; gap: 24px; font-size: 14px;">
          <a href="#" class="fsp-link" @click.prevent="mvp">Политика обработки данных</a>
          <a href="#" class="fsp-link" @click.prevent="mvp">Пользовательское соглашение</a>
          <a href="#" class="fsp-link" @click.prevent="mvp">Поддержка</a>
        </div>
      </div>
    </footer>
  </div>
</template>
