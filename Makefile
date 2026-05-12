.PHONY: install dev test lint format

install:
	uv sync

dev:
	uvicorn src.main:app --reload --port 8000

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check src/

format:
	uv run ruff format src/

run:
	uv run python scripts/run_local.py
