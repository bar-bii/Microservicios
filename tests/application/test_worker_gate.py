import asyncio

import pytest

from application.config import FIFO_ORDER, HRRN_ORDER
from application.worker_gate import WorkerGate


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


class Job:
    """Toma un worker de la compuerta y lo retiene hasta que se llame a finish()."""

    def __init__(self, gate: WorkerGate, name: str, size: int, started: list[str]) -> None:
        self._done = asyncio.Event()
        self.task = asyncio.create_task(self._run(gate, name, size, started))

    async def _run(self, gate: WorkerGate, name: str, size: int, started: list[str]) -> None:
        async with gate.worker(size):
            started.append(name)
            await self._done.wait()

    async def finish(self) -> None:
        self._done.set()
        await self.task


@pytest.mark.anyio
async def test_gate_runs_as_many_jobs_at_once_as_it_has_workers():
    gate = WorkerGate(workers=2)
    started: list[str] = []

    jobs = [Job(gate, name, 1, started) for name in ("a", "b", "c")]
    await settle()

    assert started == ["a", "b"]
    assert gate.waiting == 1

    await jobs[0].finish()
    await settle()

    assert started == ["a", "b", "c"]
    assert gate.waiting == 0
    await jobs[1].finish()
    await jobs[2].finish()


@pytest.mark.anyio
async def test_fifo_hands_the_worker_to_the_earliest_waiter():
    clock = FakeClock()
    gate = WorkerGate(workers=1, order=FIFO_ORDER, clock=clock)
    started: list[str] = []

    running = Job(gate, "running", 1, started)
    await settle()
    large = Job(gate, "large", 1_000, started)
    await settle()
    clock.now = 10.0
    small = Job(gate, "small", 1, started)
    await settle()
    clock.now = 11.0

    await running.finish()
    await settle()

    assert started == ["running", "large"]
    await large.finish()
    await small.finish()


@pytest.mark.anyio
async def test_hrrn_hands_the_worker_to_the_waiter_with_the_longest_wait_for_its_size():
    clock = FakeClock()
    gate = WorkerGate(workers=1, order=HRRN_ORDER, clock=clock)
    started: list[str] = []

    running = Job(gate, "running", 1, started)
    await settle()
    large = Job(gate, "large", 1_000, started)
    await settle()
    clock.now = 10.0
    small = Job(gate, "small", 1, started)
    await settle()
    clock.now = 11.0

    await running.finish()
    await settle()

    assert started == ["running", "small"]
    await small.finish()
    await large.finish()


@pytest.mark.anyio
async def test_hrrn_lets_a_large_job_through_once_it_has_waited_long_enough():
    clock = FakeClock()
    gate = WorkerGate(workers=1, order=HRRN_ORDER, clock=clock)
    started: list[str] = []

    running = Job(gate, "running", 1, started)
    await settle()
    large = Job(gate, "large", 1_000, started)
    await settle()
    clock.now = 5_000.0
    small = Job(gate, "small", 1, started)
    await settle()
    clock.now = 5_001.0

    await running.finish()
    await settle()

    assert started == ["running", "large"]
    await large.finish()
    await small.finish()


@pytest.mark.anyio
async def test_hrrn_breaks_ties_by_arrival_order():
    clock = FakeClock()
    gate = WorkerGate(workers=1, order=HRRN_ORDER, clock=clock)
    started: list[str] = []

    running = Job(gate, "running", 1, started)
    await settle()
    first = Job(gate, "first", 10, started)
    await settle()
    second = Job(gate, "second", 10, started)
    await settle()

    await running.finish()
    await settle()

    assert started == ["running", "first"]
    await first.finish()
    await second.finish()


@pytest.mark.anyio
async def test_hrrn_treats_an_empty_payload_as_the_smallest_job():
    clock = FakeClock()
    gate = WorkerGate(workers=1, order=HRRN_ORDER, clock=clock)
    started: list[str] = []

    running = Job(gate, "running", 1, started)
    await settle()
    large = Job(gate, "large", 1_000, started)
    await settle()
    clock.now = 10.0
    empty = Job(gate, "empty", 0, started)
    await settle()
    clock.now = 11.0

    await running.finish()
    await settle()

    assert started == ["running", "empty"]
    await empty.finish()
    await large.finish()


@pytest.mark.anyio
async def test_gate_frees_the_worker_when_the_job_raises():
    gate = WorkerGate(workers=1)

    with pytest.raises(RuntimeError):
        async with gate.worker(1):
            raise RuntimeError("extraction failed")

    async with asyncio.timeout(1), gate.worker(1):
        pass


@pytest.mark.anyio
async def test_a_cancelled_waiter_leaves_the_queue_without_taking_a_worker():
    gate = WorkerGate(workers=1)
    started: list[str] = []

    running = Job(gate, "running", 1, started)
    await settle()
    cancelled = Job(gate, "cancelled", 1, started)
    await settle()
    waiting = Job(gate, "waiting", 1, started)
    await settle()

    cancelled.task.cancel()
    await settle()
    assert gate.waiting == 1

    await running.finish()
    await settle()

    assert started == ["running", "waiting"]
    await waiting.finish()


@pytest.mark.anyio
async def test_a_waiter_cancelled_right_after_getting_the_worker_gives_it_back():
    gate = WorkerGate(workers=1)
    started: list[str] = []

    running = Job(gate, "running", 1, started)
    await settle()
    cancelled = Job(gate, "cancelled", 1, started)
    await settle()

    running._done.set()
    await asyncio.sleep(0)
    cancelled.task.cancel()
    await settle()

    assert started == ["running"]
    async with asyncio.timeout(1), gate.worker(1):
        pass
