import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "tests" / "stress" / "run_benchmark.sh"


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def fake_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "repo"
    stress_dir = root / "tests" / "stress"
    for mode in ("baseline", "scaled"):
        results_dir = stress_dir / "results" / mode
        results_dir.mkdir(parents=True)
        (results_dir / "docker-stats-k6.txt").write_text("OLD\n", encoding="utf-8")

    shutil.copy2(RUNNER, stress_dir / "run_benchmark.sh")

    for name in ("run_k6.sh", "run_vegeta.sh"):
        write_executable(
            stress_dir / name,
            "#!/usr/bin/env bash\nsleep 0.2\nexit 0\n",
        )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_log = tmp_path / "docker.log"
    write_executable(
        bin_dir / "docker",
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$*" >> "{docker_log}"\n'
        'case "$1" in\n'
        "  version) echo 29.7.2 ;;\n"
        "  compose)\n"
        '    case "$2" in\n'
        "      version) echo 5.4.0 ;;\n"
        "      ps) echo fake-app-id ;;\n"
        "      logs) echo fake-log-line ;;\n"
        "    esac ;;\n"
        "  stats) echo 'fake-app-1|10.0%|10MiB / 1GiB' ;;\n"
        "esac\n",
    )
    write_executable(bin_dir / "uv", "#!/usr/bin/env bash\nexit 0\n")

    return root, bin_dir, docker_log


VARIANT_VARIABLES = (
    "EXTRACTION_EXECUTOR",
    "WORKER_POOL_SIZE",
    "MAX_QUEUE_SIZE",
    "WEB_CONCURRENCY",
)


def run_benchmark(
    root: Path,
    bin_dir: Path,
    mode: str,
    variant: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key not in VARIANT_VARIABLES}
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env.update(variant or {})
    return subprocess.run(
        ["bash", str(root / "tests" / "stress" / "run_benchmark.sh"), mode],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_run_benchmark_rejects_unknown_mode():
    result = subprocess.run(
        ["bash", str(RUNNER), "unknown"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Uso:" in result.stderr


@pytest.mark.parametrize(
    ("mode", "replicas"),
    [("baseline", "1"), ("scaled", "5")],
)
def test_run_benchmark_writes_metadata_stats_and_exit_codes(fake_repo, mode, replicas):
    root, bin_dir, docker_log = fake_repo

    result = run_benchmark(root, bin_dir, mode)

    assert result.returncode == 0, result.stderr
    results_dir = root / "tests" / "stress" / "results" / mode
    metadata = (results_dir / "metadata.txt").read_text(encoding="utf-8")
    assert f"mode={mode}" in metadata
    assert f"replicas={replicas}" in metadata
    assert "date=" in metadata
    assert "cpus=" in metadata
    assert "MemTotal:" in metadata
    assert "docker=29.7.2" in metadata
    assert "compose=5.4.0" in metadata

    stats = (results_dir / "docker-stats-k6.txt").read_text(encoding="utf-8")
    assert "OLD" not in stats
    assert "fake-app-1" in stats
    assert (results_dir / "k6-exit-code").read_text(encoding="utf-8") == "0\n"
    assert (results_dir / "vegeta-exit-code").read_text(encoding="utf-8") == "0\n"
    assert f"compose up -d --build --scale app={replicas}" in docker_log.read_text(encoding="utf-8")


def test_run_benchmark_records_scenario_failures_and_continues(fake_repo):
    root, bin_dir, _docker_log = fake_repo
    write_executable(
        root / "tests" / "stress" / "run_k6.sh",
        "#!/usr/bin/env bash\nexit 7\n",
    )

    result = run_benchmark(root, bin_dir, "baseline")

    assert result.returncode == 0, result.stderr
    results_dir = root / "tests" / "stress" / "results" / "baseline"
    assert (results_dir / "k6-exit-code").read_text(encoding="utf-8") == "7\n"
    assert (results_dir / "vegeta-exit-code").read_text(encoding="utf-8") == "0\n"


def test_run_benchmark_records_the_concurrency_variant(fake_repo):
    root, bin_dir, _docker_log = fake_repo

    result = run_benchmark(
        root,
        bin_dir,
        "baseline",
        variant={
            "EXTRACTION_EXECUTOR": "process",
            "WORKER_POOL_SIZE": "2",
            "MAX_QUEUE_SIZE": "30",
            "WEB_CONCURRENCY": "3",
        },
    )

    assert result.returncode == 0, result.stderr
    metadata = (root / "tests/stress/results/baseline/metadata.txt").read_text(encoding="utf-8")
    assert "extraction_executor=process" in metadata
    assert "worker_pool_size=2" in metadata
    assert "max_queue_size=30" in metadata
    assert "web_concurrency=3" in metadata


def test_run_benchmark_records_unset_variant_variables_as_default(fake_repo):
    root, bin_dir, _docker_log = fake_repo

    result = run_benchmark(root, bin_dir, "baseline")

    assert result.returncode == 0, result.stderr
    metadata = (root / "tests/stress/results/baseline/metadata.txt").read_text(encoding="utf-8")
    assert "extraction_executor=default" in metadata
    assert "worker_pool_size=default" in metadata
    assert "max_queue_size=default" in metadata
    assert "web_concurrency=default" in metadata


def test_run_benchmark_saves_container_logs_per_scenario(fake_repo):
    root, bin_dir, _docker_log = fake_repo

    result = run_benchmark(root, bin_dir, "baseline")

    assert result.returncode == 0, result.stderr
    results_dir = root / "tests" / "stress" / "results" / "baseline"
    for scenario in ("k6", "vegeta"):
        logs = (results_dir / f"compose-logs-{scenario}.log").read_text(encoding="utf-8")
        assert "fake-log-line" in logs
