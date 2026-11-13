SHELL := /bin/bash

BASE_URL ?= http://localhost:8080
REPLICAS ?= 5
RESULTS_DIR ?= tests/stress/results
K6_IMAGE ?= grafana/k6:1.8.3
VEGETA_IMAGE ?= peterevans/vegeta:6.9.1
VEGETA_RATE ?= 50
VEGETA_DURATION ?= 30s
VEGETA_TIMEOUT ?= 30s

export BASE_URL RESULTS_DIR K6_IMAGE VEGETA_IMAGE VEGETA_RATE VEGETA_DURATION VEGETA_TIMEOUT

.PHONY: help stress-corpus stress-up stress-down stress-k6 stress-vegeta stress-run stress-baseline stress-scaled

.NOTPARALLEL: stress-run

help:
	@echo "Objetivos de stress testing:"
	@echo "  stress-corpus   Genera el corpus sintético determinista (tests/stress/pdfs)."
	@echo "  stress-up       Levanta el stack con REPLICAS réplicas (default: 5)."
	@echo "  stress-down     Detiene y elimina el stack."
	@echo "  stress-k6       Ejecuta el escenario k6 (K6_IMAGE, K6_SCRIPT, BASE_URL, RESULTS_DIR)."
	@echo "  stress-vegeta   Ejecuta el escenario Vegeta (VEGETA_IMAGE, VEGETA_RATE, VEGETA_DURATION, VEGETA_TIMEOUT)."
	@echo "  stress-baseline 1 réplica; resultados en tests/stress/results/baseline."
	@echo "  stress-scaled   5 réplicas; resultados en tests/stress/results/scaled."

stress-corpus:
	uv run python tests/stress/generate_corpus.py

stress-up:
	docker compose up -d --build --scale app=$(REPLICAS)

stress-down:
	docker compose down --remove-orphans

stress-k6:
	tests/stress/run_k6.sh

stress-vegeta:
	tests/stress/run_vegeta.sh

stress-run: stress-corpus stress-up stress-k6 stress-vegeta

stress-baseline: REPLICAS := 1
stress-baseline: RESULTS_DIR := tests/stress/results/baseline
stress-baseline: stress-run

stress-scaled: REPLICAS := 5
stress-scaled: RESULTS_DIR := tests/stress/results/scaled
stress-scaled: stress-run
