# Sandbox isolation

После submit оркестратор материализует **immutable snapshot** в отдельный каталог и запускает тесты драйвером, отличным от writable RDE.

`dockerSandboxArgs` (`services/sandbox/src/drivers.ts`):

- `--network none --read-only --cap-drop ALL --security-opt no-new-privileges`
- snapshot mount `/src:ro`, рабочая копия только в size-limited tmpfs
- timeout `KILL`, ulimit fsize/nofile, pids-limit
- без platform env и без Docker credentials внутри контейнера

Лог truncate + redact; coverage в summary только если задание включило coverage. Известные adversarial fixtures: `packages/test-fixtures/sandbox/{escape-attempts,fork-bomb,endless-loop,memory-hog}`.
