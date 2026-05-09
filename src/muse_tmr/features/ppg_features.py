"""PPG, HR, and HRV feature extraction for SleepEpoch windows."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.signal import butter, detrend, filtfilt, find_peaks

from muse_tmr.features.epochs import SleepEpoch


@dataclass(frozen=True)
class PPGFeatureConfig:
    ppg_sample_rate_hz: float = 64.0
    min_ppg_coverage: float = 0.5
    min_heart_rate_coverage: float = 0.5
    min_ppg_seconds_for_peak_hr: float = 5.0
    ppg_low_hz: float = 0.5
    ppg_high_hz: float = 4.0
    peak_prominence: float = 0.3
    sudden_hr_change_bpm: float = 10.0
    min_valid_hr_bpm: float = 30.0
    max_valid_hr_bpm: float = 240.0
    flat_ppg_std_threshold: float = 1e-9

    def validate(self) -> None:
        if self.ppg_sample_rate_hz <= 0:
            raise ValueError("ppg_sample_rate_hz must be positive")
        if not 0 <= self.min_ppg_coverage <= 1:
            raise ValueError("min_ppg_coverage must be between 0 and 1")
        if not 0 <= self.min_heart_rate_coverage <= 1:
            raise ValueError("min_heart_rate_coverage must be between 0 and 1")
        if self.min_ppg_seconds_for_peak_hr <= 0:
            raise ValueError("min_ppg_seconds_for_peak_hr must be positive")
        if self.ppg_low_hz <= 0 or self.ppg_high_hz <= self.ppg_low_hz:
            raise ValueError("invalid PPG bandpass range")
        if self.ppg_high_hz >= self.ppg_sample_rate_hz / 2:
            raise ValueError("ppg_high_hz must be below Nyquist")
        if self.peak_prominence <= 0:
            raise ValueError("peak_prominence must be positive")
        if self.sudden_hr_change_bpm <= 0:
            raise ValueError("sudden_hr_change_bpm must be positive")
        if self.min_valid_hr_bpm <= 0 or self.max_valid_hr_bpm <= self.min_valid_hr_bpm:
            raise ValueError("invalid heart-rate bounds")
        if self.flat_ppg_std_threshold < 0:
            raise ValueError("flat_ppg_std_threshold must be non-negative")


@dataclass(frozen=True)
class SuddenHeartRateChange:
    start_time: float
    end_time: float
    before_bpm: float
    after_bpm: float
    delta_bpm: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "before_bpm": self.before_bpm,
            "after_bpm": self.after_bpm,
            "delta_bpm": self.delta_bpm,
        }


@dataclass(frozen=True)
class PPGFeatureRow:
    epoch_index: int
    start_time: float
    end_time: float
    ppg_coverage: float
    heart_rate_coverage: float
    ppg_sample_count: int
    heart_rate_sample_count: int
    ppg_channel_count: int
    ppg_channel_sample_counts: Mapping[str, int]
    primary_ppg_channel: str
    ppg_estimated_hr_bpm: float
    ppg_confidence: float
    ppg_peak_count: int
    ppg_signal_quality: str
    mean_hr_bpm: float
    median_hr_bpm: float
    min_hr_bpm: float
    max_hr_bpm: float
    hr_trend_bpm_per_min: float
    hr_source: str
    mean_rr_ms: float
    sdnn_ms: float
    rmssd_ms: float
    pnn50_percent: float
    hrv_source: str
    sudden_hr_change_count: int
    max_sudden_hr_change_bpm: float
    sudden_hr_changes: Tuple[SuddenHeartRateChange, ...]
    artifact_flags: Tuple[str, ...]
    quality_flags: Tuple[str, ...]

    @property
    def is_noisy(self) -> bool:
        return bool(self.artifact_flags)

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "epoch_index": self.epoch_index,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "ppg_coverage": self.ppg_coverage,
            "heart_rate_coverage": self.heart_rate_coverage,
            "ppg_sample_count": self.ppg_sample_count,
            "heart_rate_sample_count": self.heart_rate_sample_count,
            "ppg_channel_count": self.ppg_channel_count,
            "primary_ppg_channel": self.primary_ppg_channel,
            "ppg_estimated_hr_bpm": self.ppg_estimated_hr_bpm,
            "ppg_confidence": self.ppg_confidence,
            "ppg_peak_count": self.ppg_peak_count,
            "ppg_signal_quality": self.ppg_signal_quality,
            "mean_hr_bpm": self.mean_hr_bpm,
            "median_hr_bpm": self.median_hr_bpm,
            "min_hr_bpm": self.min_hr_bpm,
            "max_hr_bpm": self.max_hr_bpm,
            "hr_trend_bpm_per_min": self.hr_trend_bpm_per_min,
            "hr_source": self.hr_source,
            "mean_rr_ms": self.mean_rr_ms,
            "sdnn_ms": self.sdnn_ms,
            "rmssd_ms": self.rmssd_ms,
            "pnn50_percent": self.pnn50_percent,
            "hrv_source": self.hrv_source,
            "sudden_hr_change_count": self.sudden_hr_change_count,
            "max_sudden_hr_change_bpm": self.max_sudden_hr_change_bpm,
            "is_noisy": self.is_noisy,
            "artifact_flags": ";".join(self.artifact_flags),
            "quality_flags": ";".join(self.quality_flags),
            "sudden_hr_changes_json": json.dumps(
                [change.to_dict() for change in self.sudden_hr_changes],
                sort_keys=True,
            ),
        }
        for channel, count in sorted(self.ppg_channel_sample_counts.items()):
            payload[f"ppg_channel_samples_{channel}"] = count
        return payload


@dataclass(frozen=True)
class _PPGPeakResult:
    channel: str
    estimated_hr_bpm: float
    confidence: float
    peak_times: Tuple[float, ...]
    signal_quality: str


def extract_ppg_features(
    epoch: SleepEpoch,
    config: Optional[PPGFeatureConfig] = None,
) -> PPGFeatureRow:
    config = config or PPGFeatureConfig()
    config.validate()

    ppg_channels = _collect_ppg_channels(epoch)
    hr_times, hr_values = _collect_heart_rate_series(epoch)
    ppg_peak_result = _estimate_ppg_heart_rate(ppg_channels, config)
    ppg_coverage = float(epoch.coverage.get("ppg", 0.0))
    heart_rate_coverage = float(epoch.coverage.get("heart_rate", 0.0))
    quality_flags = tuple(
        flag for flag in epoch.quality_flags
        if "ppg" in flag or "heart_rate" in flag
    )
    artifact_flags = _artifact_flags(
        ppg_channels=ppg_channels,
        hr_values=hr_values,
        ppg_coverage=ppg_coverage,
        heart_rate_coverage=heart_rate_coverage,
        quality_flags=quality_flags,
        config=config,
    )
    hr_summary = _heart_rate_summary(hr_times, hr_values, ppg_peak_result)
    hrv = _hrv_metrics(ppg_peak_result.peak_times, hr_values)
    sudden_changes = _sudden_hr_changes(hr_times, hr_values, config)

    return PPGFeatureRow(
        epoch_index=epoch.index,
        start_time=epoch.start_time,
        end_time=epoch.end_time,
        ppg_coverage=ppg_coverage,
        heart_rate_coverage=heart_rate_coverage,
        ppg_sample_count=max((values.size for values in ppg_channels.values()), default=0),
        heart_rate_sample_count=int(hr_values.size),
        ppg_channel_count=len(ppg_channels),
        ppg_channel_sample_counts={
            channel: int(values.size) for channel, values in ppg_channels.items()
        },
        primary_ppg_channel=ppg_peak_result.channel,
        ppg_estimated_hr_bpm=ppg_peak_result.estimated_hr_bpm,
        ppg_confidence=ppg_peak_result.confidence,
        ppg_peak_count=len(ppg_peak_result.peak_times),
        ppg_signal_quality=ppg_peak_result.signal_quality,
        mean_hr_bpm=hr_summary["mean_hr_bpm"],
        median_hr_bpm=hr_summary["median_hr_bpm"],
        min_hr_bpm=hr_summary["min_hr_bpm"],
        max_hr_bpm=hr_summary["max_hr_bpm"],
        hr_trend_bpm_per_min=hr_summary["hr_trend_bpm_per_min"],
        hr_source=hr_summary["hr_source"],
        mean_rr_ms=hrv["mean_rr_ms"],
        sdnn_ms=hrv["sdnn_ms"],
        rmssd_ms=hrv["rmssd_ms"],
        pnn50_percent=hrv["pnn50_percent"],
        hrv_source=hrv["hrv_source"],
        sudden_hr_change_count=len(sudden_changes),
        max_sudden_hr_change_bpm=_safe_max(
            abs(change.delta_bpm) for change in sudden_changes
        ),
        sudden_hr_changes=sudden_changes,
        artifact_flags=artifact_flags,
        quality_flags=quality_flags,
    )


def extract_ppg_feature_rows(
    epochs: Iterable[SleepEpoch],
    config: Optional[PPGFeatureConfig] = None,
) -> Tuple[PPGFeatureRow, ...]:
    return tuple(extract_ppg_features(epoch, config=config) for epoch in epochs)


def export_ppg_feature_rows(rows: Sequence[PPGFeatureRow], output_path: Path) -> Path:
    output_path = output_path.expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([row.to_dict() for row in rows])

    suffix = output_path.suffix.lower()
    if suffix == ".csv":
        frame.to_csv(output_path, index=False)
    elif suffix in {".parquet", ".pq"}:
        frame.to_parquet(output_path, index=False)
    else:
        raise ValueError("PPG feature export path must end with .csv, .parquet, or .pq")
    return output_path


def _collect_ppg_channels(epoch: SleepEpoch) -> Mapping[str, np.ndarray]:
    channel_values: Dict[str, list] = {}
    for frame in epoch.frames:
        if frame.ppg is None:
            continue
        for channel, values in frame.ppg.channels.items():
            channel_values.setdefault(channel, []).extend(values)
    return {
        channel: np.asarray(values, dtype=float)
        for channel, values in channel_values.items()
    }


def _collect_heart_rate_series(epoch: SleepEpoch) -> Tuple[np.ndarray, np.ndarray]:
    times = []
    bpms = []
    for frame in epoch.frames:
        if frame.heart_rate is None:
            continue
        times.append(float(frame.heart_rate.timestamp))
        bpms.append(float(frame.heart_rate.bpm))
    return np.asarray(times, dtype=float), np.asarray(bpms, dtype=float)


def _estimate_ppg_heart_rate(
    channels: Mapping[str, np.ndarray],
    config: PPGFeatureConfig,
) -> _PPGPeakResult:
    if not channels:
        return _PPGPeakResult("", math.nan, 0.0, (), "Missing")

    channel, values = _primary_ppg_channel(channels)
    finite_values = values[np.isfinite(values)]
    min_samples = int(config.ppg_sample_rate_hz * config.min_ppg_seconds_for_peak_hr)
    if finite_values.size < min_samples:
        return _PPGPeakResult(channel, math.nan, 0.0, (), "Insufficient data")
    if float(np.std(finite_values)) <= config.flat_ppg_std_threshold:
        return _PPGPeakResult(channel, math.nan, 0.0, (), "Flatline")

    filtered = _filter_ppg(finite_values, config)
    std = float(np.std(filtered))
    if not math.isfinite(std) or std <= 0:
        return _PPGPeakResult(channel, math.nan, 0.0, (), "Poor")

    normalized = (filtered - np.mean(filtered)) / std
    peaks, _ = find_peaks(
        normalized,
        distance=max(1, int(0.4 * config.ppg_sample_rate_hz)),
        prominence=config.peak_prominence,
        height=0,
    )
    if peaks.size < 3:
        return _PPGPeakResult(channel, math.nan, 0.0, (), "Too few peaks detected")

    peak_times = peaks / config.ppg_sample_rate_hz
    ibi_seconds = np.diff(peak_times)
    valid_ibi = ibi_seconds[(ibi_seconds > 0.25) & (ibi_seconds < 2.0)]
    if valid_ibi.size < 2:
        return _PPGPeakResult(channel, math.nan, 0.0, tuple(peak_times), "Irregular rhythm")

    mean_ibi = float(np.mean(valid_ibi))
    estimated_hr_bpm = 60.0 / mean_ibi
    confidence = _clamp01(1.0 - _safe_divide(float(np.std(valid_ibi)), mean_ibi))
    return _PPGPeakResult(
        channel=channel,
        estimated_hr_bpm=float(estimated_hr_bpm),
        confidence=confidence,
        peak_times=tuple(float(value) for value in peak_times),
        signal_quality=_signal_quality(confidence),
    )


def _primary_ppg_channel(channels: Mapping[str, np.ndarray]) -> Tuple[str, np.ndarray]:
    best_channel = ""
    best_values = np.asarray((), dtype=float)
    best_std = -1.0
    for channel, values in sorted(channels.items()):
        finite = values[np.isfinite(values)]
        channel_std = float(np.std(finite)) if finite.size else -1.0
        if channel_std > best_std:
            best_channel = channel
            best_values = values
            best_std = channel_std
    return best_channel, best_values


def _filter_ppg(values: np.ndarray, config: PPGFeatureConfig) -> np.ndarray:
    signal = detrend(values)
    nyquist = config.ppg_sample_rate_hz / 2.0
    low = config.ppg_low_hz / nyquist
    high = config.ppg_high_hz / nyquist
    b, a = butter(4, [low, high], btype="band")
    min_length_for_filter = 3 * max(len(a), len(b))
    if signal.size <= min_length_for_filter:
        return signal
    return filtfilt(b, a, signal)


def _heart_rate_summary(
    hr_times: np.ndarray,
    hr_values: np.ndarray,
    ppg_peak_result: _PPGPeakResult,
) -> Mapping[str, object]:
    finite_mask = np.isfinite(hr_times) & np.isfinite(hr_values) & (hr_values > 0)
    finite_times = hr_times[finite_mask]
    finite_values = hr_values[finite_mask]
    if finite_values.size:
        return {
            "mean_hr_bpm": float(np.mean(finite_values)),
            "median_hr_bpm": float(np.median(finite_values)),
            "min_hr_bpm": float(np.min(finite_values)),
            "max_hr_bpm": float(np.max(finite_values)),
            "hr_trend_bpm_per_min": _heart_rate_trend(finite_times, finite_values),
            "hr_source": "heart_rate",
        }
    if math.isfinite(ppg_peak_result.estimated_hr_bpm):
        hr = ppg_peak_result.estimated_hr_bpm
        return {
            "mean_hr_bpm": hr,
            "median_hr_bpm": hr,
            "min_hr_bpm": hr,
            "max_hr_bpm": hr,
            "hr_trend_bpm_per_min": math.nan,
            "hr_source": "ppg",
        }
    return {
        "mean_hr_bpm": math.nan,
        "median_hr_bpm": math.nan,
        "min_hr_bpm": math.nan,
        "max_hr_bpm": math.nan,
        "hr_trend_bpm_per_min": math.nan,
        "hr_source": "missing",
    }


def _heart_rate_trend(times: np.ndarray, values: np.ndarray) -> float:
    if values.size < 2:
        return math.nan
    relative_times = times - float(np.min(times))
    if float(np.max(relative_times)) <= 0:
        return math.nan
    slope_bpm_per_second = float(np.polyfit(relative_times, values, 1)[0])
    return slope_bpm_per_second * 60.0


def _hrv_metrics(
    ppg_peak_times: Tuple[float, ...],
    hr_values: np.ndarray,
) -> Mapping[str, object]:
    if len(ppg_peak_times) >= 3:
        rr_ms = np.diff(np.asarray(ppg_peak_times, dtype=float)) * 1000.0
        return {**_rr_metrics(rr_ms), "hrv_source": "ppg"}

    finite_hr = hr_values[np.isfinite(hr_values) & (hr_values > 0)]
    if finite_hr.size >= 3:
        rr_ms = 60000.0 / finite_hr
        return {**_rr_metrics(rr_ms), "hrv_source": "heart_rate"}

    return {
        "mean_rr_ms": math.nan,
        "sdnn_ms": math.nan,
        "rmssd_ms": math.nan,
        "pnn50_percent": math.nan,
        "hrv_source": "missing",
    }


def _rr_metrics(rr_ms: np.ndarray) -> Mapping[str, float]:
    finite_rr = rr_ms[np.isfinite(rr_ms) & (rr_ms > 0)]
    if finite_rr.size < 2:
        return {
            "mean_rr_ms": math.nan,
            "sdnn_ms": math.nan,
            "rmssd_ms": math.nan,
            "pnn50_percent": math.nan,
        }
    rr_diffs = np.diff(finite_rr)
    return {
        "mean_rr_ms": float(np.mean(finite_rr)),
        "sdnn_ms": float(np.std(finite_rr)),
        "rmssd_ms": _safe_rms(rr_diffs),
        "pnn50_percent": (
            float(np.sum(np.abs(rr_diffs) > 50.0) / rr_diffs.size * 100.0)
            if rr_diffs.size
            else math.nan
        ),
    }


def _sudden_hr_changes(
    hr_times: np.ndarray,
    hr_values: np.ndarray,
    config: PPGFeatureConfig,
) -> Tuple[SuddenHeartRateChange, ...]:
    finite_mask = np.isfinite(hr_times) & np.isfinite(hr_values)
    times = hr_times[finite_mask]
    values = hr_values[finite_mask]
    if values.size < 2:
        return ()

    changes = []
    for index in range(1, values.size):
        delta = float(values[index] - values[index - 1])
        if abs(delta) >= config.sudden_hr_change_bpm:
            changes.append(
                SuddenHeartRateChange(
                    start_time=float(times[index - 1]),
                    end_time=float(times[index]),
                    before_bpm=float(values[index - 1]),
                    after_bpm=float(values[index]),
                    delta_bpm=delta,
                )
            )
    return tuple(changes)


def _artifact_flags(
    ppg_channels: Mapping[str, np.ndarray],
    hr_values: np.ndarray,
    ppg_coverage: float,
    heart_rate_coverage: float,
    quality_flags: Tuple[str, ...],
    config: PPGFeatureConfig,
) -> Tuple[str, ...]:
    flags = set(quality_flags)
    if not ppg_channels:
        flags.add("ppg_missing")
    elif ppg_coverage < config.min_ppg_coverage:
        flags.add("low_ppg_coverage")

    for channel, values in ppg_channels.items():
        if values.size == 0:
            flags.add(f"ppg_empty_{channel}")
            continue
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            flags.add(f"ppg_nonfinite_{channel}")
            continue
        if finite.size != values.size:
            flags.add(f"ppg_nonfinite_{channel}")
        if float(np.std(finite)) <= config.flat_ppg_std_threshold:
            flags.add(f"ppg_flatline_{channel}")

    finite_hr = hr_values[np.isfinite(hr_values)]
    if hr_values.size == 0:
        flags.add("heart_rate_missing")
    elif finite_hr.size == 0:
        flags.add("heart_rate_nonfinite")
    elif finite_hr.size != hr_values.size:
        flags.add("heart_rate_nonfinite")

    if heart_rate_coverage < config.min_heart_rate_coverage:
        flags.add("low_heart_rate_coverage")
    if finite_hr.size and (
        np.any(finite_hr < config.min_valid_hr_bpm)
        or np.any(finite_hr > config.max_valid_hr_bpm)
    ):
        flags.add("heart_rate_out_of_range")
    return tuple(sorted(flags))


def _signal_quality(confidence: float) -> str:
    if confidence > 0.8:
        return "Excellent"
    if confidence > 0.6:
        return "Good"
    if confidence > 0.4:
        return "Fair"
    return "Poor"


def _safe_rms(values: Iterable[float]) -> float:
    values_array = np.asarray(tuple(values), dtype=float)
    finite = values_array[np.isfinite(values_array)]
    if finite.size == 0:
        return math.nan
    return float(math.sqrt(np.mean(finite * finite)))


def _safe_max(values: Iterable[float]) -> float:
    values_array = np.asarray(tuple(values), dtype=float)
    finite = values_array[np.isfinite(values_array)]
    if finite.size == 0:
        return math.nan
    return float(np.max(finite))


def _safe_divide(numerator: float, denominator: float) -> float:
    if not math.isfinite(numerator) or not math.isfinite(denominator) or denominator <= 0:
        return math.nan
    return float(numerator / denominator)


def _clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return float(max(0.0, min(1.0, value)))
