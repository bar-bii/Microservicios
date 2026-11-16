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
