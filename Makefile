# ============================================================================
# NEXUS AI TRAFFIC CONTROL - developer task runner
# Works with GNU make (Git Bash / WSL / Linux / macOS).
# Windows users without `make` can run the equivalent scripts/*.ps1 files.
# ============================================================================
.DEFAULT_GOAL := help
PY := python
VENV := .venv
BIN := $(VENV)/Scripts

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: install-backend install-frontend ## Install all dependencies

.PHONY: install-backend
install-backend: ## Create venv + install backend deps
	$(PY) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/python -m pip install -r backend/requirements.txt

.PHONY: install-frontend
install-frontend: ## Install frontend deps
	cd frontend && npm install

.PHONY: backend
backend: ## Run the FastAPI backend (reload)
	$(BIN)/uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000

.PHONY: frontend
frontend: ## Run the Vite dev server
	cd frontend && npm run dev

.PHONY: dev
dev: ## Run backend + frontend together
	$(MAKE) -j2 backend frontend

.PHONY: test
test: test-backend test-frontend ## Run all tests

.PHONY: test-backend
test-backend: ## Run backend pytest suite
	cd backend && ../$(BIN)/python -m pytest -q

.PHONY: test-frontend
test-frontend: ## Run frontend vitest suite
	cd frontend && npm run test

.PHONY: train
train: ## Train an agent: make train AGENT=a2c EPISODES=200
	$(BIN)/python -m scripts.training.train --agent $(AGENT) --episodes $(EPISODES)

.PHONY: evaluate
evaluate: ## Evaluate a checkpoint vs fixed-time + untrained: make evaluate AGENT=a2c SCENARIO=emergency_heavy
	$(BIN)/python -m scripts.training.evaluate --agent $(AGENT) --scenario $(SCENARIO)

.PHONY: experiment
experiment: ## Run an experiment batch from a config file: make experiment CONFIG=...
	$(BIN)/python -m scripts.experiments.run --config $(CONFIG)

.PHONY: validate
validate: ## Run repository validation checks
	$(BIN)/python -m scripts.validation.check_all

.PHONY: lint
lint: ## Lint backend + frontend
	$(BIN)/ruff check backend scripts tests
	cd frontend && npm run lint

.PHONY: clean
clean: ## Remove caches and build artifacts
	rm -rf frontend/dist frontend/.vite .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
