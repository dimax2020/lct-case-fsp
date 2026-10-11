import type { components } from '~/api/schema'

type S = components['schemas']

export const IDS = {
  candidate: '11111111-1111-4111-8111-111111111111',
  c2: '11111111-1111-4111-8111-111111111112',
  c3: '11111111-1111-4111-8111-111111111113',
  c4: '11111111-1111-4111-8111-111111111114',
  c5: '11111111-1111-4111-8111-111111111115',
  c6: '11111111-1111-4111-8111-111111111116',
  company: '22222222-2222-4222-8222-222222222222',
  need: '33333333-3333-4333-8333-333333333333',
  userC: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  userE: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  inv1: '44444444-4444-4444-8444-444444444441',
  inv2: '44444444-4444-4444-8444-444444444442',
  inv3: '44444444-4444-4444-8444-444444444443',
  inv4: '44444444-4444-4444-8444-444444444444',
  exp1: '55555555-5555-4555-8555-555555555551',
  exp2: '55555555-5555-4555-8555-555555555552',
  proj1: '66666666-6666-4666-8666-666666666661',
  ach1: '77777777-7777-4777-8777-777777777771',
  ach2: '77777777-7777-4777-8777-777777777772',
}

export interface PoolPerson {
  candidate_id: string
  full_name: string
  display_name: string
  category_id: string
  category: string
  grade: string
  experience_years: number
  city: string
  formats: S['WorkFormat'][]
  fsp_badge: S['FspBadge'] | null
  fsp_discipline: string | null
  match: number
  test_score: number
  explanations: string[]
  skills: string[]
  projects: string[]
  domains: string[]
  active_30d: boolean
  email: string
  phone: string
}

export interface AttemptRec {
  id: string
  specialization: S['Specialization']
  declared_grade: S['Grade']
  started_at: string
  deadline_at: string
  finished_at: string | null
  answers: S['AnswerIn'][]
  order: string[]
  result: S['AttemptResult'] | null
}

export interface Db {
  profile: S['CandidateProfile']
  settings: S['CandidateSettings']
  company: S['CompanyOut']
  needs: S['NeedOut'][]
  requirements: Record<string, S['RequirementOut'][]>
  people: PoolPerson[]
  favorites: string[]
  invitations: S['InvitationOut'][]
  messages: Record<string, S['MessageOut'][]>
  resumes: Record<string, S['ResumeView'] & { hits: number }>
  attempts: Record<string, AttemptRec>
  jobs: Record<string, S['JobOut'] & { hits: number }>
  grade: S['GradeView']
}

const KEY = 'fsp-api-mock-v1'
let memory: Db | null = null

export function uid() {
  return crypto.randomUUID()
}

export function taskOrder() {
  return TASKS.map(t => t.id)
}

export function taskById(id: string) {
  return TASKS.find(t => t.id === id) ?? null
}

export function correctOption(taskId: string) {
  return CORRECT[taskId] ?? ''
}

export function getDb() {
  if (!memory) memory = readStorage() ?? seed()
  return memory
}

export function saveDb() {
  if (memory && import.meta.client) sessionStorage.setItem(KEY, JSON.stringify(memory))
}

function readStorage(): Db | null {
  if (!import.meta.client) return null
  const raw = sessionStorage.getItem(KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as Db
  } catch {
    return null
  }
}

function longText(text: string) {
  let out = text.trim()
  const extra = ' Первые три месяца человек разбирает антифрод: правила, инциденты p99 и идемпотентные списания.'
  while (out.length < 320) out += extra
  return out
}

const mcq = (id: string, skills: string[], difficulty: number, body: string, options: [string, string, string, string]): S['TaskPublic'] => ({
  id,
  kind: 'mcq',
  skills,
  difficulty,
  body,
  options: options.map((text, i) => ({ id: String.fromCharCode(97 + i), text })),
  languages: [],
  tests_public: null,
})

export const TASKS: S['TaskPublic'][] = [
  mcq('t01', ['go'], 3, 'Сервис принимает до 120 запросов в минуту на клиента. Счётчик лежит в map и обновляется из нескольких горутин. Что произойдёт?', [
    'Ничего: map в Go безопасна для конкурентного доступа',
    'Гонка данных: возможна паника при записи в map и неверный счётчик',
    'Лимит всегда сработает раньше на один запрос',
    'Ошибка компиляции из-за присваивания в структуру',
  ]),
  mcq('t02', ['postgresql'], 3, 'Самый частый запрос — последние 50 платежей клиента по дате. Какой индекс лучше его ускорит?', [
    'Отдельные индексы на client_id и created_at',
    'Составной индекс (client_id, created_at DESC)',
    'Индекс только на created_at',
    'Хеш-индекс на client_id',
  ]),
  mcq('t03', ['go'], 4, 'Клиент повторил списание из-за таймаута. Как гарантировать, что деньги спишутся один раз?', [
    'Увеличить таймаут на клиенте',
    'Ключ идемпотентности с уникальным ограничением в БД',
    'Ретраи с экспоненциальной задержкой',
    'Блокировка на всё время запроса',
  ]),
  mcq('t04', ['kafka'], 3, 'События по одному счёту должны обрабатываться строго по порядку. Что для этого нужно?', [
    'Один консьюмер на весь топик',
    'Ключ сообщения = id счёта',
    'Включить сжатие топика',
    'acks=all на продюсере',
  ]),
  mcq('t05', ['go'], 3, 'Несколько горутин пишут в небуферизованный канал, а читатель забирает только первое значение. Почему остальные горутины зависнут?', [
    'fetch блокирует главный поток',
    'Отправка в небуферизованный канал блокируется, пока её не прочитают',
    'Переменная цикла захватывается по ссылке',
    'Канал нужно закрыть до return',
  ]),
  mcq('t06', ['postgresql'], 4, 'Два перевода читают баланс и списывают сумму. Что в PostgreSQL не даст уйти в минус?', [
    'READ COMMITTED без изменений',
    'SELECT ... FOR UPDATE перед списанием',
    'Повторное чтение баланса после UPDATE',
    'Индекс на поле balance',
  ]),
  mcq('t07', ['go'], 2, 'В запрос к БД передан r.Context(), и клиент закрыл соединение. Что произойдёт?', [
    'Запрос выполнится до конца',
    'Контекст отменится, драйвер прервёт запрос',
    'Сервер упадёт с паникой',
    'Соединение с БД закроется навсегда',
  ]),
  mcq('t08', ['go'], 3, 'Какая метрика раньше покажет деградацию антифрод-сервиса для бизнеса?', [
    'Загрузка CPU',
    'p99 времени ответа и доля решений по умолчанию при таймауте',
    'Количество подов',
    'Размер логов в сутки',
  ]),
  mcq('t09', ['docker'], 2, 'Зачем фиксировать базовый образ и зависимости в сборке сервиса?', [
    'Чтобы контейнер запускался от root',
    'Чтобы повторная сборка давала тот же артефакт',
    'Чтобы отключить healthcheck',
    'Чтобы увеличить лимит памяти',
  ]),
  {
    id: 't10',
    kind: 'code',
    skills: ['python'],
    difficulty: 3,
    body: 'Напишите функцию, которая возвращает True, если строка — палиндром без учёта пробелов и регистра. Открытый пример: stdin «А роза упала на лапу Азора», stdout «True».',
    options: null,
    languages: ['python', 'go'],
    tests_public: [{ stdin: 'А роза упала на лапу Азора\n', expected: 'True\n' }],
  },
  {
    id: 't11',
    kind: 'code',
    skills: ['go'],
    difficulty: 3,
    body: 'Напишите программу, которая читает целое N и печатает сумму чисел от 1 до N. Открытый пример: stdin «4», stdout «10».',
    options: null,
    languages: ['go', 'python'],
    tests_public: [{ stdin: '4\n', expected: '10\n' }],
  },
  {
    id: 't12',
    kind: 'code',
    skills: ['python', 'go'],
    difficulty: 4,
    body: 'Напишите программу, которая читает строку из слов и печатает их в обратном порядке. Открытый пример: stdin «go kafka sql», stdout «sql kafka go».',
    options: null,
    languages: ['python', 'go'],
    tests_public: [{ stdin: 'go kafka sql\n', expected: 'sql kafka go\n' }],
  },
]

const CORRECT: Record<string, string> = {
  t01: 'b', t02: 'b', t03: 'b', t04: 'b', t05: 'b', t06: 'b', t07: 'b', t08: 'b', t09: 'b',
}

function seed(): Db {
  const description = longText('Перестраиваем процессинг платежей: 3 тыс. транзакций в секунду, шесть разработчиков, релиз раз в неделю. Нужен человек в антифрод на Go, Kafka и PostgreSQL.')
  const profile: S['CandidateProfile'] = {
    id: IDS.candidate,
    full_name: 'Алексей Кузнецов',
    display_name: 'Алексей К.',
    city: 'Новосибирск',
    specialization: 'backend',
    grade: 'middle',
    grade_score: 82,
    ready_for_next: false,
    category_rank: 12,
    category_size: 340,
    min_salary: 240000,
    formats: ['remote', 'hybrid'],
    status: 'seeking',
    visible: true,
    in_pool_eligible: true,
    liked_skills: ['go', 'postgresql'],
    disliked_skills: [],
    liked_domains: ['fintech'],
    blocked_domains: [],
    last_active_at: new Date().toISOString(),
    phone: '+7 913 000-42-18',
    contact_email: 'a.kuznetsov@mail.ru',
    skills: [
      { skill_id: 'go', score: 88, source: 'test' },
      { skill_id: 'postgresql', score: 81, source: 'test' },
      { skill_id: 'kafka', score: null, source: 'resume' },
      { skill_id: 'docker', score: null, source: 'resume' },
    ],
    projects: [{
      id: IDS.proj1,
      task: 'Переписал расчёт тарифов биллинга',
      role: 'owner',
      skills: ['go', 'postgresql'],
      scale: 'p99 с 900 до 120 мс',
      outcome: 'Расчёт держит пик без очереди',
      date: '2024-06-01T00:00:00.000Z',
      url: null,
      source: 'project',
    }],
    experiences: [
      {
        id: IDS.exp1,
        company: 'Сибирь Телеком',
        role: 'Backend-разработчик',
        start: '2023-03-01T00:00:00.000Z',
        end: null,
        description: 'Биллинг на Go: переписал расчёт тарифов, p99 с 900 до 120 мс.',
        evidence_span: null,
      },
      {
        id: IDS.exp2,
        company: 'Студия Восток',
        role: 'Junior-разработчик',
        start: '2022-02-01T00:00:00.000Z',
        end: '2023-02-01T00:00:00.000Z',
        description: 'Внутренние API и фоновые задачи.',
        evidence_span: null,
      },
    ],
    fsp_achievements: [
      { id: IDS.ach1, discipline: 'algo', event: 'Чемпионат России 2025', place: 2, year: 2025 },
      { id: IDS.ach2, discipline: 'product', event: 'Кубок России 2024', place: null, year: 2024 },
    ],
  }
  const people: PoolPerson[] = [
    {
      candidate_id: IDS.candidate, full_name: 'Алексей Кузнецов', display_name: 'Алексей К.',
      category_id: 'backend:middle', category: 'Backend · Middle', grade: 'middle', experience_years: 4,
      city: 'Новосибирск', formats: ['remote'], fsp_badge: { discipline: 'algo', text: 'ФСП · 2 место ЧР-2025' },
      fsp_discipline: 'algo', match: 94, test_score: 82,
      explanations: ['Тест Middle: 82/100, место 12 из 340', 'Стек совпадает: Go 88, PostgreSQL 81', 'Призёр Чемпионата России, алгоритмы'],
      skills: ['go', 'postgresql', 'kafka'], projects: ['Биллинг: p99 120 мс'], domains: ['fintech'], active_30d: true,
      email: 'a.kuznetsov@mail.ru', phone: '+7 913 000-42-18',
    },
    {
      candidate_id: IDS.c2, full_name: 'Мария Соколова', display_name: 'Мария С.',
      category_id: 'backend:middle', category: 'Backend · Middle', grade: 'middle', experience_years: 3,
      city: 'Казань', formats: ['remote'], fsp_badge: { discipline: 'infosec', text: 'ФСП · финал Кубка-2024' },
      fsp_discipline: 'infosec', match: 89, test_score: 79,
      explanations: ['Тест Middle: 79/100', 'Стек 3 из 4: нет подтверждённого Kafka', 'Финалист Кубка по инфобезу'],
      skills: ['go', 'postgresql'], projects: ['Антифрод: задание 5 дней назад'], domains: ['fintech'], active_30d: true,
      email: 'm.sokolova@mail.ru', phone: '+7 843 000-11-22',
    },
    {
      candidate_id: IDS.c3, full_name: 'Игорь Лебедев', display_name: 'Игорь Л.',
      category_id: 'backend:middle', category: 'Backend · Middle', grade: 'middle', experience_years: 5,
      city: 'Москва', formats: ['remote'], fsp_badge: null, fsp_discipline: null, match: 86, test_score: 90,
      explanations: ['Лучший тест в категории: 90/100', 'Стек 4 из 4, 3 года в платёжных системах'],
      skills: ['go', 'postgresql', 'kafka'], projects: ['Платёжный шлюз'], domains: ['fintech'], active_30d: false,
      email: 'i.lebedev@mail.ru', phone: '+7 495 000-33-44',
    },
    {
      candidate_id: IDS.c4, full_name: 'Екатерина Волкова', display_name: 'Екатерина В.',
      category_id: 'backend:middle', category: 'Backend · Middle', grade: 'middle', experience_years: 2,
      city: 'Новосибирск', formats: ['office'], fsp_badge: { discipline: 'product', text: 'ФСП · полуфинал ЧР-2025' },
      fsp_discipline: 'product', match: 72, test_score: 71,
      explanations: ['Тест Middle: 71/100', 'Стек: Go и Redis', 'Хакатон ФСП по продуктовому программированию'],
      skills: ['go'], projects: ['Хакатон каталога'], domains: ['ecommerce'], active_30d: true,
      email: 'e.volkova@mail.ru', phone: '+7 383 000-55-66',
    },
    {
      candidate_id: IDS.c5, full_name: 'Олег Николаев', display_name: 'Олег Н.',
      category_id: 'backend:senior', category: 'Backend · Senior', grade: 'senior', experience_years: 8,
      city: 'Екатеринбург', formats: ['remote'], fsp_badge: { discipline: 'algo', text: 'ФСП · КМС' },
      fsp_discipline: 'algo', match: 91, test_score: 88,
      explanations: ['Тест Senior: 88/100', 'Вёл антифрод в банке 3 года'],
      skills: ['go', 'postgresql', 'kafka'], projects: ['Антифрод банка'], domains: ['fintech'], active_30d: true,
      email: 'o.nikolaev@mail.ru', phone: '+7 343 000-77-88',
    },
    {
      candidate_id: IDS.c6, full_name: 'Дина Рахимова', display_name: 'Дина Р.',
      category_id: 'frontend:middle', category: 'Frontend · Middle', grade: 'middle', experience_years: 4,
      city: 'Уфа', formats: ['remote'], fsp_badge: null, fsp_discipline: null, match: 78, test_score: 80,
      explanations: ['Тест Frontend Middle: 80/100', 'Go на бэкенде, часть стека совпадает'],
      skills: ['go', 'vue', 'postgresql'], projects: ['Кабинет мерчанта'], domains: ['fintech'], active_30d: true,
      email: 'd.rakhimova@mail.ru', phone: '+7 347 000-99-00',
    },
  ]
  const created = '2026-10-10T09:00:00.000Z'
  return {
    profile,
    settings: { visible: true, hidden_company_ids: [] },
    company: {
      id: IDS.company,
      name: 'Код Сибири',
      city: 'Новосибирск',
      size: '120',
      industry: 'Финтех',
      about: 'Платёжный процессинг для региональных банков.',
      recruiter_contact: { name: 'Анна Морозова', email: 'hr@kodsib.ru', phone: '+7 383 000-00-00' },
      benefits: ['dms'],
    },
    needs: [{
      id: IDS.need,
      title: 'Backend-разработчик в процессинг платежей',
      specialization: 'backend',
      grades: ['middle', 'senior'],
      salary_from: 250000,
      salary_to: 320000,
      formats: ['remote'],
      city: 'Новосибирск',
      must_skills: ['go', 'postgresql', 'kafka'],
      nice_skills: ['docker'],
      description,
      domain: 'fintech',
      stages: 2,
      status: 'open',
      company_id: IDS.company,
    }],
    requirements: {},
    people,
    favorites: [IDS.candidate],
    invitations: [
      {
        id: IDS.inv1, need_id: IDS.need, candidate_id: IDS.c5, status: 'accepted',
        title: 'Тимлид антифрода', message: 'Ищем человека, который вёл антифрод.', salary_from: 380000, salary_to: 450000,
        contact_channel: 'email', deadline: '2026-10-24T00:00:00.000Z', decline_reason: null, created_at: '2026-10-08T10:00:00.000Z',
        company_name: 'Код Сибири', need_title: 'Backend-разработчик в процессинг платежей', candidate_display_name: 'Олег Н.',
        candidate_email: null, candidate_phone: null, recruiter_contact: null,
      },
      {
        id: IDS.inv2, need_id: IDS.need, candidate_id: IDS.c2, status: 'viewed',
        title: 'Backend-разработчик (Go)', message: 'Команда антифрода, релиз раз в неделю.', salary_from: 250000, salary_to: 320000,
        contact_channel: 'telegram', deadline: '2026-10-20T00:00:00.000Z', decline_reason: null, created_at: '2026-10-09T10:00:00.000Z',
        company_name: 'Код Сибири', need_title: 'Backend-разработчик в процессинг платежей', candidate_display_name: 'Мария С.',
        candidate_email: null, candidate_phone: null, recruiter_contact: null,
      },
      {
        id: IDS.inv3, need_id: IDS.need, candidate_id: IDS.candidate, status: 'sent',
        title: 'Backend-разработчик (Go)', message: 'Перестраиваем процессинг и ищем человека в антифрод. Ваш результат по алгоритмам и опыт соревнований — то, что нужно.',
        salary_from: 250000, salary_to: 320000, contact_channel: 'telegram', deadline: '2026-10-24T00:00:00.000Z',
        decline_reason: null, created_at: created, company_name: 'Код Сибири', need_title: 'Backend-разработчик в процессинг платежей',
        candidate_display_name: 'Алексей К.', candidate_email: null, candidate_phone: null, recruiter_contact: null,
      },
      {
        id: IDS.inv4, need_id: IDS.need, candidate_id: IDS.c6, status: 'declined',
        title: 'Backend-разработчик (Go)', message: 'Будем рады познакомиться.', salary_from: 250000, salary_to: 320000,
        contact_channel: 'email', deadline: null, decline_reason: 'stack', created_at: '2026-10-05T10:00:00.000Z',
        company_name: 'Код Сибири', need_title: 'Backend-разработчик в процессинг платежей', candidate_display_name: 'Дина Р.',
        candidate_email: null, candidate_phone: null, recruiter_contact: null,
      },
    ],
    messages: {
      [IDS.inv1]: [{
        id: '88888888-8888-4888-8888-888888888881',
        author_user_id: IDS.userE,
        kind: 'text',
        body: 'Олег, спасибо, что приняли приглашение. Предлагаю созвон на этой неделе.',
        slots: null,
        hiring_stage: 'interview',
        created_at: '2026-10-08T12:00:00.000Z',
      }],
    },
    resumes: {},
    attempts: {},
    jobs: {},
    grade: {
      specialization: 'backend',
      declared_grade: 'middle',
      grade: 'middle',
      score: 82,
      ready_for_next: false,
      rank: 12,
      category_size: 340,
      skill_scores: [
        { skill_id: 'go', score: 88 },
        { skill_id: 'postgresql', score: 81 },
        { skill_id: 'kafka', score: 76 },
      ],
      history: [{
        attempt_id: '99999999-9999-4999-8999-999999999991',
        finished_at: '2026-10-10T12:00:00.000Z',
        score: 82,
        grade: 'middle',
      }],
    },
  }
}
