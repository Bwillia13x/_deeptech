PYTHON := python
PIP := $(PYTHON) -m pip
PKG := signal_harvester
DOCKER_COMPOSE ?= docker compose

LOCUST_HOST ?= http://localhost:8000
LOCUST_USERS ?= 100
LOCUST_SPAWN_RATE ?= 10
LOCUST_RUN_TIME ?= 5m
LOCUST_REPORT ?= results/load_test_report.html
SQLITE_DB ?= var/app.db
PG_URL ?= postgresql://postgres:postgres@localhost:5432/signal_harvester
STAGING_ENV_FILE ?= .env.staging

export PYTHONPATH := src

.PHONY: install lint format test clean run init-db fetch analyze score notify top export api daemon snapshot verify site html serve prune stats quota retain staging-up staging-down staging-stack-up staging-stack-down monitoring-validate load-test migrate-postgres migrate-postgres-dry-run validate-postgres verify-all

install:
	pip install -e ".[dev]"

lint:
	ruff check src tests

format:
	ruff format src tests

test:
	python -m pytest tests/ -v

clean:
	rm -rf build/ dist/ *.egg-info/
	rm -rf .pytest_cache/
	find . -type d -name __pycache__ -delete
	find . -type f -name "*.pyc" -delete

run: init-db
	harvest pipeline

init-db:
	harvest init-db-cmd

fetch:
	harvest fetch

analyze:
	harvest analyze

score:
	harvest score

notify:
	harvest notify

top:
	harvest top

export:
	harvest export

api:
	harvest api

daemon:
	harvest daemon

snapshot:
	harvest snapshot

verify:
	harvest verify

site:
	harvest site

html:
	harvest html

serve:
	harvest serve

prune:
	harvest prune

stats:
	harvest stats

quota:
	harvest quota

retain:
	harvest retain

migrate-postgres:
	@if [ -z "$(PG_URL)" ]; then \
		echo "PG_URL environment variable (postgresql://user:pass@host/db) is required"; \
		exit 1; \
	fi
	$(PYTHON) scripts/migrate_to_postgresql.py --source $(SQLITE_DB) --target $(PG_URL)

migrate-postgres-dry-run:
	@if [ -z "$(PG_URL)" ]; then \
		echo "PG_URL environment variable (postgresql://user:pass@host/db) is required"; \
		exit 1; \
	fi
	$(PYTHON) scripts/migrate_to_postgresql.py --source $(SQLITE_DB) --target $(PG_URL) --dry-run

validate-postgres:
	@if [ -z "$(PG_URL)" ]; then \
		echo "PG_URL environment variable (postgresql://user:pass@host/db) is required"; \
		exit 1; \
	fi
	PG_URL="$(PG_URL)" DATABASE_URL="$(PG_URL)" $(PYTHON) scripts/validate_postgresql.py

staging-up:
	./scripts/deploy-monitoring-docker.sh

staging-down:
	$(DOCKER_COMPOSE) -f docker-compose.monitoring.yml down

staging-stack-up:
	@if [ ! -f "$(STAGING_ENV_FILE)" ]; then \
		echo "Missing $(STAGING_ENV_FILE). Copy .env.staging.example and populate hostnames/secrets before running staging-stack-up."; \
		exit 1; \
	fi
	$(DOCKER_COMPOSE) --env-file $(STAGING_ENV_FILE) -f docker-compose.staging.yml up -d

staging-stack-down:
	@if [ ! -f "$(STAGING_ENV_FILE)" ]; then \
		echo "Missing $(STAGING_ENV_FILE). Copy .env.staging.example and populate hostnames/secrets before running staging-stack-down."; \
		exit 1; \
	fi
	$(DOCKER_COMPOSE) --env-file $(STAGING_ENV_FILE) -f docker-compose.staging.yml down

staging-schema-init:
	@if [ ! -f "$(STAGING_ENV_FILE)" ]; then \
		echo "Missing $(STAGING_ENV_FILE). Copy .env.staging.example and populate hostnames/secrets before running staging-schema-init."; \
		exit 1; \
	fi
	CMD="python scripts/init_postgres_schema.py"; \
	if [ "$(DRY_RUN)" = "1" ]; then \
		CMD="$$CMD --dry-run"; \
	fi; \
	$(DOCKER_COMPOSE) --env-file $(STAGING_ENV_FILE) -f docker-compose.staging.yml run --rm signal-harvester $$CMD

monitoring-validate:
	./scripts/validate-monitoring.sh

load-test:
	mkdir -p results
	locust -f scripts/load_test.py --host=$(LOCUST_HOST) --users=$(LOCUST_USERS) --spawn-rate=$(LOCUST_SPAWN_RATE) --run-time=$(LOCUST_RUN_TIME) --headless --html $(LOCUST_REPORT)

ci: install lint test

verify-all: lint test
	@echo "Running full verification suite..."
	@echo "1. Backend linting and tests complete"
	@echo "2. Building frontend..."
	cd frontend && npm install && npm run build
	@echo "3. Type checking frontend..."
	cd frontend && npm run typecheck
	@echo "4. Profiling critical queries (Phase Three performance analyzers)"
	harvest db analyze-performance --iterations 25
	@echo "✓ All verifications passed!"
