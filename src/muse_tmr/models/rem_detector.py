"""REM detector contracts."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class RemPrediction:
    probability: float
    reason_codes: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be between 0.0 and 1.0")
