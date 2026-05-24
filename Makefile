COMPOSE := docker compose -f docker/docker-compose.yml
COMPOSE_PROD := docker compose -f deploy/docker-compose.prod.yml

.PHONY: up down logs psql migrate revision current dev mobile test test-db-create test-db-migrate test-db-reset lint format typecheck check prod-build prod-migrate prod-up prod-down prod-logs

up:
	$(COMPOSE) up -d
	@echo "Postgres is up on $${DATABASE_URL:-postgresql+psycopg://me:me@localhost:5435/me}"

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f db

psql:
	$(COMPOSE) exec db psql -U me -d me

migrate:
	uv run alembic upgrade head

revision:
	@if [ -z "$(m)" ]; then echo "usage: make revision m=\"short message\""; exit 1; fi
	uv run alembic revision --autogenerate -m "$(m)"

current:
	uv run alembic current

be:
	uv run uvicorn app.main:app --reload

mobile:
	pnpm --filter mobile exec expo start --port 19000 --ios --clear

test:
	uv run pytest

# Test DB lifecycle. Operator runs `make test-db-migrate` once after `make up`
# (and again after any new migration). conftest does not manage the DB itself.
test-db-create:
	$(COMPOSE) exec -T db createdb -U me me_test 2>/dev/null || true

test-db-migrate: test-db-create
	DATABASE_URL=postgresql+psycopg://me:me@localhost:5435/me_test \
	JWT_SECRET=dummy-not-used-by-alembic-but-required-by-settings \
	uv run alembic upgrade head

test-db-reset: test-db-migrate
	$(COMPOSE) exec -T db psql -U me -d me_test -c "TRUNCATE users RESTART IDENTITY CASCADE"

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run ty check app

check: lint typecheck test

prod-build:
	$(COMPOSE_PROD) build

prod-migrate:
	$(COMPOSE_PROD) run --rm api alembic upgrade head

prod-up:
	$(COMPOSE_PROD) up -d

prod-down:
	$(COMPOSE_PROD) down

prod-logs:
	$(COMPOSE_PROD) logs -f api
