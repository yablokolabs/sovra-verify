# Sovra Verify — developer entry points.
#
# `make run` is the documented way to start the application.
# Every recipe runs from the repository root and uses only project-local paths.
#
# Credentials are never read, written or echoed by this file. `make run` calls
# scripts/launch.sh, which injects only the two named application credentials.

SHELL := /bin/bash
.DEFAULT_GOAL := help

REPO_ROOT := $(shell cd "$(dir $(lastword $(MAKEFILE_LIST)))" && pwd)
PYTHON ?= python3
VENV := $(REPO_ROOT)/.venv
VENV_PYTHON := $(VENV)/bin/python
BACKEND := $(REPO_ROOT)/track_2b/backend
FRONTEND := $(REPO_ROOT)/track_2b/frontend
IMAGE ?= sovra-verify:local
PORT ?= 8080

# Use the virtualenv interpreter when it exists, otherwise the system one.
ifeq ($(wildcard $(VENV_PYTHON)),)
RUN_PYTHON := $(PYTHON)
else
RUN_PYTHON := $(VENV_PYTHON)
endif

.PHONY: help install install-frontend run run-local test evaluate smoke \
        verify-providers no-footer report-pdf audit docker-build docker-run e2e clean

## help: show every available target (default)
help:
	@echo "Sovra Verify — available targets"
	@echo ""
	@echo "  make install           create .venv and install backend + test dependencies"
	@echo "  make install-frontend  install frontend dependencies (npm)"
	@echo "  make run               start the app in Docker (documented entry point)"
	@echo "  make run-local         start the app as a host process (no Docker)"
	@echo "  make test              run the backend test suite"
	@echo "  make evaluate          measure the frozen evaluation corpus and write RESULTS.json"
	@echo "  make smoke             real-provider smoke test (calls CSCS)"
	@echo "  make verify-providers  verify /models and one real request per provider"
	@echo "  make no-footer         fail if any footer or attribution marker exists"
	@echo "  make report-pdf        build track_2b/technical_report.pdf and check it"
	@echo "  make audit             fail if a credential or forbidden file would ship"
	@echo "  make e2e               full HTTP end-to-end run, then inspect generated output"
	@echo "  make docker-build      build the container image"
	@echo "  make docker-run        run the container via scripts/launch.sh"
	@echo "  make clean             remove generated build artifacts only"
	@echo ""
	@echo "Default model: Apertus 1.5 70B (swiss-ai/Apertus-v1.5-70B) on CSCS."
	@echo "The 8B model is optional and is never selected automatically."

## install: create the virtualenv and install backend plus test dependencies
install:
	@test -d "$(VENV)" || $(PYTHON) -m venv "$(VENV)"
	@"$(VENV_PYTHON)" -m pip install --quiet --upgrade pip
	@"$(VENV_PYTHON)" -m pip install --quiet -r "$(BACKEND)/requirements-dev.txt"
	@echo "backend dependencies installed into $(VENV)"
	@echo "next: make run   (Docker, uses scripts/launch.sh)"

## install-frontend: install frontend dependencies
install-frontend:
	@if [ ! -d "$(FRONTEND)" ]; then echo "no frontend directory at $(FRONTEND)" >&2; exit 1; fi
	@cd "$(FRONTEND)" && if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
	@echo "frontend dependencies installed"

## run: start the application in Docker
run:
	@"$(REPO_ROOT)/scripts/launch.sh" --docker

## run-local: start the application as a host process
run-local:
	@"$(REPO_ROOT)/scripts/launch.sh" --local --port $(PORT)

## test: run the backend test suite
test:
	@cd "$(REPO_ROOT)" && PYTHONPATH="$(BACKEND)" "$(RUN_PYTHON)" -m pytest track_2b/tests -q

## evaluate: measure the frozen evaluation corpus with real inference
evaluate:
	@cd "$(REPO_ROOT)" && "$(RUN_PYTHON)" scripts/evaluate.py

## smoke: real-provider smoke test
smoke:
	@cd "$(REPO_ROOT)" && SOVRA_PYTHON="$(RUN_PYTHON)" bash scripts/smoke.sh

## verify-providers: verify model discovery and one real request per provider
verify-providers:
	@cd "$(REPO_ROOT)" && "$(RUN_PYTHON)" scripts/verify_providers.py

## no-footer: fail if any footer or attribution marker exists
no-footer:
	@cd "$(REPO_ROOT)" && "$(RUN_PYTHON)" scripts/check_no_footer.py

## report-pdf: build the technical report PDF and verify its page budget and page edges
report-pdf:
	@cd "$(REPO_ROOT)" && "$(RUN_PYTHON)" scripts/build_report_pdf.py

## audit: fail if any credential value, key-shaped string or forbidden file is publishable
audit:
	@cd "$(REPO_ROOT)" && "$(RUN_PYTHON)" scripts/audit_secrets.py

## e2e: full HTTP end-to-end run
e2e:
	@cd "$(REPO_ROOT)" && SOVRA_PYTHON="$(RUN_PYTHON)" bash scripts/run_e2e.sh

## docker-build: build the container image
docker-build:
	@docker build -f "$(REPO_ROOT)/track_2b/Dockerfile" -t "$(IMAGE)" "$(REPO_ROOT)"

## docker-run: run the container through the credential-safe launcher
docker-run:
	@"$(REPO_ROOT)/scripts/launch.sh" --docker --port $(PORT)

## clean: remove generated build artifacts only
clean:
	@echo "removing generated build artifacts (never credentials, never source documents)"
	@rm -rf "$(REPO_ROOT)/track_2b/frontend/node_modules"
	@rm -rf "$(REPO_ROOT)/track_2b/frontend/dist"
	@rm -rf "$(REPO_ROOT)/.sovra_work"
	@rm -rf "$(REPO_ROOT)/.sovra_work_test"
	@find "$(REPO_ROOT)/track_2b" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@find "$(REPO_ROOT)/scripts" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -rf "$(REPO_ROOT)/.pytest_cache"
	@find "$(REPO_ROOT)/track_2b" -maxdepth 1 -name '*.sqlite3' -delete 2>/dev/null || true
	@echo ""
	@echo "kept on purpose:"
	@echo "  track_2b/data/demo/        source documents used by the demo"
	@echo "  track_2b/data/evaluation/  measured results and the frozen corpus"
	@echo "  ~/.hermes/.env             never touched by this project"
