"""Volume calibration records for sleep-time cues."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Mapping, Tuple

from muse_tmr.audio.audio_player import AudioPlaybackConfig

VOLUME_CALIBRATION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class VolumeCalibration:
    device_name: str
    detectable_volume: float
    identifiable_volume: float
    comfortable_volume: float
    cue_id: str = "test-cue"
    backend_name: str = "unknown"
    calibrated_at_utc: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.calibrated_at_utc:
            object.__setattr__(self, "calibrated_at_utc", _utc_now())
        self.validate()

    @property
    def scheduler_max_volume(self) -> float:
        return self.comfortable_volume

    def validate(self) -> None:
        if not self.device_name.strip():
            raise ValueError("device_name must not be empty")
        if not self.cue_id.strip():
            raise ValueError("cue_id must not be empty")
        volumes = (
            self.detectable_volume,
            self.identifiable_volume,
            self.comfortable_volume,
        )
        if any(not 0.0 <= volume <= 1.0 for volume in volumes):
            raise ValueError("calibration volumes must be between 0.0 and 1.0")
        if not self.detectable_volume <= self.identifiable_volume <= self.comfortable_volume:
            raise ValueError(
                "volumes must be ordered: detectable <= identifiable <= comfortable"
            )

    def to_dict(self) -> Dict[str, object]:
        return {
            "device_name": self.device_name,
            "detectable_volume": self.detectable_volume,
            "identifiable_volume": self.identifiable_volume,
            "comfortable_volume": self.comfortable_volume,
            "scheduler_max_volume": self.scheduler_max_volume,
            "cue_id": self.cue_id,
            "backend_name": self.backend_name,
            "calibrated_at_utc": self.calibrated_at_utc,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "VolumeCalibration":
        return cls(
            device_name=str(payload["device_name"]),
            detectable_volume=float(payload["detectable_volume"]),
            identifiable_volume=float(payload["identifiable_volume"]),
            comfortable_volume=float(payload["comfortable_volume"]),
            cue_id=str(payload.get("cue_id", "test-cue")),
            backend_name=str(payload.get("backend_name", "unknown")),
            calibrated_at_utc=str(payload.get("calibrated_at_utc", "")),
            notes=str(payload.get("notes", "")),
        )


@dataclass(frozen=True)
class VolumeCalibrationStore:
    calibrations: Tuple[VolumeCalibration, ...] = ()
    schema_version: int = VOLUME_CALIBRATION_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "calibrations": [calibration.to_dict() for calibration in self.calibrations],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "VolumeCalibrationStore":
        return cls(
            schema_version=int(payload.get("schema_version", VOLUME_CALIBRATION_SCHEMA_VERSION)),
            calibrations=tuple(
                VolumeCalibration.from_dict(item)
                for item in payload.get("calibrations", ())
            ),
        )

    def save(self, output_path: Path) -> Path:
        output_path = output_path.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return output_path

    @classmethod
    def load(cls, input_path: Path) -> "VolumeCalibrationStore":
        return cls.from_dict(json.loads(input_path.expanduser().read_text(encoding="utf-8")))

    def with_calibration(self, calibration: VolumeCalibration) -> "VolumeCalibrationStore":
        kept = tuple(
            existing
            for existing in self.calibrations
            if existing.device_name != calibration.device_name
        )
        return VolumeCalibrationStore(
            schema_version=self.schema_version,
            calibrations=kept + (calibration,),
        )

    def latest(self) -> VolumeCalibration:
        if not self.calibrations:
            raise KeyError("no volume calibrations available")
        return self.calibrations[-1]

    def latest_for_device(self, device_name: str) -> VolumeCalibration:
        for calibration in reversed(self.calibrations):
            if calibration.device_name == device_name:
                return calibration
        raise KeyError(f"no volume calibration for device: {device_name}")


def load_volume_calibrations(input_path: Path) -> VolumeCalibrationStore:
    return VolumeCalibrationStore.load(input_path)


def save_volume_calibration(
    calibration: VolumeCalibration,
    output_path: Path,
    *,
    append: bool = True,
) -> Path:
    output_path = output_path.expanduser()
    if append and output_path.exists():
        store = VolumeCalibrationStore.load(output_path)
    else:
        store = VolumeCalibrationStore()
    return store.with_calibration(calibration).save(output_path)


def calibrated_max_volume(
    calibration: VolumeCalibration,
    *,
    hard_cap: float = 0.20,
) -> float:
    _validate_volume(hard_cap, "hard_cap")
    return min(calibration.scheduler_max_volume, hard_cap)


def audio_config_with_calibration(
    config: AudioPlaybackConfig,
    calibration: VolumeCalibration,
) -> AudioPlaybackConfig:
    max_volume = calibrated_max_volume(calibration, hard_cap=config.max_volume)
    return replace(
        config,
        max_volume=max_volume,
        default_volume=min(config.default_volume, max_volume),
        device_name=config.device_name or calibration.device_name,
    )


def _validate_volume(volume: float, name: str) -> None:
    if not 0.0 <= volume <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
