# Observability

- Logs: JSON lines, `packages/platform/src/observability.ts`. Sensitive keys (`token`, `secret`, `password`, `authorization`, `cookie`, `content`, `body`) заменяются на `[omitted]`; строки проходят `redactSecrets`.
- Metrics: in-process counters/histograms, scrape `GET /metrics` с platform token. Серии: `http_requests_total`, `http_request_duration_ms`, `jobs_queue_depth`, `jobs_enqueued_total`, `practice_transitions_total`, `telemetry_rejected_total`.
- Traces: `x-request-id` на каждый HTTP ответ; jobs несут `trace_id`.
- Alerts (рекомендуемые пороги): 5xx > 1% за 5 мин; `jobs_queue_depth{status="RETRYING"}` рост; доля sandbox `UNKNOWN`/`FAILED` с infraError; provisioning failure burst.

Dead letters: `GET /v1/ops/dead-letters`. Audit chain: `GET /v1/practices/:id/audit` (auditor).
