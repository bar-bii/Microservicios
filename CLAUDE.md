# CLAUDE.md

Este archivo da contexto a Claude Code (claude.ai/code) sobre el proyecto.

## Stage 2 — Microservices Split: Load/Stress Testing & Optimization

Context for the project's next phase (assignment brief, not yet implemented): the PDF text/Markdown extraction responsibility is split out into its own independent microservice, benchmarked under load/stress with Grafana k6 and Vegeta against a reference implementation from the professor.

### New microservice contract
- Dedicated service exposing `POST /extract`, receiving the raw PDF binary (`multipart/form-data` or a direct binary body).
- Response: `200 OK`, `application/json`, shaped as `{ "content": "<extracted text>", "page_count": <int> }`.
- Stack is unconstrained — any language/framework/PDF library, independent of the current Python/FastAPI stack.

### Deployment constraints (for fair benchmarking)
- Packaged as a Docker image, deployed via `docker compose`.
- Horizontal scaling up to a max of 5 replicas (e.g. `deploy.replicas: 5`) behind a reverse proxy/load balancer (Traefik/Caddy).
- Explicit per-container resource limits in `docker-compose.yml` (e.g. max 1.0 CPU, 512MB–1GB RAM per replica).
- Load tests run against the official PDF corpus in `tests/stress/pdfs` (variable size/density, up to ~9MB).

### Reference benchmarks to beat
- **Spike test (k6, closed model)**: ramp to 100 VUs over 10s, hold 20s, ramp down 10s. Reference numbers: 1,037 requests in 40s, 25.35 req/s sustained throughput, 0.00% error rate, p50 1.88s, p90/p95 7.83s/8.80s, max latency 13.94s.
- **Fixed-rate load test (Vegeta, open model)**: 50 req/s continuous for 30s (1,500 requests rotating 4 test PDFs), 30s client timeout. Reference numbers: 16.65 req/s effective throughput, 66.53% success (998/1,500), 33.40% client timeouts (501 requests) from CPU queue saturation above ~25 sustainable req/s, p50 14.89s.

### Optimization directions to investigate
- Low-CPU/memory PDF extraction libraries that read the stream directly, without dumping the file to disk or duplicating buffers in memory.
- Backpressure and concurrency limiting: avoid unbounded request queues past their useful lifetime; return `429 Too Many Requests` / `503 Service Unavailable` in a controlled way instead.
- Replica strategy and load balancing across the 5 instances.
- Separate the HTTP runtime process from the text-extraction worker pool.

### Grading criteria
- Base grade: technical approval, runs in Docker (up to 5 replicas), functional `/extract`, working test scripts.
- +1.5 points (2nd midterm) for beating the professor's throughput, success rate, and latencies under the same hardware constraints.
- +1.0 extra point for the best overall balance of throughput, failure rate, and latency percentiles across all submissions.
- Qualitative evaluation: Twelve-Factor App compliance (env-var config, port binding, stateless processes, logs to stdout), code structure/modularity/readability, architecture write-up, before/after optimization metrics comparison, and a documented investigation process (required to be eligible for the extra point).

### Deliverables
- Reproducible repo with `Dockerfile` and `docker-compose.yml`, single-command `docker compose up --build`.
- Test scripts: adapted k6 script for the spike test, Vegeta script for the fixed-load test.
- Markdown/PDF report: architecture justification and identified bottleneck analysis.
