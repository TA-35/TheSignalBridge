"""Thread-safety of the lazy loaders.

Every model in this pipeline is loaded on first use, and every one is reached
from a thread pool - analyse() runs four analysers at once, and
run_examples.py runs several messages on top of that. The plain
`if x is None: x = load()` idiom races: measured, twelve threads running it
concurrently executed the loader twelve times. The objects are equivalent so
nothing is *wrong*, but it loads a 30MB NumPy model once per racing thread,
which on a 1GB t3.micro is the difference between serving and being OOM-killed.

These tests force the race with a barrier and a deliberately slow factory.
Without the lock they fail; with it they pass.
"""
from __future__ import annotations

import threading
import time

import pytest

from Src.source.pipeline._lazy import Lazy, LazyDict

THREADS = 12


def _race(target) -> None:
    """Run `target` on THREADS threads, released simultaneously."""
    barrier = threading.Barrier(THREADS)

    def run() -> None:
        barrier.wait()
        target()

    threads = [threading.Thread(target=run) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


# --------------------------------------------------------------------------
# Lazy
# --------------------------------------------------------------------------

def test_the_factory_runs_exactly_once_under_concurrency():
    calls: list[int] = []

    def slow():
        calls.append(1)
        time.sleep(0.02)   # widen the check-then-set window
        return object()

    holder = Lazy(slow)
    _race(holder.get)
    assert len(calls) == 1, f"loader ran {len(calls)} times, expected 1"


def test_every_thread_sees_the_same_object():
    holder = Lazy(lambda: object())
    seen: list[int] = []
    _race(lambda: seen.append(id(holder.get())))
    assert len(set(seen)) == 1, "threads got different instances"


def test_a_factory_returning_none_is_not_reloaded():
    """`_value is None` as the loaded-flag would reload forever here."""
    calls: list[int] = []

    def returns_none():
        calls.append(1)
        return None

    holder = Lazy(returns_none)
    assert holder.get() is None
    assert holder.get() is None
    assert len(calls) == 1


def test_reset_forces_a_reload():
    calls: list[int] = []
    holder = Lazy(lambda: (calls.append(1), object())[1])
    holder.get()
    holder.reset()
    holder.get()
    assert len(calls) == 2
    assert holder.loaded


def test_a_raising_factory_propagates_and_does_not_cache():
    holder = Lazy(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    for _ in range(2):
        with pytest.raises(RuntimeError):
            holder.get()
    assert not holder.loaded


# --------------------------------------------------------------------------
# LazyDict
# --------------------------------------------------------------------------

def test_each_key_is_built_exactly_once_under_concurrency():
    calls: dict[str, int] = {}
    lock = threading.Lock()

    def slow(key: str):
        with lock:
            calls[key] = calls.get(key, 0) + 1
        time.sleep(0.02)
        return object()

    holder: LazyDict = LazyDict(slow)
    _race(lambda: [holder.get(k) for k in ("a", "b")])
    assert calls == {"a": 1, "b": 1}, f"built more than once: {calls}"


def test_distinct_keys_get_distinct_values():
    holder: LazyDict = LazyDict(lambda key: f"value-{key}")
    assert holder.get("x") == "value-x"
    assert holder.get("y") == "value-y"


def test_a_per_call_factory_is_used_when_there_is_no_default():
    holder: LazyDict = LazyDict()
    assert holder.get("k", lambda key: f"built-{key}") == "built-k"
    # Cached, so the second factory is never consulted.
    assert holder.get("k", lambda key: "different") == "built-k"


def test_no_factory_at_all_is_an_error_not_a_silent_none():
    holder: LazyDict = LazyDict()
    with pytest.raises(ValueError, match="no factory"):
        holder.get("k")


# --------------------------------------------------------------------------
# The real loaders, as wired into the pipeline
# --------------------------------------------------------------------------

def test_concurrent_analyse_loads_the_extractor_once():
    """The end-to-end case: many threads analysing at the same moment."""
    from Src.source.pipeline import analysis

    analysis._extraction.reset()
    errors: list[str] = []

    def work():
        try:
            analysis.analyse("Could you send the report by Friday?")
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    _race(work)
    assert not errors, errors[0]
    assert analysis._extraction.loaded
