import importlib.util
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from muse_tmr.data.sample_types import HeartRateSample, MuseFrame, PPGSample
from muse_tmr.features.epochs import EpochBuilder, EpochConfig, SleepEpoch
from muse_tmr.features.ppg_features import (
    PPGFeatureConfig,
    export_ppg_feature_rows,
    extract_ppg_feature_rows,
    extract_ppg_features,
)


SAMPLE_RATE_HZ = 64


def synthetic_ppg(
    heart_rate_bpm: float,
    *,
    seconds: float = 30.0,
    sample_rate_hz: int = SAMPLE_RATE_HZ,
    baseline: float = 50000.0,
    amplitude: float = 1000.0,
):
    timestamps = np.arange(0, seconds, 1 / sample_rate_hz)
    heart_hz = heart_rate_bpm / 60.0
    pulse = np.sin(2 * np.pi * heart_hz * timestamps)
    harmonic = 0.25 * np.sin(4 * np.pi * heart_hz * timestamps - np.pi / 4)
    respiratory = 0.05 * np.sin(2 * np.pi * 0.25 * timestamps)
    return (baseline + amplitude * (pulse + harmonic + respiratory)).tolist()


def ppg_hr_epoch(
    *,
    ppg_channels=None,
    hr_values=None,
    epoch_index: int = 0,
) -> SleepEpoch:
    frames = []
    if ppg_channels is not None:
        frames.append(
            MuseFrame(
                timestamp=1000.0,
                ppg=PPGSample(timestamp=1000.0, channels=ppg_channels, source="test"),
                source="test",
            )
        )
    if hr_values is not None:
        for index, bpm in enumerate(hr_values):
            frames.append(
                MuseFrame(
                    timestamp=1000.0 + index,
                    heart_rate=HeartRateSample(
                        timestamp=1000.0 + index,
                        bpm=bpm,
                        source="test",
                    ),
                    source="test",
                )
            )
    return EpochBuilder(EpochConfig(epoch_seconds=30, stride_seconds=30))._build_epoch(
        epoch_index,
        1000.0,
        tuple(frames),
    )


class TestPPGFeatures(unittest.TestCase):
    def test_ppg_signal_estimates_heart_rate_when_hr_series_missing(self):
        epoch = ppg_hr_epoch(
            ppg_channels={
                "LO_NIR": synthetic_ppg(72.0),
                "RO_NIR": synthetic_ppg(72.0, amplitude=500.0),
            }
        )

        row = extract_ppg_features(epoch)

        self.assertAlmostEqual(row.ppg_estimated_hr_bpm, 72.0, delta=4.0)
        self.assertAlmostEqual(row.mean_hr_bpm, row.ppg_estimated_hr_bpm)
        self.assertEqual(row.hr_source, "ppg")
        self.assertEqual(row.hrv_source, "ppg")
        self.assertGreater(row.ppg_peak_count, 20)

    def test_heart_rate_summary_and_trend_use_hr_samples(self):
        hr_values = [60.0 + index for index in range(30)]
        epoch = ppg_hr_epoch(
            ppg_channels={"LO_NIR": synthetic_ppg(70.0)},
            hr_values=hr_values,
        )

        row = extract_ppg_features(epoch)

        self.assertAlmostEqual(row.mean_hr_bpm, sum(hr_values) / len(hr_values))
        self.assertEqual(row.hr_source, "heart_rate")
        self.assertGreater(row.hr_trend_bpm_per_min, 50.0)
        self.assertEqual(row.min_hr_bpm, 60.0)
        self.assertEqual(row.max_hr_bpm, 89.0)

    def test_hrv_proxy_uses_variable_hr_when_ppg_peaks_unavailable(self):
        hr_values = [60.0, 62.0, 58.0, 63.0, 59.0, 61.0] * 5
        epoch = ppg_hr_epoch(hr_values=hr_values)

        row = extract_ppg_features(epoch)

        self.assertEqual(row.hrv_source, "heart_rate")
        self.assertGreater(row.rmssd_ms, 0.0)
        self.assertGreaterEqual(row.pnn50_percent, 0.0)
        self.assertIn("ppg_missing", row.artifact_flags)

    def test_sudden_heart_rate_changes_are_logged(self):
        epoch = ppg_hr_epoch(hr_values=[60.0, 61.0, 80.0, 79.0, 55.0])

        row = extract_ppg_features(epoch, PPGFeatureConfig(sudden_hr_change_bpm=10.0))

        self.assertEqual(row.sudden_hr_change_count, 2)
        self.assertEqual(row.max_sudden_hr_change_bpm, 24.0)
        self.assertEqual(row.sudden_hr_changes[0].before_bpm, 61.0)
        self.assertEqual(row.sudden_hr_changes[0].after_bpm, 80.0)

    def test_missing_ppg_with_hr_does_not_crash(self):
        epoch = ppg_hr_epoch(hr_values=[62.0] * 30)

        row = extract_ppg_features(epoch)

        self.assertEqual(row.ppg_sample_count, 0)
        self.assertEqual(row.hr_source, "heart_rate")
        self.assertAlmostEqual(row.mean_hr_bpm, 62.0)
        self.assertIn("ppg_missing", row.artifact_flags)

    def test_missing_ppg_and_hr_returns_flags_without_crashing(self):
        epoch = SleepEpoch(
            index=0,
            start_time=1000.0,
            end_time=1030.0,
            frames=(),
            modality_counts={},
            sample_counts={},
            coverage={"ppg": 0.0, "heart_rate": 0.0},
            quality_flags=("missing_ppg", "missing_heart_rate"),
        )

        row = extract_ppg_features(epoch)

        self.assertTrue(math.isnan(row.mean_hr_bpm))
        self.assertEqual(row.hr_source, "missing")
        self.assertIn("ppg_missing", row.artifact_flags)
        self.assertIn("heart_rate_missing", row.artifact_flags)

    def test_nonfinite_ppg_and_out_of_range_hr_are_flagged(self):
        ppg_values = synthetic_ppg(72.0)
        ppg_values[10] = math.nan
        epoch = ppg_hr_epoch(
            ppg_channels={"LO_NIR": ppg_values},
            hr_values=[20.0, 60.0, math.nan, 300.0],
        )

        row = extract_ppg_features(epoch)

        self.assertIn("ppg_nonfinite_LO_NIR", row.artifact_flags)
        self.assertIn("heart_rate_nonfinite", row.artifact_flags)
        self.assertIn("heart_rate_out_of_range", row.artifact_flags)

    def test_feature_rows_export_to_csv(self):
        rows = extract_ppg_feature_rows([
            ppg_hr_epoch(
                ppg_channels={"LO_NIR": synthetic_ppg(72.0)},
                hr_values=[72.0] * 30,
            )
        ])

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "ppg_features.csv"
            export_ppg_feature_rows(rows, output_path)
            frame = pd.read_csv(output_path)

        self.assertEqual(len(frame), 1)
        self.assertIn("mean_hr_bpm", frame.columns)
        self.assertIn("rmssd_ms", frame.columns)
        self.assertIn("sudden_hr_changes_json", frame.columns)

    @unittest.skipIf(
        importlib.util.find_spec("pyarrow") is None and importlib.util.find_spec("fastparquet") is None,
        "pandas parquet engine is not installed",
    )
    def test_feature_rows_export_to_parquet_when_engine_available(self):
        rows = extract_ppg_feature_rows([
            ppg_hr_epoch(ppg_channels={"LO_NIR": synthetic_ppg(72.0)})
        ])

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "ppg_features.parquet"
            export_ppg_feature_rows(rows, output_path)
            frame = pd.read_parquet(output_path)

        self.assertEqual(len(frame), 1)
        self.assertIn("ppg_estimated_hr_bpm", frame.columns)


if __name__ == "__main__":
    unittest.main()
