import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from application.config import FIFO_ORDER


@dataclass(frozen=True, slots=True, eq=False)
class _Waiter:
    size: int
    since: float
    turn: asyncio.Future[None]


class WorkerGate:
    """Reparte un número fijo de workers entre los trabajos que esperan.

    Con `fifo` el worker libre va al que llegó primero. Con `hrrn` (highest
    response ratio next) va al que más esperó en relación con su tamaño: los
    trabajos chicos pasan rápido y los grandes ganan prioridad con la espera.
    """

    def __init__(
        self,
        workers: int,
        order: str = FIFO_ORDER,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._free = workers
        self._order = order
        self._clock = clock
        self._waiters: list[_Waiter] = []

    @property
    def waiting(self) -> int:
        return len(self._waiters)

    @asynccontextmanager
    async def worker(self, size: int) -> AsyncIterator[None]:
        await self._acquire(size)
        try:
            yield
        finally:
            self._release()

    async def _acquire(self, size: int) -> None:
        if self._free > 0:
            self._free -= 1
            return

        waiter = _Waiter(size, self._clock(), asyncio.get_running_loop().create_future())
        self._waiters.append(waiter)
        try:
            await waiter.turn
        except asyncio.CancelledError:
            if waiter in self._waiters:
                self._waiters.remove(waiter)
            else:
                self._release()
            raise

    def _release(self) -> None:
        if not self._waiters:
            self._free += 1
            return

        waiter = self._next_waiter()
        self._waiters.remove(waiter)
        waiter.turn.set_result(None)

    def _next_waiter(self) -> _Waiter:
        if self._order == FIFO_ORDER:
            return self._waiters[0]

        now = self._clock()
        return max(self._waiters, key=lambda waiter: (now - waiter.since) / max(waiter.size, 1))
