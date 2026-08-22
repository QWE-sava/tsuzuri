from __future__ import annotations

import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor


class BackgroundWorker:
    def __init__(self, max_workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="tsuzuri-bg")
        self._jobs: dict[str, Future] = {}
        self._lock = threading.Lock()

    def submit(self, name: str, fn, *args, **kwargs) -> Future:
        with self._lock:
            self._jobs.pop(name, None)
        future = self._pool.submit(fn, *args, **kwargs)
        with self._lock:
            self._jobs[name] = future
        future.add_done_callback(lambda done: self._on_done(name, done))
        return future

    def _on_done(self, name: str, future: Future) -> None:
        error = future.exception()
        if error is not None:
            traceback.print_exception(type(error), error, error.__traceback__)
        with self._lock:
            if self._jobs.get(name) is future:
                del self._jobs[name]

    def wait_for(self, name: str, timeout: float | None = None) -> bool:
        with self._lock:
            future = self._jobs.get(name)
        if future is None:
            return True
        try:
            future.result(timeout=timeout)
            return True
        except Exception:
            return False

    def pending(self) -> list[str]:
        with self._lock:
            return list(self._jobs.keys())

    def shutdown(self, wait: bool = False) -> None:
        self._pool.shutdown(wait=wait)
