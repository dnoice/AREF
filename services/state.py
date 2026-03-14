"""
✒ Metadata
    - Title: In-Memory State Abstractions (AREF Edition - v2.0)
    - File Name: state.py
    - Relative Path: services/state.py
    - Artifact Type: library
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!

✒ Description:
    Generic bounded in-memory storage primitives used by all AREF
    microservices. Replaces raw module-level dicts and lists with
    size-bounded, typed containers that prevent unbounded memory growth.

✒ Key Features:
    - Feature 1: InMemoryStore — dict-like key-value store implementing
                  MutableMapping with configurable max entries and automatic
                  eviction of oldest entries when full
    - Feature 2: BoundedLog — list subclass for audit trails and event logs
                  with automatic oldest-entry eviction when capacity exceeded

✒ Usage Instructions:
    from services.state import InMemoryStore, BoundedLog

    orders = InMemoryStore[dict](max_entries=10000)
    audit = BoundedLog[dict](max_entries=5000)
---------
"""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from typing import Generic, TypeVar

T = TypeVar("T")


class InMemoryStore(MutableMapping[str, T], Generic[T]):
    """Bounded dict-like store that evicts oldest entries when full.

    Drop-in replacement for ``dict[str, T]`` — supports ``[]``, ``in``,
    ``len()``, ``del``, ``.values()``, ``.items()``, and iteration.
    """

    def __init__(self, max_entries: int = 10_000, initial: dict[str, T] | None = None) -> None:
        self._data: dict[str, T] = dict(initial) if initial else {}
        self._max_entries = max_entries

    def __getitem__(self, key: str) -> T:
        return self._data[key]

    def __setitem__(self, key: str, value: T) -> None:
        self._data[key] = value
        while len(self._data) > self._max_entries:
            oldest = next(iter(self._data))
            del self._data[oldest]

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data


class BoundedLog(list[T]):
    """List with automatic oldest-entry eviction when capacity is exceeded."""

    def __init__(self, max_entries: int = 5000) -> None:
        super().__init__()
        self._max_entries = max_entries

    def append(self, item: T) -> None:  # type: ignore[override]
        super().append(item)
        while len(self) > self._max_entries:
            self.pop(0)
