# Incident / retry

Jobs (`workspace.provision`, `workspace.teardown`, `sandbox.run`, `ai.analyze`, `ai.evaluate_answer`, `practice.expire_sweep`, `snapshot.interval_sweep`, `retention.sweep`) имеют статусы `QUEUED → RUNNING → SUCCEEDED | RETRYING | FAILED`. Backoff: `min(cap, base * 2^(attempt-1))`, default cap 5 мин. После `maxAttempts` запись уходит в dead-letter.

Правила:

- Permanent errors (`PermanentJobError`, validation, missing snapshot) не ретраятся.
- Sandbox timeout → `TIMED_OUT`, не `PASSED`.
- Infra error sandbox → `UNKNOWN` + безопасная причина.
- Submit с тем же idempotency key не создаёт вторую version.
- Snapshot hash mismatch — явная ошибка reconstruction, UI не подменяет более поздним состоянием.

При массовом provisioning/sandbox failure: остановить enqueue (масштаб), снять dead-letters, проверить Docker/runtime image, не расширять network policy.
