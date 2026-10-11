<script setup lang="ts">
useHead({ title: 'Опрос и тест на грейд — Карьера ФСП' })

const links = [
  { label: 'Профиль', href: '/candidate/profile' },
  { label: 'Приглашения', href: '/candidate/invites' },
  { label: 'Грейд и тесты', href: '/candidate/grade' },
  { label: 'Вакансии', href: '/candidate/vacancy' },
  { label: 'Настройки', href: '/candidate/settings' }
]

interface Task { title: string; text: string; code?: string; kind: string; level: number; options: string[] }
const TOTAL = 12
const FIRST = 5 // первые 4 задания уже решены
const tasks: Task[] = [
  {
    title: 'Ограничение частоты запросов', kind: 'Код', level: 3,
    text: 'Сервис принимает до 120 запросов в минуту на клиента. Функция ниже должна вернуть false, если лимит превышен. Что произойдёт при одновременных вызовах из нескольких горутин?',
    code: `func (l *Limiter) Allow(id string) bool {
    w := l.windows[id]
    if time.Since(w.start) > time.Minute {
        w.start, w.count = time.Now(), 0
    }
    w.count++
    return w.count <= 120
}`,
    options: ['Ничего: map в Go безопасна для конкурентного доступа', 'Гонка данных: возможна паника при записи в map и неверный счётчик', 'Лимит всегда будет срабатывать раньше на один запрос', 'Ошибка компиляции из-за присваивания в структуру']
  },
  {
    title: 'Индекс для выборки платежей', kind: 'SQL', level: 3,
    text: 'Самый частый запрос: последние 50 платежей клиента по дате. Какой индекс лучше всего его ускорит?',
    code: `SELECT * FROM payments
WHERE client_id = $1
ORDER BY created_at DESC
LIMIT 50;`,
    options: ['Отдельные индексы на client_id и created_at', 'Составной индекс (client_id, created_at DESC)', 'Индекс на created_at', 'Хеш-индекс на client_id']
  },
  {
    title: 'Идемпотентность списания', kind: 'Архитектура', level: 4,
    text: 'Клиент повторил запрос на списание из-за таймаута. Как гарантировать, что деньги спишутся один раз?',
    options: ['Увеличить таймаут на клиенте', 'Ключ идемпотентности с уникальным ограничением в БД', 'Ретраи с экспоненциальной задержкой', 'Распределённая блокировка на всё время запроса']
  },
  {
    title: 'Порядок сообщений в Kafka', kind: 'Kafka', level: 3,
    text: 'События по одному счёту должны обрабатываться строго по порядку. Что для этого нужно?',
    options: ['Один консьюмер на весь топик', 'Ключ сообщения = id счёта', 'Включить сжатие топика', 'acks=all на продюсере']
  },
  {
    title: 'Утечка горутин', kind: 'Код', level: 3,
    text: 'Почему эта функция может оставлять висящие горутины?',
    code: `func first(urls []string) string {
    ch := make(chan string)
    for _, u := range urls {
        go func(u string) { ch <- fetch(u) }(u)
    }
    return <-ch
}`,
    options: ['fetch блокирует главный поток', 'Небуферизованный канал: остальные горутины навсегда заблокированы на отправке', 'Переменная цикла захватывается по ссылке', 'Канал нужно закрыть до return']
  },
  {
    title: 'Изоляция транзакций', kind: 'SQL', level: 4,
    text: 'Два параллельных перевода читают баланс и списывают сумму. Какой подход в PostgreSQL исключит уход баланса в минус?',
    options: ['READ COMMITTED без изменений', 'SELECT ... FOR UPDATE перед списанием', 'Повторное чтение баланса после UPDATE', 'Индекс на поле balance']
  },
  {
    title: 'Контекст и отмена', kind: 'Код', level: 2,
    text: 'Что произойдёт с запросом к БД, если клиент закрыл HTTP-соединение, а в запрос передан r.Context()?',
    options: ['Запрос продолжит выполняться до конца', 'Контекст отменится, драйвер прервёт запрос', 'Сервер упадёт с паникой', 'Соединение с БД закроется навсегда']
  },
  {
    title: 'Мониторинг антифрода', kind: 'Архитектура', level: 3,
    text: 'Какая метрика лучше всего покажет деградацию антифрод-сервиса для бизнеса?',
    options: ['Загрузка CPU', 'p99 времени ответа и доля решений «по умолчанию» при таймауте', 'Количество подов', 'Размер логов в сутки']
  }
]

const { show } = useToast()
const idx = ref(0)
const answers = ref<(number | null)[]>(tasks.map(() => null))
const done = ref<('ok' | 'skip')[]>([])
const seconds = ref(18 * 60 + 42)
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => { timer = setInterval(() => { if (seconds.value > 0) seconds.value-- }, 1000) })
onBeforeUnmount(() => clearInterval(timer))

const task = computed(() => tasks[idx.value]!)
const number = computed(() => FIRST + idx.value)
const solved = computed(() => FIRST - 1 + done.value.length)
const clock = computed(() => `${String(Math.floor(seconds.value / 60)).padStart(2, '0')}:${String(seconds.value % 60).padStart(2, '0')}`)
const cells = computed(() => Array.from({ length: TOTAL }, (_, i) => (i < solved.value ? 'var(--success)' : i === solved.value ? 'var(--warning)' : 'var(--line-strong)')))

function next(kind: 'ok' | 'skip') {
  if (kind === 'ok' && answers.value[idx.value] == null) { show('Выберите вариант ответа'); return }
  done.value.push(kind)
  if (idx.value < tasks.length - 1) { idx.value++; return }
  show('Тест завершён — категория Backend · Middle подтверждена')
  navigateTo('/candidate/grade')
}
const optStyle = (on: boolean) => on
  ? '--cut: var(--cut-s); padding: 14px 16px; display: flex; gap: 12px; align-items: center; cursor: pointer;'
  : '--cut: var(--cut-s); --fill: var(--bg); --edge: var(--line-strong); --bw: 1px; padding: 14px 16px; display: flex; gap: 12px; align-items: center; cursor: pointer;'
</script>

<template>
  <div style="background: var(--bg); color: var(--text); font-family: var(--font-sans); min-height: 100vh;">
    <FspHeader product="Карьера" user="Алексей К." :links="links" />

    <main style="max-width: 1240px; margin: 0 auto; padding: 40px 32px 64px;">
      <nav aria-label="Шаги онбординга" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 8px; margin-bottom: 40px;">
        <div style="padding: 14px 0; box-shadow: inset 0 3px 0 var(--success);"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Шаг 1 · готово</div><div style="font-weight: 600; margin-top: 4px;">Отрасль и специализация</div></div>
        <div style="padding: 14px 0; box-shadow: inset 0 3px 0 var(--success);"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Шаг 2 · готово</div><div style="font-weight: 600; margin-top: 4px;">Предполагаемый грейд</div></div>
        <div style="padding: 14px 0; box-shadow: inset 0 3px 0 var(--warning);"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text);">Шаг 3 · сейчас</div><div style="font-weight: 600; margin-top: 4px;">Тест на грейд</div></div>
        <div style="padding: 14px 0; box-shadow: inset 0 3px 0 var(--line-strong);"><div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted);">Шаг 4</div><div style="font-weight: 600; margin-top: 4px; color: var(--text-muted);">Категория</div></div>
      </nav>

      <div style="display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start;">
        <section style="flex: 999 1 600px; min-width: 0; display: flex; flex-direction: column; gap: 24px;">
          <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 12px;">
            <span style="font-size: 14px; color: var(--text-muted);">Задание</span>
            <span class="fsp-display" style="font-size: 20px; line-height: 24px;">{{ number }} / {{ TOTAL }}</span>
            <FspTag>{{ task.kind }}</FspTag>
            <FspTag>Сложность {{ task.level }} из 5</FspTag>
            <span style="margin-left: auto; display: inline-flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; font-variant-numeric: tabular-nums;"><FspIcon name="clock" />{{ clock }}</span>
          </div>
          <div>
            <h1 style="margin: 0; font-size: 22px; line-height: 30px; font-weight: 600;">{{ task.title }}</h1>
            <p style="margin: 12px 0 0; font-size: 16px; line-height: 24px; color: var(--text-muted);">{{ task.text }}</p>
          </div>
          <pre v-if="task.code" style="margin: 0; padding: 20px; background: var(--surface-hover); font: 500 14px/22px ui-monospace, 'JetBrains Mono', monospace; color: var(--text); overflow-x: auto; box-shadow: inset 3px 0 0 var(--disc-algo);">{{ task.code }}</pre>
          <fieldset :key="idx" style="border: 0; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px;">
            <legend style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">Выберите ответ</legend>
            <label v-for="(o, i) in task.options" :key="i" :class="['fsp-cut', answers[idx] === i && 'fsp-active']" :style="optStyle(answers[idx] === i)">
              <input v-model="answers[idx]" type="radio" :name="'a' + idx" :value="i" style="accent-color: var(--primary); width: 18px; height: 18px; margin: 0;">{{ o }}
            </label>
          </fieldset>
          <div style="display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between; padding-top: 16px; box-shadow: inset 0 1px 0 var(--line);">
            <FspButton variant="ghost" @click="next('skip')">Пропустить</FspButton>
            <FspButton icon-right="arrow-right" @click="next('ok')">{{ idx === tasks.length - 1 ? 'Завершить тест' : 'Ответить' }}</FspButton>
          </div>
        </section>

        <aside style="flex: 1 1 320px; min-width: 0; display: flex; flex-direction: column; gap: 16px;">
          <FspPlate :dots="6">
            <div style="font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--on-plate-muted);">Вы проходите тест на</div>
            <div class="fsp-display" style="font-size: 26px; line-height: 30px; margin: 10px 0 6px;">Backend · Middle</div>
            <div style="font-size: 14px; line-height: 20px; color: var(--on-plate-muted);">ИТ · Разработка · Go, PostgreSQL</div>
          </FspPlate>
          <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <div class="fsp-display" style="font-size: 16px; line-height: 20px; margin-bottom: 12px;">Как устроен тест</div>
            <ul style="margin: 0; padding: 0 0 0 18px; display: flex; flex-direction: column; gap: 8px; font-size: 14px; line-height: 20px; color: var(--text-muted);">
              <li>Задачи берутся из банка с откалиброванной сложностью — одинаково честно для всех.</li>
              <li>Числа, имена и условия в каждой задаче уникальны для вас — готовые ответы не помогут.</li>
              <li>Сложность подстраивается по ходу: ответили уверенно — следующий вопрос труднее.</li>
            </ul>
          </div>
          <div style="padding: 20px 0 0; box-shadow: inset 0 1px 0 var(--line);">
            <div style="display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 12px;"><span style="color: var(--text-muted);">Прогресс</span><b>{{ solved }} из {{ TOTAL }}</b></div>
            <div style="display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 4px;">
              <span v-for="(c, i) in cells" :key="i" :style="{ height: '8px', background: c }" />
            </div>
            <p style="margin: 16px 0 0; font-size: 13px; line-height: 18px; color: var(--text-muted);">Прервать можно в любой момент — прогресс сохранится на 24 часа.</p>
            <FspButton variant="ghost" size="sm" href="/candidate/profile" style="margin-top: 12px;" toast="Прогресс сохранён — вернитесь в течение 24 часов">Прервать тест</FspButton>
          </div>
        </aside>
      </div>
    </main>
  </div>
</template>
