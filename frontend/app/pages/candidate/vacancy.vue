<script setup lang="ts">
useHead({ title: 'Страница вакансии — Карьера ФСП' })

const v = reactive((() => {
  return {
      yes: true, dots: 6, logo: 56,
      s1from: 220000, s1to: 280000, s2from: 240000,
      tags1: ['Go', 'PostgreSQL', { label: 'Алгоритмы', match: true }],
      tags2: ['Go', 'ClickHouse', 'Kafka'],
      links: [
        { label: 'Профиль', href: '/candidate/profile' },
        { label: 'Приглашения', href: '/candidate/invites' },
        { label: 'Грейд и тесты', href: '/candidate/grade' },
        { label: 'Вакансии', href: '/candidate/vacancy', active: true },
        { label: 'Настройки', href: '/candidate/settings' }
      ]
    };
})())

const { show } = useToast()
const applied = ref(false)
const saved = ref(false)
function apply() {
  applied.value = true
  show('Отклик отправлен — Код Сибири увидит ваш профиль и контакты')
}
function toggleSave() {
  saved.value = !saved.value
  show(saved.value ? 'Вакансия в избранном' : 'Вакансия убрана из избранного')
}
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Карьера" user="Алексей К." :unread="v.yes" :links="v.links" logo-dark="/brand/championship-logo-white.svg" logo-light="/brand/championship-logo-navy.svg" />

    <main style="max-width: 1240px; margin: 0 auto; padding: 32px 32px 64px;">
      <nav aria-label="Хлебные крошки" style="font-size: 14px; color: var(--text-muted); margin-bottom: 24px; display: flex; gap: 8px; flex-wrap: wrap;">
        <NuxtLink to="/candidate/invites" style="color: var(--text-muted); text-decoration: none;">Вакансии</NuxtLink><span>/</span><NuxtLink to="/candidate/invites" style="color: var(--text-muted); text-decoration: none;">Backend</NuxtLink><span>/</span><span style="color: var(--text);">Backend-разработчик (Go) в антифрод</span>
      </nav>

      <div style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
        <article style="flex: 999 1 640px; min-width: 0; display: flex; flex-direction: column; gap: 32px;">

          <header style="display: flex; flex-direction: column; gap: 16px;">
            <div style="display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
              <FspDisciplineBadge discipline="algo" />
              <FspTag>Middle · Senior</FspTag>
              <span style="font-size: 13px; color: var(--text-muted);">Опубликована 8 октября · 46 просмотров · 9 откликов</span>
            </div>
            <h1 style="margin: 0; font-size: 36px; line-height: 44px; font-weight: 700;">Backend-разработчик (Go) в антифрод</h1>
            <div style="display: flex; flex-wrap: wrap; gap: 16px; align-items: center;">
              <FspCompanyLogo name="Код Сибири" :size="v.logo" />
              <div><a href="#company" class="fsp-link" style="font-weight: 600; font-size: 17px;">Код Сибири</a><div style="font-size: 14px; color: var(--text-muted); margin-top: 4px;">Финтех · Новосибирск · 120 сотрудников</div></div>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px 24px; font-size: 15px; color: var(--text-muted);">
              <span style="display: inline-flex; gap: 6px; align-items: center;"><FspIcon name="remote" />Удалённо, часовой пояс МСК ±4</span>
              <span style="display: inline-flex; gap: 6px; align-items: center;"><FspIcon name="level" />Опыт от 3 лет</span>
              <span style="display: inline-flex; gap: 6px; align-items: center;"><FspIcon name="briefcase" />Полный день, ТК РФ</span>
            </div>
          </header>

          <section>
            <h2 class="fsp-display" style="font-size: 22px; line-height: 26px; margin-bottom: 14px;">О задаче</h2>
            <p style="margin: 0 0 12px; font-size: 16px; line-height: 26px;">Мы обрабатываем платежи 14 региональных банков — около 3 тысяч транзакций в секунду в пике. Сейчас антифрод работает на правилах, написанных пять лет назад, и пропускает новые схемы мошенничества. Строим новый сервис: потоковая обработка событий, скоринг в реальном времени, объяснимые решения для аналитиков банка.</p>
            <p style="margin: 0; font-size: 16px; line-height: 26px;">Ищем разработчика, который возьмёт на себя ядро скоринга: от проектирования схемы данных до выкатки в прод.</p>
          </section>

          <section>
            <h2 class="fsp-display" style="font-size: 22px; line-height: 26px; margin-bottom: 14px;">Чем предстоит заниматься</h2>
            <ul style="margin: 0; padding: 0 0 0 20px; display: flex; flex-direction: column; gap: 10px; font-size: 16px; line-height: 24px;">
              <li>Проектировать и писать сервис скоринга транзакций на Go с задержкой до 50 мс на p99</li>
              <li>Строить конвейер событий на Kafka: дедупликация, обогащение, окна агрегации</li>
              <li>Оптимизировать запросы и схему в PostgreSQL под 2 млрд строк истории</li>
              <li>Вместе с аналитиками превращать новые схемы мошенничества в правила и признаки</li>
              <li>Ревьюить код коллег и участвовать в дежурствах (раз в 6 недель, оплачиваются отдельно)</li>
            </ul>
          </section>

          <section style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 16px;">
            <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line);">
              <h2 class="fsp-display" style="font-size: 18px; line-height: 22px; margin-bottom: 14px;">Обязательно</h2>
              <ul style="list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; font-size: 15px; line-height: 22px;">
                <li style="display: flex; gap: 10px;"><span style="color: var(--success); flex: none;"><FspIcon name="check" /></span>Go от 2 лет в продакшене</li>
                <li style="display: flex; gap: 10px;"><span style="color: var(--success); flex: none;"><FspIcon name="check" /></span>Конкурентность: каналы, мьютексы, контексты</li>
                <li style="display: flex; gap: 10px;"><span style="color: var(--success); flex: none;"><FspIcon name="check" /></span>PostgreSQL: индексы, планы запросов, партиционирование</li>
                <li style="display: flex; gap: 10px;"><span style="color: var(--success); flex: none;"><FspIcon name="check" /></span>Kafka или другой брокер сообщений</li>
              </ul>
            </div>
            <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line);">
              <h2 class="fsp-display" style="font-size: 18px; line-height: 22px; margin-bottom: 14px;">Будет плюсом</h2>
              <ul style="list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; font-size: 15px; line-height: 22px;">
                <li style="display: flex; gap: 10px;"><span style="color: var(--danger); flex: none;"><FspIcon name="x" /></span>Kubernetes, Helm</li>
                <li style="display: flex; gap: 10px;"><span style="color: var(--success); flex: none;"><FspIcon name="check" /></span>Опыт олимпиад или соревнований по программированию</li>
                <li style="display: flex; gap: 10px;"><span style="color: var(--text-muted); flex: none;"><FspIcon name="chevron-down" /></span>Платёжные системы, антифрод</li>
                <li style="display: flex; gap: 10px;"><span style="color: var(--text-muted); flex: none;"><FspIcon name="chevron-down" /></span>ClickHouse</li>
              </ul>
              <div style="font-size: 13px; color: var(--text-muted); margin-top: 14px;">Отметки — сравнение с вашим подтверждённым профилем</div>
            </div>
          </section>

          <section>
            <h2 class="fsp-display" style="font-size: 22px; line-height: 26px; margin-bottom: 14px;">Стек</h2>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <FspTag :match="v.yes">Go 1.23</FspTag>
              <FspTag :match="v.yes">PostgreSQL 16</FspTag>
              <FspTag :match="v.yes">Kafka</FspTag>
              <FspTag>Redis</FspTag>
              <FspTag>gRPC</FspTag>
              <FspTag>Kubernetes</FspTag>
              <FspTag>Prometheus</FspTag>
              <FspTag>GitLab CI</FspTag>
            </div>
          </section>

          <section>
            <h2 class="fsp-display" style="font-size: 22px; line-height: 26px; margin-bottom: 14px;">Условия</h2>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 16px 32px; font-size: 15px; line-height: 22px;">
              <div><b>Деньги</b><div style="color: var(--text-muted);">250 000 – 320 000 ₽ на руки, пересмотр раз в полгода, годовой бонус до 2 окладов</div></div>
              <div><b>График</b><div style="color: var(--text-muted);">Удалённо, ядро команды 11:00–17:00 МСК, офис в Новосибирске по желанию</div></div>
              <div><b>Команда</b><div style="color: var(--text-muted);">6 разработчиков, 2 аналитика, тимлид; релиз раз в неделю</div></div>
              <div><b>Развитие</b><div style="color: var(--text-muted);">Бюджет на конференции, оплата участия в соревнованиях ФСП</div></div>
            </div>
          </section>

          <section>
            <h2 class="fsp-display" style="font-size: 22px; line-height: 26px; margin-bottom: 16px;">Как проходит отбор</h2>
            <ol style="list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 170px), 1fr)); gap: 8px;">
              <li style="padding: 16px 0; box-shadow: inset 0 3px 0 var(--accent-mark);"><div class="fsp-display" style="font-size: 18px;">01</div><div style="font-weight: 600; margin-top: 6px;">Отклик</div><div style="font-size: 13px; color: var(--text-muted);">ответ за 3 дня</div></li>
              <li style="padding: 16px 0; box-shadow: inset 0 3px 0 var(--line-strong);"><div class="fsp-display" style="font-size: 18px;">02</div><div style="font-weight: 600; margin-top: 6px;">Тех. интервью</div><div style="font-size: 13px; color: var(--text-muted);">60 минут с тимлидом</div></li>
              <li style="padding: 16px 0; box-shadow: inset 0 3px 0 var(--line-strong);"><div class="fsp-display" style="font-size: 18px;">03</div><div style="font-weight: 600; margin-top: 6px;">Встреча с командой</div><div style="font-size: 13px; color: var(--text-muted);">45 минут</div></li>
              <li style="padding: 16px 0; box-shadow: inset 0 3px 0 var(--line-strong);"><div class="fsp-display" style="font-size: 18px;">04</div><div style="font-weight: 600; margin-top: 6px;">Оффер</div><div style="font-size: 13px; color: var(--text-muted);">в течение 2 дней</div></li>
            </ol>
            <p style="margin: 12px 0 0; font-size: 14px; color: var(--text-muted);">Тестового задания нет: компания опирается на ваш тест на грейд и результаты ФСП.</p>
          </section>

          <section>
            <h2 class="fsp-display" style="font-size: 22px; line-height: 26px; margin-bottom: 16px;">Похожие вакансии</h2>
            <div style="display: flex; flex-direction: column; box-shadow: inset 0 1px 0 var(--line);">
              <FspVacancyCard variant="row" discipline="algo" posted="вчера" title="Go-разработчик в платёжную команду" company="Полярный Бит" :salary-from="v.s1from" :salary-to="v.s1to" city="Москва" format="Удалённо" experience="1–3 года" :tags="v.tags1" />
              <FspVacancyCard variant="row" discipline="infosec" posted="3 дня назад" title="Разработчик систем обнаружения мошенничества" company="Щит Лаб" :salary-from="v.s2from" city="Казань" format="Гибрид" experience="3–6 лет" :tags="v.tags2" />
            </div>
          </section>
        </article>

        <aside style="flex: 1 1 340px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
          <FspPlate :dots="v.dots">
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Зарплата</div>
            <div style="font-size: 30px; line-height: 36px; font-weight: 700; font-variant-numeric: tabular-nums; margin: 8px 0 4px;">250 000 – 320 000 ₽</div>
            <div style="font-size: 14px; color: var(--on-plate-muted); margin-bottom: 20px;">на руки, в месяц</div>
            <div style="display: flex; flex-direction: column; gap: 8px;">
              <FspButton v-if="!applied" size="lg" :block="v.yes" @click="apply">Откликнуться</FspButton>
              <div v-else style="display: flex; align-items: center; gap: 10px; min-height: 56px; font-weight: 600;"><span style="color: var(--active-success); display: inline-flex;"><FspIcon name="check" /></span>Отклик отправлен · ответ в течение 3 дней</div>
              <FspButton variant="ghost" :icon="saved ? 'bookmark-fill' : 'bookmark'" :block="v.yes" style="color: var(--on-plate);" :aria-pressed="saved" @click="toggleSave">{{ saved ? 'В избранном' : 'В избранное' }}</FspButton>
            </div>
          </FspPlate>

          <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <div style="display: flex; justify-content: space-between; align-items: baseline; gap: 12px;">
              <div class="fsp-display" style="font-size: 16px; line-height: 20px;">Ваше соответствие</div>
              <div class="fsp-display" style="font-size: 28px; line-height: 32px;">87%</div>
            </div>
            <div style="height: 8px; background: var(--surface-hover); margin: 14px 0 16px;"><div style="width: 87%; height: 8px; background: var(--success);"></div></div>
            <ul style="list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; font-size: 14px; line-height: 20px;">
              <li>Грейд Middle подтверждён · 82/100</li>
              <li>Все обязательные навыки подтверждены</li>
              <li>Опыт соревнований ФСП — в плюсах вакансии</li>
              <li style="color: var(--text-muted);">Kubernetes не подтверждён</li>
            </ul>
            <NuxtLink to="/candidate/onboarding" class="fsp-link" style="display: inline-block; margin-top: 14px; font-size: 14px; font-weight: 600;">Пройти мини-тест по Kubernetes · 10 мин</NuxtLink>
          </div>

          <div id="company" style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line); display: flex; flex-direction: column; gap: 10px; font-size: 14px; line-height: 20px;">
            <div class="fsp-display" style="font-size: 16px; line-height: 20px;">О компании</div>
            <span style="color: var(--text-muted);">Платёжный процессинг для региональных банков, на рынке с 2014 года.</span>
            <span>3 открытые вакансии · отвечает на отклики в среднем за 2 дня</span>
            <a href="#" class="fsp-link" style="font-weight: 600;" @click.prevent="show('У Кода Сибири 3 открытые вакансии — список появится в каталоге')">Все вакансии компании</a>
          </div>
        </aside>
      </div>
    </main>
  </div>
</template>
