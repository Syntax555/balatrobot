.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck quality fixtures all

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
	@echo "$(YELLOW)Running stylua formatter...$(RESET)"
	stylua src/lua

typecheck: ## Run type checker
	@echo "$(YELLOW)Running type checker...$(RESET)"
	ty check

quality: lint typecheck format ## Run all code quality checks
	@echo "$(GREEN)✓ All checks completed$(RESET)"

fixtures: ## Generate fixtures
	@echo "$(YELLOW)Starting Balatro...$(RESET)"
	balatrobot --fast --debug
	@echo "$(YELLOW)Generating all fixtures...$(RESET)"
	python tests/fixtures/generate.py

all: lint format typecheck ## Run all code quality checks
	@echo "$(GREEN)✓ All checks completed$(RESET)"
