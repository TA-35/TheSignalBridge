"""Load an expensive resource exactly once, even under concurrency.

Every model and parser in this pipeline is loaded lazily, and every one of
them is reached from a thread pool - `analyse()` runs four analysers at once,
and `run_examples.py` runs several messages at once on top of that. The
obvious idiom

    if _thing is None:
        _thing = load()

has a window between the test and the assignment. Measured: twelve threads
racing that pattern ran the loader twelve times. It is not a correctness bug
(the objects are equivalent and last write wins) but it loads a 30MB NumPy
model and a spaCy pipeline once per racing thread, which on a 1GB t3.micro
is the difference between working and being killed by the OOM reaper.

Double-checked locking fixes it: check without the lock (the common case,
uncontended and cheap), take the lock only when the value looks absent, then
check again inside the lock because another thread may have finished while
this one waited.

`functools.lru_cache` is thread-safe but explicitly does not promise the
function runs only once, so it does not solve this problem.
"""
from __future__ import annotations

import threading
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class Lazy(Generic[T]):
    """A value produced on first use, exactly once, thread-safely."""

    __slots__ = ("_factory", "_lock", "_value", "_loaded")

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._lock = threading.Lock()
        self._value: T | None = None
        # A separate flag rather than `_value is None`, so a factory that
        # legitimately returns None is not reloaded on every call.
        self._loaded = False

    def get(self) -> T:
        if self._loaded:                     # fast path, no lock
            return self._value               # type: ignore[return-value]
        with self._lock:
            if not self._loaded:             # re-check: someone may have won
                self._value = self._factory()
                self._loaded = True
        return self._value                   # type: ignore[return-value]

    def reset(self) -> None:
        """Drop the cached value. For tests and for config changes."""
        with self._lock:
            self._value = None
            self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded


class LazyDict(Generic[T]):
    """Per-key lazy values, each built exactly once.

    One lock for the whole map rather than one per key: these loads happen a
    handful of times over a process lifetime, so contention is irrelevant and
    a single lock is far easier to reason about.

    The factory is supplied per call rather than stored, because some callers
    need the current config to build the value. Storing a mutable factory and
    reassigning it before each get() would reintroduce exactly the race this
    class exists to remove - two threads could swap it between the assignment
    and the read.
    """

    __slots__ = ("_default_factory", "_lock", "_values")

    def __init__(self, factory: Callable[[str], T] | None = None) -> None:
        self._default_factory = factory
        self._lock = threading.Lock()
        self._values: dict[str, T] = {}

    def get(self, key: str, factory: Callable[[str], T] | None = None) -> T:
        try:
            return self._values[key]         # fast path, no lock
        except KeyError:
            pass
        build = factory or self._default_factory
        if build is None:
            raise ValueError(f"no factory supplied for {key!r}")
        with self._lock:
            if key not in self._values:      # re-check: someone may have won
                self._values[key] = build(key)
            return self._values[key]

    def reset(self) -> None:
        with self._lock:
            self._values.clear()

    def __contains__(self, key: str) -> bool:
        return key in self._values
