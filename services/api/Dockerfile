FROM python:3.12-slim

WORKDIR /srv

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Slow links to files.pythonhosted.org otherwise die on the default 15s read timeout.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300

# INSTALL_ML=1 pulls sentence-transformers and torch for the worker.
ARG INSTALL_ML=0
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ "$INSTALL_ML" = "1" ]; then pip install --timeout 300 --retries 10 -e ".[ml]"; \
    else pip install --timeout 300 --retries 10 -e .; fi

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
