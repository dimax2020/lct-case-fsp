# Engineering Process Analysis

Платформа оценки разработчиков: работодатель выдаёт practice, кандидат подключает расширение VS Code, дашборд показывает телеметрию открытой папки. Sandbox, review и отчёт по восьми измерениям остаются на сервере. SSH к инфраструктуре не выдаётся.

## Требования

- **Node.js 20.10+** и npm
- **git** (нужен серверу для истории коммитов)
- macOS или Linux

Необязательно:

- **Docker** и образ `node:20-alpine` — если хотите настоящую изоляцию workspace/sandbox (рекомендуется после того, как UI уже работает)
- **Ollama** с моделью `qwen2.5-coder:0.5b` — только для AI-анализа; submit, тесты и review работают без неё

## Первый запуск

Один процесс на каталог `data/`. Если порт 8080 занят — остановите старый API (`Ctrl+C`).

```bash
npm ci
npm run dev
```

В терминале появится `api listening`. Откройте http://127.0.0.1:8080/employer.html и введите своё имя. Пароль не нужен.

Если база после abort/kill не открывается, сервер сам откладывает сломанный `data/db` и создаёт новую. Старый `npm run seed` при работающем `dev` больше не нужен.

Ожидаемое предупреждение: `NON-ISOLATED local drivers` — в разработке runners идут на хосте, не в Docker.

### Работодатель

1. http://127.0.0.1:8080/employer.html
2. Введите своё имя и нажмите **Войти**
3. Введите название, описание и дедлайн → **Создать практику**. Затем загрузите свой проект (zip) или ТЗ
4. Нажмите **Создать ссылку для кандидата**. Когда кандидат укажет имя, оно появится в списке практик
5. Скопируйте ссылку из зелёной плашки. Она показывается **один раз**

На обзоре практики виден git-адрес, куда кандидат загружает проект, и статус расширения.

### Кандидат

1. Откройте ссылку-приглашение
2. Укажите своё имя. Дальше вход на `/candidate.html` — тем же именем, без пароля
3. Прочитайте согласие → **Принять и начать**
4. На странице практики — короткая инструкция, скачивание расширения и кнопка **Открыть мою ссылку**. Ссылка только ваша, код вставлять не нужно
5. Откройте папку проекта и отправьте код. Git пароль не спросит:

```bash
git remote add origin http://127.0.0.1:8080/git/<id практики>.git
git push -u origin HEAD
```

Работодатель видит коммиты и телеметрию во вкладке «Ход работы», а в списке практик — имя кандидата. Кнопка **Закрыть задачу** на странице кандидата снимает snapshot и запускает sandbox. Расширение задачу не закрывает.

### Расширение VS Code

```bash
npm run extension:compile
```

В Cursor/VS Code откройте этот репозиторий и запустите конфигурацию **EPA: расширение VS Code**. В новом окне откройте папку задания и выполните **EPA: Подключить практику**.

Кандидату этот запуск не нужен: он скачивает `epa-vscode.vsix` со своей страницы. Пакет собирается так:

```bash
npm run extension:package
```

Расширение не читает другие папки, нажатия клавиш, экран и буфер обмена вне редактора. Секреты в командах вырезаются до отправки. Новая персональная ссылка отзывает предыдущую сессию расширения.

Если загруженный проект — задание `auth-service`, его исходные тесты частично падают: это и есть задание.

## Docker-изоляция (после того как UI заработал)

```bash
docker pull node:20-alpine
```

Остановите `dev:local` (`Ctrl+C`). Тот же каталог `data/` можно использовать, **но не держите два API сразу**.

```bash
EPA_RDE_DRIVER=docker EPA_SANDBOX_DRIVER=docker npm run seed
EPA_RDE_DRIVER=docker EPA_SANDBOX_DRIVER=docker npm run dev
```

`npm run seed` / `npm run dev` без `:local` по умолчанию тоже ждут Docker. Если образа нет — provisioning workspace упадёт.

Проверка: `GET http://127.0.0.1:8080/healthz` → `"rdeDriver":"docker","sandboxDriver":"docker","isolated":true`.

## AI (необязательно)

Модель по умолчанию — `qwen2.5-coder:0.5b`. Если её нет, платформа берёт ближайшую установленную модель Qwen.

```bash
ollama pull qwen2.5-coder:0.5b
```

Ollama должна слушать `OLLAMA_URL` (по умолчанию http://127.0.0.1:11434). Без Ollama submit/тесты/review работают, анализ в отчёте будет `FAILED`.

## Если не стартует

### `RuntimeError: Aborted` / простыня `/tmp/pglite/share/postgresql/timezone/…`

Это падение **PGlite**, не «сломанный timezone». Обычно:

1. Уже запущен другой `npm run dev` или `npm run seed` на том же `data/`. Найдите и остановите:

   ```bash
   lsof -iTCP:8080 -sTCP:LISTEN
   # затем kill <pid>
   ```

2. База повреждена после abort. Снесите данные и начните заново (потеряются локальные practices):

   ```bash
   rm -rf data
   npm run seed:local
   npm run dev:local
   ```

### `EADDRINUSE` / port 8080

На порту уже кто-то слушает. Остановите старый процесс или задайте другой: `PORT=8081 npm run dev:local` и откройте http://127.0.0.1:8081

### Workspace не становится `READY`

При `dev:local` смотрите логи API. При Docker: контейнер `epa-ws-…`, образ `node:20-alpine`, Docker Desktop запущен.

### Вход не находит имя

Работодатель входит любым именем: первое использование создаёт кабинет. Кандидат сначала открывает ссылку приглашения и указывает имя там. Повторный вход — тем же именем на `/candidate.html`.

## Команды

| Команда | Назначение |
|---|---|
| `npm run seed:local` | Токены + PGlite, runners на хосте |
| `npm run dev:local` | API + UI + worker, runners на хосте |
| `npm run seed` / `npm run dev` | То же, но RDE/sandbox через Docker |
| `npm run typecheck` | TypeScript |
| `npm test` | unit + integration + e2e + security + performance |
| `npm run acceptance` | E2E сценария из спецификации, пишет `docs/runbooks/acceptance-result.md` |

## Переменные окружения

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `PORT` | `8080` | HTTP |
| `EPA_DATA_DIR` | `./data` | БД, git, snapshots, workspaces |
| `DATABASE_URL` | `pglite://<data>/db` | PGlite или `postgres://…` |
| `EPA_RDE_DRIVER` | `docker` | `local` только для разработки |
| `EPA_SANDBOX_DRIVER` | `docker` | `local` только для разработки |
| `EPA_RUNTIME_IMAGE` | `node:20-alpine` | Образ runners |
| `EPA_SIGNING_SECRET` | случайный в dev | Обязателен в production |
| `OLLAMA_URL` / `OLLAMA_MODEL` | localhost / `qwen2.5-coder:0.5b` | Локальный AI |

В production `local`-драйверы запрещены. Compose: `infra/deployments/docker-compose.yml`.

## Документация

- [Архитектура](docs/architecture/overview.md)
- [Рубрика оценки](docs/architecture/assessment.md)
- [Threat model](docs/threat-model/threat-model.md)
- [Consent и retention](docs/privacy/consent-and-retention.md)
- [Операционный runbook](docs/runbooks/operations.md)
