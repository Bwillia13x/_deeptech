PYTHON := python
PIP := $(PYTHON) -m pip
PKG := signal_harvester

export PYTHONPATH := src

.PHONY: install lint format test clean run init-db fetch analyze score notify top export api daemon snapshot verify site html serve prune stats quota retain

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
