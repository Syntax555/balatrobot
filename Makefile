.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck quality test all

# Colors for output
YELLOW := \033[33m
GREEN := \033[32m
BLUE := \033[34m
RED := \033[31m
RESET := \033[0m

help: ## Show this help message
	@echo "$(BLUE)BalatroBot Development Makefile$(RESET)"
	@echo ""
	@echo "$(YELLOW)Available targets:$(RESET)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(GREEN)%-18s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install balatrobot and all dependencies (including dev)
	@echo "$(YELLOW)Installing all dependencies...$(RESET)"
	uv sync --all-extras

lint: ## Run ruff linter (check only)
	@echo "$(YELLOW)Running ruff linter...$(RESET)"
	ruff check --fix --select I .
	ruff check --fix .

format: ## Run ruff and mdformat formatters
	@echo "$(YELLOW)Running ruff formatter...$(RESET)"
	ruff check --select I --fix .
	ruff format .
	@echo "$(YELLOW)Running mdformat formatter...$(RESET)"
	mdformat ./docs README.md CLAUDE.md

typecheck: ## Run type checker
	@echo "$(YELLOW)Running type checker...$(RESET)"
	basedpyright src/balatrobot

quality: lint typecheck format ## Run all code quality checks
	@echo "$(GREEN)✓ All checks completed$(RESET)"

fixtures: ## Generate fixtures
	@echo "$(YELLOW)Generating fixtures...$(RESET)"
	python tests/fixtures/generate.py

test: ## Run tests head-less
	@echo "$(YELLOW)Starting Balatro...$(RESET)"
	python balatro.py start --fast --debug
	@command -v aerospace >/dev/null 2>&1 && aerospace workspace 3
	@echo "$(YELLOW)Running tests...$(RESET)"
	pytest tests/lua

all: lint format typecheck test ## Run all code quality checks and tests
	@echo "$(GREEN)✓ All checks completed$(RESET)"
