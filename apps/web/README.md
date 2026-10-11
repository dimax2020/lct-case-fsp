# Карьера ФСП — веб-приложение

Nuxt 4 (Vue 3, SSR) по дизайн-системе «Чемпионат России». Данные берутся из API `services/api` через BFF-прокси Nuxt (`/api/*`), вход — через ФСП ID на Keycloak (`nuxt-oidc-auth`). Для показа без бэкенда есть мок-режим.

## Запуск

```bash
npm install
npm run dev                                # http://localhost:3000, нужен запущенный API и Keycloak
NUXT_PUBLIC_API_MOCKS=1 npm run dev        # без бэкенда: ответы API имитируются в браузере
npx vue-tsc --noEmit                       # проверка типов
npm run build && node .output/server/index.mjs
npm run api:types                          # пересобрать app/api/schema.d.ts из contracts/openapi.yaml
```

В составе всего стенда приложение поднимается через `make up` из корня репозитория.

## Маршруты

| Путь | Экран |
|---|---|
| `/` | Лендинг |
| `/auth` | Выбор роли и согласие, дальше — вход или регистрация в ФСП ID (`?role=employer`, `?mode=login`) |
| `/legal/privacy`, `/legal/terms` | Политика обработки данных и условия публикации профиля |
| `/candidate/onboarding` | Опрос (отрасль, специализация, грейд) и тест на грейд. Сюда попадает новый кандидат после регистрации |
| `/candidate/profile` | Профиль: условия поиска, резюме, проекты, ФСП, подсказки, рабочий стиль |
| `/candidate/grade` | Тесты и грейд: категория, лестница, пересдача, история, вход в тест рабочего стиля |
| `/candidate/psych` | Тест рабочего стиля: три части и результат |
| `/candidate/invites` | Приглашения: принять или отклонить с причиной |
| `/candidate/chat` | Переписка по принятым приглашениям, выбор слота интервью |
| `/candidate/vacancy` | Вакансии и отклики с сопроводительным сообщением |
| `/candidate/settings` | Приватность, ФСП ID, согласия, аккаунт |
| `/employer/need` | Описание потребности и запуск подборки |
| `/employer/pool` | Подборка, весь банк и избранные; из банка можно пригласить |
| `/employer/candidate` | Карточка кандидата: объяснение, PDF, тест рабочего стиля, форма приглашения |
| `/employer/invites` | Приглашения и их статусы |
| `/employer/chat` | Переписка и этапы найма |
| `/employer/vacancies` | Публикация и редактирование вакансий, работа с откликами |
| `/employer/company` | Профиль компании: сайт, логотип, контакты |

## Структура

```
app/
  assets/css/tokens.css      токены дизайн-системы (цвета, срезы, шрифты; тёмная и светлая тема)
  assets/css/fsp.css         стили компонентов дизайн-системы
  assets/css/ui.css          каркас страниц, типографика, утилиты и адаптив (960 / 640 px)
  components/fsp/*.vue       Button, Input, Chip, Checkbox, Tabs, Header, Plate, StatusBadge, Tag, …
  components/PsychResultView.vue  результат теста рабочего стиля (вид кандидата и HR)
  components/CodeEditor.vue  Monaco с подсветкой Python/Go; пока грузится — обычное поле
  composables/               useApi (типизированный клиент), useScreen, useToast, useTheme, useNotifications
  utils/labels.ts            подписи, форматирование, навигация кабинетов
  utils/psych.ts             типы и цвета теста рабочего стиля
  api/schema.d.ts            типы из contracts/openapi.yaml
  api/mock/                  мок-режим: данные, обработчики, подсчёт теста рабочего стиля
server/
  middleware/auth.ts         доступ к кабинетам по роли, прокси /api → API с Bearer-токеном, /auth/role
  utils/auth-pages.ts        куда вести после выбора роли, страница выбора роли
```

Компоненты подключаются автоматически с префиксом `Fsp`: `<FspButton>`, `<FspChip>` и так далее.

## Правила оформления

- Синий (`--primary`) — только для того, что можно нажать. Фиолетовый (`--accent-mark`) — бейджи и выделения. Зелёный, жёлтый, красный — статусы и прогресс.
- В тесте рабочего стиля цвета DISC — `--disc-red`, `--disc-yellow`, `--disc-green`, `--disc-blue`.
- Заголовки — Wadik капсом. Повторяющиеся стили — классы из `ui.css` (`fsp-page`, `fsp-eyebrow`, `u-row-wrap`, …), а не инлайн-стили.
- Тема хранится в cookie `fsp-theme`, поэтому сервер сразу отдаёт страницу в нужной теме.
