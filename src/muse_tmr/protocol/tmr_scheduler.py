"""REM-gated cue scheduler contracts."""

from dataclasses import dataclass
from typing import Iterable, Tuple


@dataclass(frozen=True)
class CueDecision:
    should_play: bool
    reason_codes: Tuple[str, ...] = ()


def arousal_guard_decision(reason_codes: Iterable[str]) -> CueDecision:
    """Convert safety guard reason codes into a cue playback decision."""

    unique_reasons = tuple(dict.fromkeys(reason_codes))
    return CueDecision(
        should_play=not unique_reasons,
        reason_codes=unique_reasons,
    )
