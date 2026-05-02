COMPOSE := docker compose -f docker/docker-compose.yml

.PHONY: up down logs psql migrate revision current dev test lint format typecheck check

up:
	$(COMPOSE) up -d
	@echo "Postgres is up on $${DATABASE_URL:-postgresql+psycopg://me:me@localhost:5434/me}"

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

dev:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run ty check app

check: lint typecheck test
