PYTHON ?= .venv/bin/python
CHARON_PORT ?= 8080
FAKE_DS_PORT ?= 5000
export CHARON_PORT FAKE_DS_PORT
DEV_E2E_ENV = CHARON_E2E_URL=http://127.0.0.1:$(CHARON_PORT) CHARON_E2E_API_KEY=dev-key \
	FAKE_DS_E2E_URL=http://127.0.0.1:$(FAKE_DS_PORT)

.PHONY: install test e2e lint fmt dev dev-e2e smoke openapi docker-build docker-dev docker-e2e

install:  ## Install Charon with dev dependencies into the venv
	$(PYTHON) -m pip install -e '.[dev]'

test:  ## Unit tests
	$(PYTHON) -m pytest

e2e:  ## End-to-end tests; starts Charon + fake Download Station in-process
	$(PYTHON) -m pytest tests/e2e

lint:  ## Lint and check formatting
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

fmt:  ## Fix lint issues where safe and format
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

dev:  ## Run Charon + fake Download Station locally (no Docker)
	scripts/dev.sh

dev-e2e:  ## End-to-end tests against a running `make dev`
	E2E_LIBRARY_DIR=$(CURDIR)/var/library $(DEV_E2E_ENV) \
		$(PYTHON) -m pytest tests/e2e

smoke:  ## curl walkthrough against a running stack
	PYTHON=$(PYTHON) CHARON_URL=http://127.0.0.1:$(CHARON_PORT) scripts/smoke.sh

openapi:  ## Regenerate docs/openapi.json after changing the API
	$(PYTHON) -m charon.openapi docs/openapi.json

docker-build:  ## Build the Charon and fake Download Station images
	docker build -t charon:latest .
	docker build -f Dockerfile.fake -t charon-fake-ds:latest .

docker-dev:  ## Run the dev stack in Docker
	mkdir -p var/data var/downloads var/library
	docker compose -f docker-compose.dev.yml up --build

docker-e2e:  ## End-to-end tests against `make docker-dev`
	E2E_LIBRARY_DIR=var/library E2E_LIBRARY_DIR_SERVICE=/library \
		$(DEV_E2E_ENV) $(PYTHON) -m pytest tests/e2e
