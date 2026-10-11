# RDE isolation

Каждый pair `candidate + practice` получает отдельный namespace:

```text
data/workspaces/<workspaceId>/
  repository/     # bind-mount в контейнер как /workspace
  git/            # GIT_DIR вне writable volume, кандидат его не видит
```

`dockerWorkspaceArgs` (`services/rde/src/drivers.ts`):

- `--network none`
- `--read-only` + tmpfs `/tmp` ограниченного размера
- `--cap-drop ALL --security-opt no-new-privileges --user 1000:1000`
- CPU / memory / pids-limit из `rde-policy-v1`
- hostname `workspace`, без host mounts кроме repository dir

Кандидат работает через browser IDE (`/candidate.html`). Прямой SSH к хосту, metadata service и другим workspace отклоняются: контейнер без сети и без ключей платформы.

Runtime image по умолчанию: `node:20-alpine` (`EPA_RUNTIME_IMAGE`).
