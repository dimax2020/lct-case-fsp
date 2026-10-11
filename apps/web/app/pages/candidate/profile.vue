<script setup lang="ts">
useHead({ title: 'Профиль кандидата — Карьера ФСП' })

const v = reactive((() => {
  return {
      yes: true, dots: 6, avatar: 88, small: 44, iconSize: 28,
      links: [
        { label: 'Профиль', href: '/candidate/profile', active: true },
        { label: 'Приглашения', href: '/candidate/invites' },
        { label: 'Грейд и тесты', href: '/candidate/grade' },
        { label: 'Вакансии', href: '/candidate/vacancy' },
        { label: 'Настройки', href: '/candidate/settings' }
      ]
    };
})())

const { show } = useToast()
const github = ref('')
const githubOpen = ref(false)
const githubSaved = ref(false)
const cvName = ref('Kuznetsov_CV.pdf')
const cvInput = ref<HTMLInputElement>()
function saveGithub() {
  if (!/github\.com\/.+/.test(github.value)) { show('Укажите ссылку вида github.com/username'); return }
  githubSaved.value = true; githubOpen.value = false
  show('GitHub добавлен — профиль станет заметнее')
}
function onCv(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  cvName.value = f.name
  show('Резюме загружено — распознаём поля')
}
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Карьера" user="Алексей К." :unread="v.yes" :links="v.links" logo-dark="/brand/championship-logo-white.svg" logo-light="/brand/championship-logo-navy.svg" />

    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px; display: flex; flex-direction: column; gap: 32px;">

      <section style="display: flex; flex-wrap: wrap; gap: 24px; align-items: center;">
        <FspCompanyLogo name="Алексей Кузнецов" :size="v.avatar" />
        <div style="flex: 999 1 360px; min-width: 0;">
          <h1 style="margin: 0; font-size: 32px; line-height: 40px; font-weight: 700;">Алексей Кузнецов</h1>
          <div style="margin-top: 6px; display: flex; flex-wrap: wrap; gap: 8px 20px; font-size: 15px; color: var(--text-muted);">
            <span>Backend-разработчик</span><span>Новосибирск · готов к удалёнке</span><span>Опыт 4 года</span>
          </div>
          <div style="margin-top: 12px;"><FspStatusBadge status="new">Профиль виден работодателям</FspStatusBadge></div>
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
          <FspButton variant="outline" size="sm" toast="PDF-профиль сформирован и скачивается">Скачать PDF-профиль</FspButton>
          <FspButton variant="plate" size="sm" href="/candidate/settings">Редактировать</FspButton>
        </div>
      </section>

      <section style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 16px;">
        <FspPlate :dots="v.dots">
          <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Ваша категория</div>
          <div class="fsp-display" style="font-size: 28px; line-height: 32px; margin: 10px 0 16px;">Backend · Middle</div>
          <div style="display: flex; gap: 32px;">
            <div><div class="fsp-display" style="font-size: 28px; line-height: 32px;">12</div><div style="font-size: 13px; color: var(--on-plate-muted);">место из 340</div></div>
            <div><div class="fsp-display" style="font-size: 28px; line-height: 32px;">82</div><div style="font-size: 13px; color: var(--on-plate-muted);">балла за тест</div></div>
          </div>
          <div style="margin-top: 16px;"><NuxtLink to="/candidate/grade" style="color: var(--on-plate); font-weight: 600; font-size: 14px;">Категория и грейд →</NuxtLink></div>
        </FspPlate>

        <NuxtLink to="/candidate/invites" class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 32px; text-decoration: none; color: var(--text); display: flex; flex-direction: column; gap: 8px;">
          <span style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Приглашения</span>
          <span class="fsp-display" style="font-size: 44px; line-height: 48px;">2 <span style="font-size: 16px; color: var(--text-muted);">новых</span></span>
          <span style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Код Сибири — 250–320 тыс. ₽<br>Полярный Бит — 220–280 тыс. ₽</span>
          <span style="margin-top: auto; font-weight: 600; font-size: 14px;">Посмотреть →</span>
        </NuxtLink>

        <div class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); padding: 32px; display: flex; flex-direction: column; gap: 12px;">
          <span style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Актуальность профиля</span>
          <span class="fsp-display" style="font-size: 44px; line-height: 48px;">92%</span>
          <div style="height: 8px; background: var(--line-strong);"><div style="width: 92%; height: 8px; background: var(--success);"></div></div>
          <span style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Решайте короткие задания от работодателей раз в 2–3 недели, чтобы оставаться выше в выдаче.</span>
        </div>
      </section>

      <section aria-label="Как подняться в выдаче" class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); --edge: var(--accent-mark); --bw: var(--border-card); padding: 28px;">
        <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 16px; align-items: baseline; margin-bottom: 18px;">
          <h2 class="fsp-display" style="font-size: 20px; line-height: 24px;">Как подняться в выдаче · топ-3</h2>
          <span style="font-size: 13px; color: var(--text-muted);">По запросам работодателей в категории Backend · Middle за 30 дней</span>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 12px;">
          <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface-hover); padding: 20px; display: flex; flex-direction: column; gap: 8px;">
            <span class="fsp-display" style="font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 34px; height: 24px; display: inline-grid; place-items: center;">01</span>
            <b style="font-size: 16px; line-height: 22px;">Подтвердите знание Kubernetes</b>
            <span class="fsp-display" style="font-size: 26px; line-height: 30px; color: var(--text);">+30% <span style="font-family: var(--font-sans); font-size: 14px; font-weight: 500; color: var(--text-muted);">работодателей</span></span>
            <span style="font-size: 14px; line-height: 20px; color: var(--text-muted);">K8s требуют в 3 из 10 запросов вашей категории. Мини-тест займёт 10 минут.</span>
            <div style="margin-top: auto; padding-top: 8px;"><FspButton size="sm" href="/candidate/onboarding">Пройти мини-тест</FspButton></div>
          </div>
          <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface-hover); padding: 20px; display: flex; flex-direction: column; gap: 8px;">
            <span class="fsp-display" style="font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 34px; height: 24px; display: inline-grid; place-items: center;">02</span>
            <b style="font-size: 16px; line-height: 22px;">Решите задание Полярного Бита</b>
            <span class="fsp-display" style="font-size: 26px; line-height: 30px; color: var(--text);">12 → 7 <span style="font-family: var(--font-sans); font-size: 14px; font-weight: 500; color: var(--text-muted);">место</span></span>
            <span style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Актуальность профиля станет 100% — вы поднимитесь в рейтинге категории.</span>
            <div style="margin-top: auto; padding-top: 8px;"><FspButton size="sm" variant="outline" href="/candidate/onboarding">Решить задание</FspButton></div>
          </div>
          <div class="fsp-cut" style="--cut: var(--cut-m); --fill: var(--surface-hover); padding: 20px; display: flex; flex-direction: column; gap: 8px;">
            <span class="fsp-display" style="font-size: 13px; color: #ffffff; background: var(--accent-mark); width: 34px; height: 24px; display: inline-grid; place-items: center;">03</span>
            <b style="font-size: 16px; line-height: 22px;">Добавьте ссылку на GitHub</b>
            <span class="fsp-display" style="font-size: 26px; line-height: 30px; color: var(--text);">+18% <span style="font-family: var(--font-sans); font-size: 14px; font-weight: 500; color: var(--text-muted);">просмотров</span></span>
            <span style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Профили с открытым кодом работодатели открывают заметно чаще.</span>
            <div style="margin-top: auto; padding-top: 8px;">
              <FspStatusBadge v-if="githubSaved" status="offer">{{ github }}</FspStatusBadge>
              <form v-else-if="githubOpen" style="display: flex; flex-direction: column; gap: 8px;" @submit.prevent="saveGithub">
                <FspInput v-model="github" placeholder="github.com/username" aria-label="Ссылка на GitHub" />
                <FspButton size="sm" type="submit">Сохранить</FspButton>
              </form>
              <FspButton v-else size="sm" variant="outline" @click="githubOpen = true">Добавить</FspButton>
            </div>
          </div>
        </div>
      </section>

      <div style="display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start;">
        <div style="flex: 999 1 560px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">

          <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; align-items: baseline; margin-bottom: 20px;">
              <h2 class="fsp-display" style="font-size: 20px; line-height: 24px;">Подтверждённые навыки</h2>
              <span style="font-size: 13px; color: var(--text-muted);">по результатам теста 10.10.2026</span>
            </div>
            <div style="display: flex; flex-direction: column; gap: 14px;">
              <div style="display: grid; grid-template-columns: 160px 1fr 48px; gap: 16px; align-items: center; font-size: 15px;"><span>Go</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 88%; height: 8px; background: var(--success);"></div></div><b style="text-align: right;">88</b></div>
              <div style="display: grid; grid-template-columns: 160px 1fr 48px; gap: 16px; align-items: center; font-size: 15px;"><span>PostgreSQL</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 81%; height: 8px; background: var(--success);"></div></div><b style="text-align: right;">81</b></div>
              <div style="display: grid; grid-template-columns: 160px 1fr 48px; gap: 16px; align-items: center; font-size: 15px;"><span>Конкурентность</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 76%; height: 8px; background: var(--warning);"></div></div><b style="text-align: right;">76</b></div>
              <div style="display: grid; grid-template-columns: 160px 1fr 48px; gap: 16px; align-items: center; font-size: 15px;"><span>Алгоритмы</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 91%; height: 8px; background: var(--success);"></div></div><b style="text-align: right;">91</b></div>
              <div style="display: grid; grid-template-columns: 160px 1fr 48px; gap: 16px; align-items: center; font-size: 15px;"><span>Проектирование API</span><div style="height: 8px; background: var(--surface-hover);"><div style="width: 69%; height: 8px; background: var(--warning);"></div></div><b style="text-align: right;">69</b></div>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 24px; padding-top: 20px; box-shadow: inset 0 1px 0 var(--line);">
              <span style="font-size: 13px; color: var(--text-muted); margin-right: 4px; align-self: center;">Из резюме, без проверки:</span>
              <FspTag>Kafka</FspTag>
              <FspTag>Docker</FspTag>
              <FspTag>Kubernetes</FspTag>
              <FspTag>gRPC</FspTag>
            </div>
          </section>

          <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <h2 class="fsp-display" style="font-size: 20px; line-height: 24px; margin-bottom: 20px;">Опыт работы</h2>
            <div style="display: flex; flex-direction: column; gap: 20px;">
              <div style="display: flex; gap: 16px;"><FspCompanyLogo name="Сибирь Телеком" :size="v.small" /><div><div style="font-weight: 600;">Backend-разработчик</div><div style="font-size: 14px; color: var(--text-muted);">Сибирь Телеком · 2023 — сейчас · 3 года</div><div style="font-size: 14px; line-height: 20px; margin-top: 6px;">Биллинг на Go: переписал расчёт тарифов, p99 с 900 до 120 мс.</div></div></div>
              <div style="display: flex; gap: 16px;"><FspCompanyLogo name="Студия Восток" :size="v.small" /><div><div style="font-weight: 600;">Junior-разработчик</div><div style="font-size: 14px; color: var(--text-muted);">Студия Восток · 2022 — 2023 · 1 год</div></div></div>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 24px; padding-top: 20px; box-shadow: inset 0 1px 0 var(--line);">
              <span style="font-size: 13px; color: var(--text-muted); margin-right: 4px; align-self: center;">Софт-скиллы:</span>
              <FspTag>Менторство</FspTag>
              <FspTag>Код-ревью</FspTag>
              <FspTag>Работа в команде 5–8 человек</FspTag>
            </div>
          </section>
        </div>

        <aside style="flex: 1 1 380px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
          <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 4px;">
              <h2 class="fsp-display" style="font-size: 20px; line-height: 24px;">Достижения ФСП</h2>
              <img src="/brand/fsp-star-dark.svg" alt="" aria-hidden="true" style="width: 28px; height: 28px;">
            </div>
            <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 20px;">Подтверждено через ФСП ID</div>
            <div style="display: flex; flex-direction: column; gap: 16px;">
              <div style="display: flex; flex-direction: column; gap: 6px; padding-bottom: 16px; box-shadow: inset 0 -1px 0 var(--line);">
                <div style="display: flex; justify-content: space-between; gap: 8px; align-items: center;"><FspDisciplineBadge discipline="algo" /><span class="fsp-display" style="font-size: 16px;">2 место</span></div>
                <div style="font-weight: 600;">Чемпионат России 2025</div>
                <div style="font-size: 13px; color: var(--text-muted);">Финал · командный зачёт · 214 команд</div>
              </div>
              <div style="display: flex; flex-direction: column; gap: 6px; padding-bottom: 16px; box-shadow: inset 0 -1px 0 var(--line);">
                <div style="display: flex; justify-content: space-between; gap: 8px; align-items: center;"><FspDisciplineBadge discipline="product" /><span class="fsp-display" style="font-size: 16px;">Финалист</span></div>
                <div style="font-weight: 600;">Кубок России 2024</div>
                <div style="font-size: 13px; color: var(--text-muted);">Продуктовое программирование · хакатон 48 ч</div>
              </div>
              <div style="display: flex; justify-content: space-between; font-size: 14px;"><span style="color: var(--text-muted);">Разряд ФСП</span><b>КМС</b></div>
            </div>
          </section>

          <section class="fsp-cut" style="--cut: var(--cut-l); --fill: var(--surface); --edge: var(--line-card); --bw: var(--border-card); --edge: var(--accent-mark); --bw: var(--border-card); padding: 28px;">
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Задание от работодателя</div>
            <div style="font-weight: 600; font-size: 17px; line-height: 24px; margin: 10px 0 6px;">Спроектируйте кэш для каталога на 2 млн позиций</div>
            <div style="font-size: 14px; line-height: 20px; color: var(--text-muted);">Полярный Бит · ~30 минут · до 18 октября</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px;">
              <FspButton size="sm" href="/candidate/onboarding">Решить</FspButton>
              <FspButton size="sm" variant="outline" toast="Полярный Бит получил запрос — обсудите подход в переписке">Предложить подход</FspButton>
            </div>
          </section>

          <section style="padding: 24px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <h2 class="fsp-display" style="font-size: 16px; line-height: 20px; margin-bottom: 16px;">Резюме</h2>
            <div style="display: flex; gap: 12px; align-items: center;">
              <FspIcon name="briefcase" :size="v.iconSize" />
              <div style="flex: 1; min-width: 0;"><div style="font-weight: 600; font-size: 14px;">{{ cvName }}</div><div style="font-size: 13px; color: var(--text-muted);">Распознано 10.10 · 14 полей</div></div>
              <FspButton size="sm" variant="ghost" @click="cvInput?.click()">Заменить</FspButton>
              <input ref="cvInput" type="file" accept=".pdf,application/pdf" hidden @change="onCv">
            </div>
          </section>
        </aside>
      </div>
    </main>
  </div>
</template>
