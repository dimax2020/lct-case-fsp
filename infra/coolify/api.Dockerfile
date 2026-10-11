# API для Coolify: в образ запечены справочник навыков, демо-данные и банк заданий,
# которые локальный compose монтирует из репозитория. Контекст сборки — корень репозитория.
FROM python:3.12-slim

WORKDIR /srv

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300

COPY services/api/pyproject.toml ./
COPY services/api/app ./app
COPY services/api/alembic ./alembic
COPY services/api/alembic.ini ./

ARG INSTALL_ML=0
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ "$INSTALL_ML" = "1" ]; then pip install --timeout 300 --retries 10 -e ".[ml]"; \
    else pip install --timeout 300 --retries 10 -e .; fi

COPY taxonomy /srv/taxonomy
COPY seed /srv/seed
COPY tmp_bank /srv/assessment
COPY services/api/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV TAXONOMY_DIR=/srv/taxonomy/data \
    SEED_DIR=/srv/seed \
    ASSESSMENT_BANK=/srv/assessment/bank.json

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
