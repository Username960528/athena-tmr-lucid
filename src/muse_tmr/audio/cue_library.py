"""Cue library metadata and validation."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class CueMetadata:
    cue_id: str
    path: str
    duration_seconds: float
    tags: Tuple[str, ...] = ()
