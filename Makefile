# =============================================================================
# MurasFood developer commands.
#
# Everything runs inside Docker so the toolchain is identical on every machine.
# On Windows use Git Bash / WSL, or run the underlying commands directly.
# =============================================================================

COMPOSE ?= docker compose
API     ?= $(COMPOSE) exec -T api
WEB     ?= $(COMPOSE) exec -T web

.DEFAULT_GOAL := help
.PHONY: help up down restart build logs ps shell dbshell migrate makemigrations \
        seed superuser test test-api test-web lint lint-api lint-web format \
        typecheck openapi clean backup restore

help: ## List available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- Stack lifecycle ---------------------------------------------------------
up: ## Start the development stack
	$(COMPOSE) up -d --build

down: ## Stop the stack (keeps volumes)
	$(COMPOSE) down

restart: ## Restart every service
	$(COMPOSE) restart

build: ## Rebuild images without starting
	$(COMPOSE) build

logs: ## Tail logs from every service
	$(COMPOSE) logs -f --tail=100

ps: ## Show service status
	$(COMPOSE) ps

# --- Backend -----------------------------------------------------------------
shell: ## Open a Django shell
	$(COMPOSE) exec api python manage.py shell

dbshell: ## Open a psql session
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-murasfood} -d $${POSTGRES_DB:-murasfood}

migrate: ## Apply database migrations
	$(API) python manage.py migrate

makemigrations: ## Generate migrations from model changes
	$(API) python manage.py makemigrations

seed: ## Load obviously-fake demo data (never real merchant data)
	$(API) python manage.py seed_demo

superuser: ## Create a platform administrator
	$(COMPOSE) exec api python manage.py createsuperuser

openapi: ## Write the OpenAPI schema to docs/api/openapi.yaml
	$(API) python manage.py spectacular --file /app/openapi.yaml
	$(COMPOSE) cp api:/app/openapi.yaml docs/api/openapi.yaml

# --- Quality gates -----------------------------------------------------------
test: test-api test-web ## Run every test suite

test-api: ## Run backend tests (pytest)
	$(API) pytest

test-web: ## Run frontend tests (vitest)
	$(WEB) npm run test

lint: lint-api lint-web ## Lint everything

lint-api: ## Ruff lint + format check
	$(API) ruff check .
	$(API) ruff format --check .

lint-web: ## ESLint
	$(WEB) npm run lint

format: ## Auto-format backend and frontend
	$(API) ruff format .
	$(API) ruff check --fix .
	$(WEB) npm run lint:fix

typecheck: ## mypy + vue-tsc
	$(API) mypy .
	$(WEB) npm run typecheck

# --- Operations --------------------------------------------------------------
backup: ## Dump the database to infrastructure/backups
	bash infrastructure/scripts/backup-db.sh

restore: ## Restore a dump: make restore FILE=path/to/dump.sql.gz
	bash infrastructure/scripts/restore-db.sh $(FILE)

clean: ## Remove containers, volumes and build caches
	$(COMPOSE) down -v --remove-orphans
