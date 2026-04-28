"""Volume calibration records for sleep-time cues."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VolumeCalibration:
    device_name: str
    detectable_volume: float
    identifiable_volume: float
    comfortable_volume: float
