.PHONY: setup lint arch test cov run audit web-install web-dev web-check web-build legacy-build

VENV ?= .venv
PY := $(VENV)/bin/python

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install -r requirements-portfolio.txt
	$(PY) -m pip install pytest-cov ruff pip-audit import-linter

lint:
	$(PY) -m ruff check .

arch:
	PYTHONPATH=src $(VENV)/bin/lint-imports

test:
	PYTHONPATH=src $(PY) -m pytest -q

cov:
	PYTHONPATH=src $(PY) -m pytest -q --cov --cov-report=term

run:
	PYTHONPATH=src $(PY) -m idx_evidence_lab.web_app

audit:
	$(PY) -m pip_audit -r requirements-portfolio.txt

web-install:
	cd frontend && npm ci

web-dev:
	cd frontend && npm run dev

web-check:
	cd frontend && npm run typecheck && npm run lint && npm run format:check && npm test

web-build:
	cd frontend && npm run build

legacy-build:
	$(PY) scripts/build_legacy_ui.py
