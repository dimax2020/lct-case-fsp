# Consent и retention

## Consent notice (`consent-v1`)

До `Start practice` кандидат видит полный текст. Без `accepted: true` и совпадения `textHash` статус не переходит в `STARTED`.

Кандидат работает в своём VS Code. Расширение смотрит только открытую папку задания. Собирается только workspace-telemetry:

- session start/end
- file created/changed/saved/deleted (относительный путь, объём изменения)
- test started/finished
- terminal command после redact секретов
- git commit (SHA, message, files)
- snapshot created
- large insertion **signal** (не вердикт)

Не собирается: нажатия клавиш, экран/камера/микрофон, буфер вне редактора workspace, файлы и процессы вне workspace, неразрешённые secrets.

Срок хранения задаётся `organisations.retention_days` (по умолчанию `EPA_RETENTION_DAYS`, 90). Текст уведомления включает purpose, retention и кто видит данные (employer организации, аудитор на чтение, сам кандидат).

## Retention

После `COMPLETED` или `EXPIRED`:

1. Workspace teardown (контейнер + writable volume). Immutable snapshots/logs живут до дедлайна retention.
2. По истечении `retentionDeadline(terminalAt, artifactRetentionDays)` platform-роль вызывает `/v1/ops/retention/sweep`.
3. Удаляются snapshots, telemetry events, object-store artifacts, sandbox logs. Остаётся append-only audit (`retention.purged`) и минимальные метаданные practice.
4. Повторный доступ к purged snapshot/report даёт `410 GONE`.

Аудит критических действий (invite, consent, status, snapshot, review, export/delete) пишется с chain-hash; приложение не может переписать прошлые строки.
