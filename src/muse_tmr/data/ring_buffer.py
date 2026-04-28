"""Small fixed-size ring buffer utility."""

from collections import deque
from typing import Deque, Generic, Iterable, Iterator, TypeVar

T = TypeVar("T")


class RingBuffer(Generic[T]):
    def __init__(self, maxlen: int) -> None:
        if maxlen <= 0:
            raise ValueError("maxlen must be positive")
        self._items: Deque[T] = deque(maxlen=maxlen)

    def append(self, item: T) -> None:
        self._items.append(item)

    def extend(self, items: Iterable[T]) -> None:
        self._items.extend(items)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[T]:
        return iter(self._items)
