# Threat model (MVP)

Доверие: control plane и работодатель организации — trusted для своих practice. Код кандидата, содержимое workspace, README и ответы интервью — untrusted. Локальный AI-вывод — untrusted до schema/evidence validation.

## Активы

- Решения и snapshots кандидатов, telemetry, sandbox logs
- Invite/session/staff tokens
- Platform secrets (`EPA_SIGNING_SECRET`, DB)
- Соседние workspace и control plane

## Контроли по категориям

| Угроза | Контроль |
|---|---|
| Кража/перебор invite | Токен только как SHA-256; rate limit `/v1/invitations/redeem`; одноразовый consume в транзакции |
| Горизонтальный доступ | Scope практики из БД, не из body; RBAC deny-by-default; candidate видит только свои practice |
| Path traversal / symlink escape | `normalizeWorkspacePath`, `O_NOFOLLOW`, запрет `..`, archive/size limits |
| Выход из RDE/sandbox | `network=none`, read-only root, `cap-drop ALL`, `no-new-privileges`, unprivileged uid, PID/CPU/RAM/tmpfs limits; git-dir вне volume |
| Подмена submission | Immutable snapshot + content hash; повторный submit — новая version; object store write-once |
| Подделка telemetry | Только agent principal своей session; sequence/idempotency; gap → 409, не тихий skip |
| Утечка секретов | redact в командах/логах/промптах; secret filenames не в AI context; structured logs без token/secret keys |
| SSRF / signed URL | Object keys непрозрачны; доступ через HMAC token с TTL; не публичный URL |
| Prompt injection | System policy не из репозитория; evidence должен существовать в snapshot; groundedness validator; UI рендерит findings как текст |
| XSS в review | `renderSafeMarkdown` после HTML-escape; CSP `script-src 'self'` |
| DoS очереди/API | body limit, batch size, rate limits, job maxAttempts, sandbox timeout/kill |
| Local drivers в prod | `loadConfig` запрещает `rde/sandbox=local` при `NODE_ENV=production` |

## Что система явно не утверждает

Нет DRM и нет детекции ChatGPT. Large insertion, прерывистый трекинг и необычная скорость — сигналы для человека, не proof of cheating. Пробел телеметрии отображается как interruption, не как обвинение.

## Остаточный риск

Docker-in-Docker / socket для provisioner требует, чтобы API-хост сам был изолирован. Kernel exploits вне модели MVP; для production нужен отдельный node pool для runners.
