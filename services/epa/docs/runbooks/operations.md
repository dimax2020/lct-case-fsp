# Runbook: деплой и операции

## Локальный запуск

Пошаговая инструкция для человека (UI, токены, PGlite, типичные ошибки) — в [README](../../README.md). Кратко:

```bash
npm ci
# сервер не должен быть запущен: PGlite — один процесс на ./data
npm run seed:local
npm run dev:local
```

http://127.0.0.1:8080 — UI работодателя и кандидата. Для изолированных runners: образ `node:20-alpine` и `npm run seed` / `npm run dev` (драйверы Docker по умолчанию).

AI по умолчанию: локальный Ollama `qwen2.5-coder:0.5b` (`OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_SETUP_MODEL`). Если Ollama недоступна, submit/tests/review продолжают работать; AI job уходит в `FAILED`/`RETRYING`.

## Production compose

См. `infra/deployments/docker-compose.yml`. Обязательны:

- `NODE_ENV=production`
- `EPA_SIGNING_SECRET` (≥ 32 bytes)
- `EPA_RDE_DRIVER=docker` и `EPA_SANDBOX_DRIVER=docker`
- volume для `EPA_DATA_DIR`
- Docker socket **только** если этот хост выделен под runners

Postgres: задайте `DATABASE_URL=postgres://…` и поднимите отдельный worker (`EPA_EMBEDDED_WORKER=false`, `npm run worker`). PGlite — single-process, для одного инстанса API.

## Наблюдаемость

- Structured JSON logs (секреты redacted, ключи token/password/authorization опущены).
- `GET /metrics` (principal `platform`) — Prometheus text: HTTP latency/count, queue depth, transitions.
- `GET /v1/ops/dead-letters` — jobs, исчерпавшие retry/backoff.
- `GET /v1/practices/:id/audit` — только `auditor`; chain hash.
- Алерты: рост `jobs_queue_depth`, 5xx, массовые `workspace.provision` / `sandbox.run` failure (см. `infra/observability`).

## Типовые сбои

| Симптом | Действие |
|---|---|
| Workspace `FAILED` | `/v1/practices/:id` → `failureReason`; dead-letter `workspace.provision`; не выдавать SSH |
| Тесты `UNKNOWN`/`FAILED` после infra error | Не считать pass; смотреть safe log через short-lived `/v1/test-runs/:id/log-link` |
| AI `FAILED` | Core flow жив; retry job или проверить Ollama; UI должен показать отсутствие анализа |
| Telemetry 409 gap | Агент ресендит с `nextExpectedSequence`; UI — interruption, не cheating |
| Retention 410 | Ожидаемо после sweep; audit `retention.purged` остаётся |

## Тесты в CI

`npm run typecheck`, `test:unit`, `test:integration`, `test:e2e`, `test:security`, `test:performance`. Docker isolation tests пропускаются, если нет образа `node:20-alpine`. E2E acceptance: `npx vitest run tests/e2e/acceptance.test.ts` или `npm run acceptance`.
