# Архитектура MVP

Платформа оценивает решение кандидата и воспроизводимый процесс его создания. Недоверенный код выполняется только в изолированном RDE workspace и в отдельном sandbox проверки. Кандидат не получает SSH/shell к control plane, другим workspace или внутренней сети.

## Компоненты

```text
Web UI (Employer / Candidate)     apps/web/public
VS Code extension (telemetry)     extensions/vscode
        │
API gateway + AuthN/AuthZ         apps/api
        ├── Practice & invitation  services/practice
        ├── RDE provisioner        services/rde
        ├── Git                    services/git
        ├── Telemetry ingestion    services/timeline
        ├── Timeline & snapshots   services/timeline, services/snapshots
        ├── Sandbox orchestrator   services/sandbox
        ├── Review                 services/review
        ├── AI orchestration       services/ai-orchestrator
        └── Assessment / report    services/assessment
              │
 DB (Postgres/PGlite) | append-only events | object store | git storage | job queue | isolated runners
```

Доменная логика живёт в `packages/domain` (статусы, consent, policies, rubric). Контракты API/телеметрии/AI — в `packages/contracts`. AuthZ — deny-by-default таблица действий в `packages/authz`. Адаптеры инфраструктуры не протекают в доменную модель.

## Потоки данных

1. Employer создаёт `Practice` из шаблона и одноразовое `Invitation` (в БД хранится только hash токена).
2. Candidate redeem → consent (`consent-v1`) → start. Worker provision'ит уникальный RDE namespace.
3. После старта кандидат получает одноразовый код и подключает расширение VS Code. Оно шлёт телеметрию только открытой папки задания. Browser IDE остаётся запасным путём к изолированному workspace; SSH по-прежнему нет.
4. Расширение и workspace agent пишут telemetry batches `(session_id, sequence)` с idempotency. Timeline показывает безопасные summaries и клиента `vscode`, не сырые клавиши. Heartbeat обновляет «на связи» в дашборде.
5. Snapshots: первый — полный manifest, далее patch относительно базы, периодический checkpoint. Submit снимает immutable snapshot.
6. Sandbox получает **копию** snapshot (не writable workspace), гоняет тесты с CPU/RAM/PID/time/network=none.
7. Review, requirement change и повторный submit связываются версиями. Прошлые snapshot не мутируются.
8. AI (локальный Ollama Qwen3-Coder 14B через `CodeAnalysisProvider`) анализирует только файлы выбранного snapshot. Сбой AI не блокирует submit/tests/review.
9. Assessment `rubric-v1` считает восемь измерений; overall помечен как рекомендация до approve работодателя.
10. После `COMPLETED`/`EXPIRED` workspace уничтожается. Retention удаляет artifacts и оставляет минимальный audit.

## Идентификаторы и идемпотентность

Сервер генерирует id (`prc_`, `ws_`, …) и timestamps. Записи telemetry, submit и create practice принимают `Idempotency-Key`. Повтор с тем же ключом и тем же hash запроса возвращает исходный результат.

## Версии политик

| Политика | Версия |
|---|---|
| Consent | `consent-v1` |
| RDE | `rde-policy-v1` |
| Sandbox | `sandbox-policy-v1` |
| Rubric | `rubric-v1` |
| AI | см. `AI_POLICY_VERSION` в `@epa/ai-provider` |
