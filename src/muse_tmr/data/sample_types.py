"""Shared sample types for Muse frames.

These dataclasses are intentionally small in M0. Later milestones extend
conversion, serialization, and unit handling.
"""

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class EEGSample:
    timestamp: float
    channels_uv: Mapping[str, float]
    source: str = "unknown"


@dataclass(frozen=True)
class IMUSample:
    timestamp: float
    accelerometer_g: Optional[Mapping[str, float]] = None
    gyroscope_dps: Optional[Mapping[str, float]] = None
    source: str = "unknown"


@dataclass(frozen=True)
class PPGSample:
    timestamp: float
    channels: Mapping[str, float]
    source: str = "unknown"


@dataclass(frozen=True)
class HeartRateSample:
    timestamp: float
    bpm: float
    source: str = "unknown"


@dataclass(frozen=True)
class BatterySample:
    timestamp: float
    percent: float
    source: str = "unknown"


@dataclass(frozen=True)
class MuseFrame:
    timestamp: float
    eeg: Optional[EEGSample] = None
    imu: Optional[IMUSample] = None
    ppg: Optional[PPGSample] = None
    heart_rate: Optional[HeartRateSample] = None
    battery: Optional[BatterySample] = None
    source: str = "unknown"

    def modalities(self) -> Tuple[str, ...]:
        present = []
        for name in ("eeg", "imu", "ppg", "heart_rate", "battery"):
            if getattr(self, name) is not None:
                present.append(name)
        return tuple(present)
