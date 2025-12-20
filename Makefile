.PHONY: help install test test-unit test-integration test-scenarios lint format type-check clean

help:
	@echo "ATS-AI v3.30 — Makefile commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install dependencies via poetry"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run all tests with coverage"
	@echo "  make test-unit        Run unit tests only"
	@echo "  make test-integration Run integration tests only"
	@echo "  make test-scenarios   Run scenario tests only"
	@echo ""
	@echo "Quality:"
	@echo "  make lint             Run ruff linter"
	@echo "  make format           Format code with black"
	@echo "  make type-check       Run mypy type checking"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean            Remove build artifacts and cache"

install:
	poetry install

test:
	poetry run pytest

test-unit:
	poetry run pytest tests/unit/

test-integration:
	poetry run pytest tests/integration/

test-scenarios:
	poetry run pytest tests/scenarios/

lint:
	poetry run ruff check src/ tests/

format:
	poetry run black src/ tests/

type-check:
	poetry run mypy src/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf htmlcov/ .coverage coverage.xml
