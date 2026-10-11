#!/bin/sh
# Подготовка базы перед стартом API.
#   AUTO_MIGRATE=1          — alembic upgrade heads
#   SEED_ON_START=always    — каждый старт возвращает демо-данные в исходное состояние
#   SEED_ON_START=if-empty  — демо-данные загружаются только в пустую базу
#   SEED_ON_START=off       — без сидов (по умолчанию; воркер использует тот же образ)
set -e
cd /srv

if [ "${AUTO_MIGRATE:-0}" = "1" ]; then
  echo "[entrypoint] alembic upgrade heads"
  alembic upgrade heads
fi

case "${SEED_ON_START:-off}" in
  always)
    echo "[entrypoint] seeding demo data"
    python -m app.demo.seed || echo "[entrypoint] seed failed, starting anyway"
    ;;
  if-empty)
    echo "[entrypoint] seeding demo data if the database is empty"
    python -m app.demo.seed --if-empty || echo "[entrypoint] seed failed, starting anyway"
    ;;
esac

exec "$@"
