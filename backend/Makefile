PYTHON ?= python3
VENV ?= .venv

install:
	./install.sh

test:
	$(VENV)/bin/python -m pytest -q

run:
	$(VENV)/bin/python -m uvicorn app.main:app --reload

