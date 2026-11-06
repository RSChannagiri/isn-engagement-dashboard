PY ?= .venv/bin/python

.PHONY: setup seed etl app test lint

setup:
	python3.12 -m venv .venv
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install -e . --no-deps

seed:
	$(PY) -m isn_engagement.seed --out data/raw

etl:
	$(PY) -m isn_engagement.etl --raw data/raw --db data/isn.db --report data/quality_report.md

app:
	$(PY) -m streamlit run app.py

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .
