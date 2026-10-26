.PHONY: help install test test-backend test-frontend eval lint build docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  make install        Install backend and frontend dependencies"
	@echo "  make test           Run all tests (backend and frontend)"
	@echo "  make test-backend   Run pytest test suite"
	@echo "  make test-frontend  Run frontend vitest test suite"
	@echo "  make eval           Run 271-row benchmark evaluation suite"
	@echo "  make lint           Run code linters and typechecks"
	@echo "  make build          Build production frontend bundle"
	@echo "  make docker-up      Start containerized services via docker-compose"
	@echo "  make docker-down    Stop containerized services"

install:
	pip install -r backend/requirements-dev.txt
	cd frontend && npm install

test: test-backend test-frontend eval

test-backend:
	cd backend && python -m pytest

test-frontend:
	cd frontend && npm test

eval:
	python eval/run_eval.py

lint:
	ruff check backend/app backend/tests
	cd frontend && npx tsc --noEmit

build:
	cd frontend && npm run build

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down
