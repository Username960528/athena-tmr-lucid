"""REM-gated cue scheduler contracts."""

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

from muse_tmr.audio import VolumeCalibration, calibrated_max_volume


@dataclass(frozen=True)
class CueDecision:
    should_play: bool
    reason_codes: Tuple[str, ...] = ()
    max_volume: Optional[float] = None
    calibration_device_name: Optional[str] = None


def arousal_guard_decision(reason_codes: Iterable[str]) -> CueDecision:
    """Convert safety guard reason codes into a cue playback decision."""

    unique_reasons = tuple(dict.fromkeys(reason_codes))
    return CueDecision(
        should_play=not unique_reasons,
        reason_codes=unique_reasons,
    )


def calibrated_cue_decision(
    reason_codes: Iterable[str],
    *,
    calibration: Optional[VolumeCalibration],
    fallback_max_volume: float = 0.20,
) -> CueDecision:
    """Convert scheduler guards into a cue decision with calibrated volume cap."""

    unique_reasons = list(dict.fromkeys(reason_codes))
    if calibration is None:
        if "volume_calibration_missing" not in unique_reasons:
            unique_reasons.append("volume_calibration_missing")
        return CueDecision(
            should_play=False,
            reason_codes=tuple(unique_reasons),
            max_volume=fallback_max_volume,
        )

    max_volume = calibrated_max_volume(calibration, hard_cap=fallback_max_volume)
    return CueDecision(
        should_play=not unique_reasons,
        reason_codes=tuple(unique_reasons),
        max_volume=max_volume,
        calibration_device_name=calibration.device_name,
    )
