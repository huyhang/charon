PYTHON ?= .venv/bin/python
CHARON_PORT ?= 8080
FAKE_DS_PORT ?= 5000
export CHARON_PORT FAKE_DS_PORT
DEV_E2E_ENV = CHARON_E2E_URL=http://127.0.0.1:$(CHARON_PORT) CHARON_E2E_API_KEY=dev-key \
	FAKE_DS_E2E_URL=http://127.0.0.1:$(FAKE_DS_PORT)

.PHONY: install test e2e lint fmt dev dev-e2e smoke openapi docker-build docker-dev docker-e2e \
	coverage py-coverage check \
	ui-install ui-dev ui-seed ui-test ui-coverage ui-lint ui-fmt ui-build ui-serve ui-api ui-e2e

install:  ## Install Charon with dev dependencies into the venv
	$(PYTHON) -m pip install -e '.[dev]'

test:  ## Unit tests
	$(PYTHON) -m pytest

e2e:  ## End-to-end tests; starts Charon + fake Download Station in-process
	$(PYTHON) -m pytest tests/e2e

lint:  ## Lint and check formatting
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

coverage: py-coverage ui-coverage  ## Backend and UI tests with coverage; fails below 90%

py-coverage:  ## Unit + in-process e2e tests with coverage; fails below 90% (HTML: htmlcov/)
	env -u CHARON_E2E_URL $(PYTHON) -m pytest tests --cov --cov-report=term --cov-report=html

check: lint ui-lint coverage  ## Everything a change must pass: lint, types, formatting, coverage

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

openapi:  ## Regenerate docs/openapi.json and the UI's API types after changing the API
	$(PYTHON) -m charon.openapi docs/openapi.json
	@if [ -d ui/node_modules ]; then $(MAKE) ui-api; fi

docker-build:  ## Build the Charon and fake Download Station images
	docker build -f docker/Dockerfile -t charon:latest .
	docker build -f docker/Dockerfile.fake -t charon-fake-ds:latest .

docker-dev:  ## Run the dev stack in Docker
	mkdir -p var/data var/downloads var/library
	docker compose -p charon -f docker/docker-compose.dev.yml up --build

docker-e2e:  ## End-to-end tests against `make docker-dev`
	E2E_LIBRARY_DIR=var/library E2E_LIBRARY_DIR_SERVICE=/library \
		FAKE_DS_E2E_URL_SERVICE=http://fake-ds:5000 \
		$(DEV_E2E_ENV) $(PYTHON) -m pytest tests/e2e

ui-install:  ## Install the UI's dependencies (Node 22.22.2+, 24.15+ or 26+)
	cd ui && npm ci

ui-dev:  ## Fake Download Station + Charon + UI dev server on http://localhost:5173
	scripts/ui-dev.sh

ui-seed:  ## Fill a running `make dev` / `make ui-dev` stack with sample data
	$(PYTHON) -m fake_ds.seed --charon http://127.0.0.1:$(CHARON_PORT) \
		--fake-ds http://127.0.0.1:$(FAKE_DS_PORT) --library var/library

ui-test:  ## UI unit tests
	cd ui && npm test

ui-coverage:  ## UI unit tests with coverage; fails below 90% (HTML: ui/coverage/)
	cd ui && npm run coverage

ui-lint:  ## UI type check and format check
	cd ui && npm run lint

ui-fmt:  ## Format the UI code
	cd ui && npm run fmt

ui-build:  ## Production build of the UI into ui/dist
	cd ui && npm run build

ui-serve: ui-build  ## Charon serves the built UI on :$(CHARON_PORT), against the fake
	CHARON_UI_DIR=$(CURDIR)/ui/dist scripts/dev.sh

ui-api:  ## Regenerate the UI's API types from docs/openapi.json
	cd ui && npm run api

ui-e2e:  ## Browser tests against a running `make ui-dev` (first: npx playwright install chromium)
	cd ui && FAKE_DS_URL=http://127.0.0.1:$(FAKE_DS_PORT) npm run e2e
