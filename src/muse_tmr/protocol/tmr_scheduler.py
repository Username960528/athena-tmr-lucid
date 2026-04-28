"""REM-gated cue scheduler contracts."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class CueDecision:
    should_play: bool
    reason_codes: Tuple[str, ...] = ()
