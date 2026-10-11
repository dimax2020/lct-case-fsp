FROM python:3.12-slim

WORKDIR /srv

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# INSTALL_ML=1 pulls sentence-transformers and torch for the worker.
ARG INSTALL_ML=0
RUN if [ "$INSTALL_ML" = "1" ]; then pip install --no-cache-dir -e ".[ml]"; \
    else pip install --no-cache-dir -e .; fi

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
