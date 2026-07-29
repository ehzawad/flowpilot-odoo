SHELL := /bin/bash

.PHONY: sync dev up down seed api worker web test lint typecheck smoke eval migrate

sync:
	uv sync --all-groups
	cd apps/web && npm ci

dev:
	cp -n .env.example .env || true
	docker compose up --build

up:
	docker compose up --build -d

down:
	docker compose down

seed:
	uv run flowpilot-seed

api:
	uv run flowpilot-api

worker:
	uv run flowpilot-worker

web:
	cd apps/web && npm run dev

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy src
	cd apps/web && npm run typecheck

smoke:
	uv run flowpilot-smoke

eval:
	uv run python evals/run_local.py

migrate:
	uv run alembic upgrade head
