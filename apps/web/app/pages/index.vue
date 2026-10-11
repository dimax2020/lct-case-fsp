<script setup lang="ts">
useHead({ title: 'Лендинг платформы: Карьера ФСП' })

const v = reactive((() => {
  return { dots: 6 };
})())
const { theme, toggle: toggleTheme } = useTheme()
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
  <div class="fsp-shell land">
    <a class="land-skip" href="#top">К содержанию</a>

    <header class="fsp-header land-header">
      <NuxtLink to="/" class="fsp-header-brand">
        <img src="/brand/fsp-star-dark.svg" alt="ФСП, на главную" class="fsp-only-dark">
        <img src="/brand/fsp-star-light.svg" alt="ФСП, на главную" class="fsp-only-light">
        <span class="fsp-header-product">Карьера</span>
      </NuxtLink>
      <nav class="fsp-header-nav" aria-label="Разделы">
        <a href="#problem">Проблема</a>
        <a href="#match">Матчинг</a>
        <a href="#how">Как это работает</a>
        <a href="#fsp">Достижения ФСП</a>
      </nav>
      <div class="fsp-header-actions">
        <FspButton variant="ghost" size="sm" :icon="theme === 'light' ? 'moon' : 'sun'" :aria-label="theme === 'light' ? 'Тёмная тема' : 'Светлая тема'" @click="toggleTheme" />
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

    <main id="top" class="land-main">

      <section class="land-hero">
        <div class="land-hero-grid">
          <div class="land-hero-copy">
            <p class="land-kicker land-rise">Платформа подбора ИТ-специалистов Федерации спортивного программирования</p>
            <h1 class="fsp-display land-title land-rise">Покажи, что ты<br><span class="land-mark">лучший</span></h1>
            <p class="land-lead land-rise"><span class="land-hook">Здесь решает не резюме, а результат.</span> Подтверди грейд тестом, добавь победы на соревнованиях ФСП и поднимайся в рейтинге своей категории. Компании видят лучших первыми и сами приходят с предложением и вилкой.</p>
            <div class="land-actions land-rise">
              <FspButton v-if="session.authenticated" size="lg" icon-right="arrow-right" :href="cabinetHref">В кабинет</FspButton>
              <template v-else>
                <FspButton size="lg" icon-right="arrow-right" href="/auth">Пройти тест на грейд</FspButton>
                <FspButton size="lg" variant="plate" href="/auth?role=employer">Я нанимаю</FspButton>
              </template>
            </div>
          </div>
          <div class="land-hero-aside land-rise">
            <FspPlate class="land-rank" :dots="v.dots">
              <div class="fsp-eyebrow fsp-eyebrow--plate">Твой рейтинг в категории</div>
              <div class="fsp-display land-rank-place">Backend, Middle</div>
              <div class="land-rank-score">
                <span class="fsp-display land-rank-num">№3</span>
                <span class="land-rank-of">из 340 кандидатов</span>
              </div>
              <div class="land-bars">
                <div class="land-bar"><span>Тест на грейд</span><div class="land-track"><i style="--w: 91%"></i></div><b>91</b></div>
                <div class="land-bar"><span>Актуальность</span><div class="land-track"><i style="--w: 100%"></i></div><b>100</b></div>
              </div>
              <div class="land-rank-foot">
                <FspDisciplineBadge discipline="algo">Призёр ЧР-2025</FspDisciplineBadge>
                <span class="land-rank-note">4 приглашения за неделю</span>
              </div>
            </FspPlate>
          </div>
        </div>
      </section>

      <section id="problem" class="land-section">
        <div class="land-section-head">
          <h2 class="fsp-display u-h2">Почему поиск работы в ИТ сломан</h2>
          <p>Универсальные площадки рассчитаны сразу на все отрасли и уже не решают задачу ни одной из сторон. Издержки несут и компании, и кандидаты, а результат подбора остаётся минимальным.</p>
        </div>
        <div class="land-problems">
          <div class="land-problem">
            <span class="fsp-step-num">01</span>
            <h3>Сотни нерелевантных откликов</h3>
            <p>Работодатель вручную разбирает поток резюме силами дорогих технических специалистов.</p>
            <p class="land-payoff"><span class="land-payoff-tag">У нас</span> компания получает готовую подборку из проверенной категории.</p>
          </div>
          <div class="land-problem">
            <span class="fsp-step-num">02</span>
            <h3>Отклики вслепую</h3>
            <p>Кандидат рассылает резюме и не получает обратной связи: ни ответа, ни понимания условий.</p>
            <p class="land-payoff"><span class="land-payoff-tag">У нас</span> приглашение приходит само, вилка видна до начала общения.</p>
          </div>
          <div class="land-problem">
            <span class="fsp-step-num">03</span>
            <h3>Резюме ничего не доказывает</h3>
            <p>Стек и места работы не подтверждают практические навыки. Отбор сводится к совпадению ключевых слов.</p>
            <p class="land-payoff"><span class="land-payoff-tag">У нас</span> грейд подтверждается тестом, а навыки баллами за задачи и победами ФСП.</p>
          </div>
          <div class="land-problem">
            <span class="fsp-step-num">04</span>
            <h3>ИТ-специфика не учтена</h3>
            <p>Стек, грейд, роль в команде и формат работы не формализованы, поэтому выдача нерелевантна обеим сторонам.</p>
            <p class="land-payoff"><span class="land-payoff-tag">У нас</span> сервис говорит на профессиональном языке ИТ.</p>
          </div>
        </div>
      </section>

      <section id="match" class="land-section">
        <div class="land-section-head">
          <h2 class="fsp-display u-h2">Сложный матчинг вместо поиска по словам</h2>
          <p>Мы сопоставляем десятки подтверждённых сигналов, чтобы компания точнее нашла сотрудника, а сотрудник нашёл свою компанию. Каждое попадание в подборку объяснено.</p>
        </div>
        <div class="land-match">
          <div class="land-signals">
            <div class="fsp-divider"><div class="u-strong-16">Категория по тесту</div><div class="u-note u-mt-6">Специализация и грейд подтверждены тестированием, а не самоописанием в резюме.</div></div>
            <div class="fsp-divider"><div class="u-strong-16">Подтверждённый стек</div><div class="u-note u-mt-6">Навыки с баллами за задачи сравниваются с требованиями команды.</div></div>
            <div class="fsp-divider"><div class="u-strong-16">Достижения ФСП</div><div class="u-note u-mt-6">Результаты соревнований поднимают кандидата выше внутри категории.</div></div>
            <div class="fsp-divider"><div class="u-strong-16">Свежесть профиля</div><div class="u-note u-mt-6">Регулярные задания от работодателей дают актуальный сигнал о форме кандидата.</div></div>
            <div class="fsp-divider"><div class="u-strong-16">Задачи команды</div><div class="u-note u-mt-6">Описание потребности разбирает языковая модель и сопоставляет с опытом и ролями кандидата.</div></div>
            <div class="fsp-divider"><div class="u-strong-16">Условия обеих сторон</div><div class="u-note u-mt-6">Вилка, формат, город и ожидания совпадают ещё до первого сообщения.</div></div>
          </div>

          <div class="fsp-cut fsp-active land-explain">
            <div class="fsp-eyebrow">Пример объяснения подборки</div>
            <div class="land-explain-top">
              <div class="u-lead">Алексей К. → Backend, процессинг</div>
              <span class="land-score">94%</span>
            </div>
            <div class="land-explain-rows">
              <div class="land-meter"><span>Категория</span><div class="fsp-meter"><i style="--w: 100%"></i></div><b class="u-right">✓</b></div>
              <div class="land-meter"><span>Стек</span><div class="fsp-meter"><i style="--w: 100%"></i></div><b class="u-right">4 / 4</b></div>
              <div class="land-meter"><span>Тест</span><div class="fsp-meter"><i style="--w: 82%"></i></div><b class="u-right">82</b></div>
              <div class="land-meter"><span>Задачи команды</span><div class="fsp-meter"><i style="--w: 71%; --tone: var(--warning)"></i></div><b class="u-right">71</b></div>
              <div class="land-meter"><span>Условия</span><div class="fsp-meter"><i style="--w: 100%"></i></div><b class="u-right">✓</b></div>
            </div>
            <div class="land-explain-foot">
              <FspDisciplineBadge discipline="algo">ФСП, 2 место ЧР</FspDisciplineBadge>
              <span class="u-small">+ поднят выше в категории</span>
            </div>
          </div>
        </div>

        <div class="land-audiences">
          <div class="land-audience">
            <h3 class="fsp-display">Компании</h3>
            <p>Подборка ранжирована по силе подтверждённого профиля и совпадению с потребностью. Уточняйте фильтры, не теряя исходную выдачу.</p>
          </div>
          <div class="land-audience">
            <h3 class="fsp-display">Кандидату</h3>
            <p>Приглашения приходят только от компаний, которым подходит твой профиль. Подсказки покажут, что улучшить, чтобы попасть в больше подборок.</p>
          </div>
        </div>
      </section>

      <section id="how" class="land-section">
        <h2 class="fsp-display u-h2 land-how-title">Как это работает</h2>
        <div class="land-paths">
          <div id="cand" class="fsp-cut land-path land-path--lead">
            <div class="land-path-head">
              <h3 class="fsp-display u-h3">Кандидату</h3>
              <FspButton v-if="session.authenticated" size="sm" :href="cabinetHref">В кабинет</FspButton>
              <FspButton v-else size="sm" href="/auth">Пройти тест на грейд</FspButton>
            </div>
            <ol class="land-steps">
              <li class="u-row-16"><span class="fsp-step-num">01</span><div><div class="u-strong">Профиль за 2 минуты</div><div class="u-note">Загрузи PDF-резюме. Стек, роли и стаж распознаются автоматически.</div></div></li>
              <li class="u-row-16"><span class="fsp-step-num">02</span><div><div class="u-strong">Опрос и тест на грейд</div><div class="u-note">Выбираешь специализацию и уровень, решаешь задачи под свой грейд.</div></div></li>
              <li class="u-row-16"><span class="fsp-step-num">03</span><div><div class="u-strong">Место в рейтинге категории</div><div class="u-note">Чем сильнее результат и достижения ФСП, тем выше ты в выдаче.</div></div></li>
              <li class="u-row-16"><span class="fsp-step-num">04</span><div><div class="u-strong">Приглашения с вилкой</div><div class="u-note">Принимаешь или отклоняешь. Контакты открываются только после согласия.</div></div></li>
            </ol>
          </div>

          <div id="emp" class="fsp-cut land-path">
            <div class="land-path-head">
              <h3 class="fsp-display u-h3">Работодателю</h3>
              <FspButton v-if="session.authenticated" size="sm" variant="outline" :href="cabinetHref">В кабинет</FspButton>
              <FspButton v-else size="sm" variant="outline" href="/auth?role=employer">Я нанимаю</FspButton>
            </div>
            <ol class="land-steps">
              <li class="u-row-16"><span class="fsp-step-num">01</span><div><div class="u-strong">Опиши потребность</div><div class="u-note">Специализация, грейд, стек и чем занимается команда.</div></div></li>
              <li class="u-row-16"><span class="fsp-step-num">02</span><div><div class="u-strong">Получи подборку лучших</div><div class="u-note">Подходящие категории и кандидаты, отсортированные по силе подтверждённого профиля.</div></div></li>
              <li class="u-row-16"><span class="fsp-step-num">03</span><div><div class="u-strong">Смотри, почему кандидат в топе</div><div class="u-note">Результаты тестов, совпадение стека и достижения ФСП. У каждого пункта есть пояснение.</div></div></li>
              <li class="u-row-16"><span class="fsp-step-num">04</span><div><div class="u-strong">Пригласи с вилкой и заданием</div><div class="u-note">Кандидат не откликается сам. К приглашению можно сразу прикрепить тестовое.</div></div></li>
            </ol>
          </div>
        </div>
      </section>

      <section id="fsp" class="land-fsp">
        <div class="fsp-cut land-fsp-plate">
          <div class="land-fsp-copy">
            <h2 class="fsp-display land-fsp-title">Спортивный опыт становится карьерным преимуществом</h2>
            <p>Свяжи профиль с ФСП ID. Результаты соревнований подтянутся автоматически и станут объективным подтверждением навыков. Нет истории ФСП? Профиль строится по тестам, ты не теряешь в выдаче.</p>
            <div class="u-row-wrap">
              <FspDisciplineBadge discipline="product" />
              <FspDisciplineBadge discipline="algo" />
              <FspDisciplineBadge discipline="uav" />
              <FspDisciplineBadge discipline="robot" />
              <FspDisciplineBadge discipline="infosec" />
            </div>
          </div>
          <img src="/brand/fsp-star-dark.svg" alt="" class="land-fsp-star">
        </div>
      </section>

      <section class="land-principles" aria-label="Принципы">
        <div class="land-principle">
          <h3 class="fsp-display">Вилка всегда видна</h3>
          <div class="u-note">Зарплата «от-до» в рублях обязательна в каждой вакансии и каждом приглашении.</div>
        </div>
        <div class="land-principle">
          <h3 class="fsp-display">Контакты только с твоего согласия</h3>
          <div class="u-note">Работодатель видит телефон и почту, только когда ты принял приглашение.</div>
        </div>
        <div class="land-principle">
          <h3 class="fsp-display">Грейд не понижают</h3>
          <div class="u-note">Не сдал тест? Проходишь уровень ниже. Справился уверенно? Грейд повышается. Не чаще раза в 3 месяца.</div>
        </div>
      </section>

      <section class="land-close">
        <div>
          <h2 class="fsp-display u-h2">Компании видят лучших первыми</h2>
          <p>Пройди тест на грейд или опиши потребность команды. Вилка видна до первого сообщения.</p>
        </div>
        <div class="land-actions">
          <FspButton v-if="session.authenticated" size="lg" icon-right="arrow-right" :href="cabinetHref">В кабинет</FspButton>
          <template v-else>
            <FspButton size="lg" icon-right="arrow-right" href="/auth">Пройти тест на грейд</FspButton>
            <FspButton size="lg" variant="plate" href="/auth?role=employer">Я нанимаю</FspButton>
          </template>
        </div>
      </section>
    </main>

    <footer class="land-footer">
      <div class="land-footer-inner">
        <img src="/brand/fsp-logo-full-dark.svg" alt="Федерация спортивного программирования России" class="fsp-only-dark">
        <img src="/brand/fsp-logo-full-light.svg" alt="Федерация спортивного программирования России" class="fsp-only-light">
        <div class="land-footer-links">
          <NuxtLink to="/legal/privacy" class="fsp-link">Политика обработки данных</NuxtLink>
          <NuxtLink to="/legal/terms" class="fsp-link">Условия публикации профиля</NuxtLink>
          <a href="mailto:support@fsp-career.ru" class="fsp-link">Поддержка</a>
        </div>
      </div>
    </footer>
  </div>
</template>
