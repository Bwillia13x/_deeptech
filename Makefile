PYTHON := python
PIP := $(PYTHON) -m pip
PKG := signal_harvester

export PYTHONPATH := src

.PHONY: install lint format test clean run init-db fetch analyze score notify top export api daemon snapshot verify site html serve prune stats quota retain verify-all

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
