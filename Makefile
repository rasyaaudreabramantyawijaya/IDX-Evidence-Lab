.PHONY: setup lint test cov run audit

VENV ?= .venv
PY := $(VENV)/bin/python

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install -r requirements-portfolio.txt
	$(PY) -m pip install pytest-cov ruff pip-audit

lint:
	$(PY) -m ruff check .

test:
	PYTHONPATH=src $(PY) -m pytest -q

cov:
	PYTHONPATH=src $(PY) -m pytest -q --cov --cov-report=term

run:
	PYTHONPATH=src $(PY) -m idx_evidence_lab.web_app

audit:
	$(PY) -m pip_audit -r requirements-portfolio.txt
