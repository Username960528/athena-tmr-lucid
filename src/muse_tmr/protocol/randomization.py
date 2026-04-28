"""Cued-vs-uncued assignment helpers."""

import random
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class CueAssignment:
    cued: Tuple[T, ...]
    uncued: Tuple[T, ...]
    seed: int


def split_cued_uncued(
    items: Sequence[T],
    seed: int,
    cued_count: Optional[int] = None,
) -> CueAssignment:
    if cued_count is None:
        cued_count = len(items) // 2
    if cued_count < 0 or cued_count > len(items):
        raise ValueError("cued_count must fit inside items")

    shuffled = list(items)
    random.Random(seed).shuffle(shuffled)
    return CueAssignment(
        cued=tuple(shuffled[:cued_count]),
        uncued=tuple(shuffled[cued_count:]),
        seed=seed,
    )
