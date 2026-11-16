SHELL := /bin/bash

BASE_URL ?= http://localhost:8080
REPLICAS ?= 5
RESULTS_DIR ?= tests/stress/results
K6_IMAGE ?= grafana/k6:1.8.3
K6_STRICT ?= 0
VEGETA_IMAGE ?= peterevans/vegeta:6.9.1
VEGETA_RATE ?= 50
VEGETA_DURATION ?= 30s
VEGETA_TIMEOUT ?= 30s
WORKERS_RESULTS_DIR ?= tests/stress/results/workers

export BASE_URL RESULTS_DIR K6_IMAGE K6_STRICT VEGETA_IMAGE VEGETA_RATE VEGETA_DURATION VEGETA_TIMEOUT

.PHONY: help stress-corpus stress-up stress-down stress-k6 stress-vegeta stress-run stress-baseline stress-scaled stress-workers

.NOTPARALLEL: stress-run

help:
	@echo "Objetivos de stress testing:"
	@echo "  stress-corpus   Genera el corpus sintético determinista (tests/stress/pdfs)."
	@echo "  stress-up       Levanta el stack con REPLICAS réplicas (default: 5)."
	@echo "  stress-down     Detiene y elimina el stack."
	@echo "  stress-k6       Ejecuta el escenario k6 (K6_IMAGE, K6_SCRIPT, K6_STRICT, BASE_URL, RESULTS_DIR)."
	@echo "  stress-vegeta   Ejecuta el escenario Vegeta (VEGETA_IMAGE, VEGETA_RATE, VEGETA_DURATION, VEGETA_TIMEOUT)."
	@echo "  stress-baseline 1 réplica + stats; resultados en tests/stress/results/baseline."
	@echo "  stress-scaled   5 réplicas + stats; resultados en tests/stress/results/scaled."
	@echo "  stress-workers  Compara hilos, procesos y workers de uvicorn con 1 réplica (WORKERS_RESULTS_DIR)."

stress-corpus:
	uv run python tests/stress/generate_corpus.py

stress-up:
	docker compose up -d --build --scale app=$(REPLICAS)

stress-down:
	docker compose down --remove-orphans

stress-k6: stress-corpus
	tests/stress/run_k6.sh

stress-vegeta: stress-corpus
	tests/stress/run_vegeta.sh

stress-run: stress-corpus stress-up stress-k6 stress-vegeta

stress-baseline: RESULTS_DIR := tests/stress/results/baseline
stress-baseline:
	tests/stress/run_benchmark.sh baseline

stress-scaled: RESULTS_DIR := tests/stress/results/scaled
stress-scaled:
	tests/stress/run_benchmark.sh scaled

stress-workers:
	RESULTS_DIR=$(WORKERS_RESULTS_DIR)/threads-4 tests/stress/run_benchmark.sh baseline
	WORKER_POOL_SIZE=1 RESULTS_DIR=$(WORKERS_RESULTS_DIR)/threads-1 tests/stress/run_benchmark.sh baseline
	EXTRACTION_EXECUTOR=process RESULTS_DIR=$(WORKERS_RESULTS_DIR)/processes-4 tests/stress/run_benchmark.sh baseline
	EXTRACTION_EXECUTOR=process WORKER_POOL_SIZE=1 RESULTS_DIR=$(WORKERS_RESULTS_DIR)/processes-1 tests/stress/run_benchmark.sh baseline
	WEB_CONCURRENCY=4 WORKER_POOL_SIZE=1 RESULTS_DIR=$(WORKERS_RESULTS_DIR)/uvicorn-4 tests/stress/run_benchmark.sh baseline
