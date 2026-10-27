SHELL := /bin/bash
PY ?= .venv/bin/python
COMPOSE ?= docker compose

.PHONY: up down migrate seed reseed test e2e demo reindex psql benchmark dev-db dev-db-stop

.env:
	cp .env.example .env

up: .env            ## start postgres/mongo/qdrant/redis/backend/frontend and wait for health
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

migrate:            ## alembic upgrade head (as the owner role)
	$(COMPOSE) exec backend alembic upgrade head

seed:               ## realistic demo data + embeddings + matches
	$(COMPOSE) exec backend python -m app.seed

reseed:             ## wipe and regenerate the demo data
	$(COMPOSE) exec backend python -m app.seed --reset

reindex:            ## rebuild Qdrant from Postgres (source of truth)
	$(COMPOSE) exec backend python -m app.reindex

test:
	$(COMPOSE) exec backend pytest -q /repo/tests

e2e:                ## Playwright against the running stack (needs: make demo; cd tests/e2e && npm i && npx playwright install chromium)
	cd tests/e2e && npx playwright test

benchmark:          ## latency / agreement at 1k, 10k, 100k items (writes docs/benchmark.generated.md)
	$(COMPOSE) exec backend python /repo/scripts/benchmark.py --qdrant-url http://qdrant:6333

demo: up migrate seed
	@echo "Frontend: http://localhost:3000   API docs: http://localhost:8000/docs"
	@echo "Demo logins are listed in README.md"

psql:
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-lostfound} $${POSTGRES_DB:-lostfound}

# --- Docker-free fallback for the DB layer (userspace Postgres + pgvector via pip) ---
dev-db:             ## start a throwaway local Postgres in .pgdata and print its URL
	$(PY) scripts/local_pg.py start
dev-db-stop:
	$(PY) scripts/local_pg.py stop
