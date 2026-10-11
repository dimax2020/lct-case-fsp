COMPOSE_FILE := infra/compose/docker-compose.yml
COMPOSE := docker compose -f $(COMPOSE_FILE)
API := services/api
PY := $(API)/.venv/bin

.PHONY: up down logs migrate seed test lint e2e reset venv epa

venv:
	cd $(API) && uv venv --python 3.12 .venv
	uv pip install -e "./$(API)[dev]" --python $(PY)/python

up:
	COMPOSE_BAKE=false $(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

migrate:
	$(COMPOSE) exec -T api alembic upgrade heads

seed:
	$(COMPOSE) exec -T api python -m app.demo.seed

test:
	cd $(API) && .venv/bin/python -m pytest -q

lint:
	cd $(API) && .venv/bin/ruff check . && .venv/bin/mypy app && .venv/bin/lint-imports
	cd apps/web && npx eslint .

e2e:
	cd tests/e2e && npx playwright test

reset:
	$(COMPOSE) down -v
	COMPOSE_BAKE=false $(COMPOSE) up -d --build

epa:
	cd services/epa && EPA_RDE_DRIVER=local EPA_SANDBOX_DRIVER=local npm run dev
