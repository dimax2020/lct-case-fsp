<script setup lang="ts">
useHead({ title: 'Категория и грейд — Карьера ФСП' })

const v = reactive((() => {
  return {
      yes: true, dots: 6,
      links: [
        { label: 'Профиль', href: '/candidate/profile' },
        { label: 'Приглашения', href: '/candidate/invites' },
        { label: 'Грейд и тесты', href: '/candidate/grade', active: true },
        { label: 'Вакансии', href: '/candidate/vacancy' },
        { label: 'Настройки', href: '/candidate/settings' }
      ]
    };
})())
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Карьера" user="Алексей К." :unread="v.yes" :links="v.links" logo-dark="/brand/championship-logo-white.svg" logo-light="/brand/championship-logo-navy.svg" />

    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px; display: flex; flex-direction: column; gap: 32px;">
      <div>
        <h1 class="fsp-display" style="font-size: 40px; line-height: 44px; margin-bottom: 8px;">Категория и грейд</h1>
        <p style="margin: 0; font-size: 16px; color: var(--text-muted);">Категорию видят работодатели. Она складывается из специализации и грейда, подтверждённого тестом.</p>
      </div>

      <section style="display: flex; flex-wrap: wrap; gap: 16px;">
        <div style="flex: 1 1 420px; min-width: 0;">
          <FspPlate :dots="v.dots">
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr)); gap: 20px;">
              <div><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Отрасль</div><div style="font-size: 18px; font-weight: 600; margin-top: 6px;">ИТ · разработка</div></div>
              <div><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Специализация</div><div style="font-size: 18px; font-weight: 600; margin-top: 6px;">Backend</div></div>
              <div><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Грейд</div><div class="fsp-display" style="font-size: 22px; line-height: 26px; margin-top: 6px;">Middle</div></div>
            </div>
            <div style="margin-top: 20px; font-size: 14px; color: var(--on-plate-muted);">Подтверждён 10.10.2026 · 82 из 100 · место 12 из 340 в категории</div>
          </FspPlate>
        </div>
        <div class="fsp-cut" style="flex: 1 1 360px; min-width: 0; --cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 32px; display: flex; flex-direction: column; gap: 12px;">
          <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Следующая смена грейда</div>
          <div class="fsp-display" style="font-size: 28px; line-height: 32px;">с 10 января</div>
          <div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Менять грейд можно не чаще раза в 3 месяца. До этой даты профиль обновляют короткие задания от работодателей.</div>
        </div>
      </section>

      <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
        <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 24px;">Лестница грейдов · Backend</h2>
        <ol style="list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr)); gap: 8px;">
          <li style="padding: 16px; box-shadow: inset 0 3px 0 var(--success);"><div style="font-weight: 600;">Intern</div><div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">пройден</div></li>
          <li style="padding: 16px; box-shadow: inset 0 3px 0 var(--success);"><div style="font-weight: 600;">Junior</div><div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">пройден</div></li>
          <li class="fsp-cut" style="--cut: var(--cut-s); --fill: var(--accent-mark); color: #ffffff; padding: 16px;"><div style="font-weight: 600;">Middle</div><div style="font-size: 13px; margin-top: 4px;">текущий</div></li>
          <li style="padding: 16px; box-shadow: inset 0 3px 0 var(--warning);"><div style="font-weight: 600;">Senior</div><div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">тест с 10 января</div></li>
          <li style="padding: 16px; box-shadow: inset 0 3px 0 var(--line-strong);"><div style="font-weight: 600;">Lead</div><div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">после Senior</div></li>
        </ol>
        <div style="display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; align-items: center;">
          <FspButton :disabled="v.yes" icon-right="arrow-right" title="Доступно с 10 января">Тест на Senior</FspButton>
          <FspButton variant="outline" href="/candidate/onboarding">Тест на Junior</FspButton>
          <FspButton variant="ghost" href="/candidate/onboarding" toast="Опрос по специализации начат заново">Сменить специализацию</FspButton>
        </div>
      </section>

      <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
        <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 20px;">История опроса и тестов</h2>
        <div style="overflow-x: auto;">
          <table style="width: 100%; min-width: 720px; border-collapse: collapse; font-size: 15px;">
            <thead>
              <tr style="text-align: left; color: var(--text-muted); font-size: 12px; letter-spacing: .06em; text-transform: uppercase;">
                <th style="padding: 0 16px 12px 0; font-weight: 600;">Дата</th><th style="padding: 0 16px 12px 0; font-weight: 600;">Этап</th><th style="padding: 0 16px 12px 0; font-weight: 600;">Заявлено</th><th style="padding: 0 16px 12px 0; font-weight: 600;">Результат</th><th style="padding: 0 0 12px; font-weight: 600;">Итог</th>
              </tr>
            </thead>
            <tbody>
              <tr style="box-shadow: inset 0 1px 0 var(--line);"><td style="padding: 14px 16px 14px 0;">10.10.2026</td><td style="padding: 14px 16px 14px 0;">Тест · 12 заданий</td><td style="padding: 14px 16px 14px 0;">Middle</td><td style="padding: 14px 16px 14px 0; font-weight: 600;">82 / 100</td><td style="padding: 14px 0;"><FspStatusBadge status="new">Грейд подтверждён</FspStatusBadge></td></tr>
              <tr style="box-shadow: inset 0 1px 0 var(--line);"><td style="padding: 14px 16px 14px 0;">10.10.2026</td><td style="padding: 14px 16px 14px 0;">Опрос по специализации</td><td style="padding: 14px 16px 14px 0;">Backend</td><td style="padding: 14px 16px 14px 0;">18 ответов</td><td style="padding: 14px 0;"><FspStatusBadge status="archived">Сохранён</FspStatusBadge></td></tr>
              <tr style="box-shadow: inset 0 1px 0 var(--line);"><td style="padding: 14px 16px 14px 0;">02.07.2026</td><td style="padding: 14px 16px 14px 0;">Тест · 12 заданий</td><td style="padding: 14px 16px 14px 0;">Senior</td><td style="padding: 14px 16px 14px 0; font-weight: 600;">58 / 100</td><td style="padding: 14px 0;"><FspStatusBadge status="review">Не хватило — предложен Middle</FspStatusBadge></td></tr>
              <tr style="box-shadow: inset 0 1px 0 var(--line);"><td style="padding: 14px 16px 14px 0;">15.09.2026</td><td style="padding: 14px 16px 14px 0;">Задание работодателя</td><td style="padding: 14px 16px 14px 0;">—</td><td style="padding: 14px 16px 14px 0;">Подход принят</td><td style="padding: 14px 0;"><FspStatusBadge status="new">+4% к актуальности</FspStatusBadge></td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
  </div>
</template>
