import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_shell_scripts_are_syntactically_valid():
    scripts = sorted((REPO_ROOT / "tests").rglob("*.sh"))

    assert scripts
    for script in scripts:
        result = subprocess.run(
            ["bash", "-n", str(script)],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"{script}: {result.stderr}"


def test_makefile_benchmark_targets_use_runner():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "tests/stress/run_benchmark.sh baseline" in makefile
    assert "tests/stress/run_benchmark.sh scaled" in makefile


def test_makefile_workers_target_runs_every_concurrency_variant():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    for variant in ("threads-4", "threads-1", "processes-4", "processes-1", "uvicorn-4"):
        assert (
            f"$(WORKERS_RESULTS_DIR)/{variant} tests/stress/run_benchmark.sh baseline" in makefile
        )


def test_makefile_queue_target_sweeps_queue_sizes_with_five_replicas():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "QUEUE_SIZES ?= 20 30 40 60 100" in makefile
    assert (
        "MAX_QUEUE_SIZE=$$size RESULTS_DIR=$(QUEUE_RESULTS_DIR)/queue-$$size "
        "tests/stress/run_benchmark.sh scaled"
    ) in makefile


def test_makefile_lb_target_compares_balancing_strategies_with_five_replicas():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "LB_STRATEGIES ?= wrr p2c leasttime" in makefile
    assert (
        "LB_STRATEGY=$$strategy RESULTS_DIR=$(LB_RESULTS_DIR)/$$strategy "
        "tests/stress/run_benchmark.sh scaled"
    ) in makefile


def test_compose_takes_the_balancing_strategy_from_the_environment():
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "traefik.http.services.pdf.loadbalancer.strategy=${LB_STRATEGY:-" in compose
