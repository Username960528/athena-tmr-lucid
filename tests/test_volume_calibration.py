import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from muse_tmr.audio import (
    AudioPlaybackConfig,
    VolumeCalibration,
    VolumeCalibrationStore,
    audio_config_with_calibration,
    calibrated_max_volume,
    load_volume_calibrations,
    save_volume_calibration,
)
from muse_tmr.cli.main import build_parser, main


class TestVolumeCalibration(unittest.TestCase):
    def test_calibration_requires_ordered_safe_volumes(self):
        calibration = VolumeCalibration(
            device_name="Bedroom Headphones",
            detectable_volume=0.02,
            identifiable_volume=0.04,
            comfortable_volume=0.08,
        )

        self.assertEqual(calibration.scheduler_max_volume, 0.08)

        with self.assertRaises(ValueError):
            VolumeCalibration(
                device_name="Bedroom Headphones",
                detectable_volume=0.05,
                identifiable_volume=0.04,
                comfortable_volume=0.08,
            )

    def test_store_round_trips_and_replaces_latest_device_calibration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "volume.json"
            save_volume_calibration(
                VolumeCalibration("Bedroom", 0.01, 0.03, 0.06, calibrated_at_utc="t1"),
                path,
            )
            save_volume_calibration(
                VolumeCalibration("Travel", 0.02, 0.04, 0.07, calibrated_at_utc="t2"),
                path,
            )
            save_volume_calibration(
                VolumeCalibration("Bedroom", 0.02, 0.05, 0.09, calibrated_at_utc="t3"),
                path,
            )

            store = load_volume_calibrations(path)

        self.assertEqual(len(store.calibrations), 2)
        self.assertEqual(store.latest().device_name, "Bedroom")
        self.assertEqual(store.latest_for_device("Bedroom").comfortable_volume, 0.09)
        self.assertEqual(store.latest_for_device("Travel").comfortable_volume, 0.07)

    def test_calibration_caps_audio_config_and_scheduler_max(self):
        calibration = VolumeCalibration(
            device_name="Bedroom Headphones",
            detectable_volume=0.02,
            identifiable_volume=0.04,
            comfortable_volume=0.08,
        )

        config = audio_config_with_calibration(
            AudioPlaybackConfig(max_volume=0.20, default_volume=0.12),
            calibration,
        )

        self.assertEqual(calibrated_max_volume(calibration, hard_cap=0.20), 0.08)
        self.assertEqual(config.max_volume, 0.08)
        self.assertEqual(config.default_volume, 0.08)
        self.assertEqual(config.device_name, "Bedroom Headphones")

    def test_store_to_dict_uses_metadata_schema(self):
        store = VolumeCalibrationStore(
            calibrations=(
                VolumeCalibration(
                    "Bedroom",
                    0.02,
                    0.04,
                    0.08,
                    cue_id="pink-noise-test",
                    backend_name="dry-run",
                    calibrated_at_utc="2026-05-12T00:00:00+00:00",
                    notes="pre-sleep",
                ),
            )
        )

        payload = store.to_dict()

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["calibrations"][0]["device_name"], "Bedroom")
        self.assertEqual(payload["calibrations"][0]["scheduler_max_volume"], 0.08)
        self.assertEqual(payload["calibrations"][0]["notes"], "pre-sleep")


class TestVolumeCalibrationCli(unittest.TestCase):
    def test_calibrate_volume_command_parses_metadata_options(self):
        args = build_parser().parse_args([
            "calibrate-volume",
            "--device-name",
            "Bedroom Headphones",
            "--output",
            "data/calibration/volume.json",
            "--detectable-volume",
            "0.02",
            "--identifiable-volume",
            "0.04",
            "--comfortable-volume",
            "0.08",
            "--cue-id",
            "pink-noise-test",
            "--backend",
            "dry-run",
        ])

        self.assertEqual(args.command, "calibrate-volume")
        self.assertEqual(args.output, Path("data/calibration/volume.json"))
        self.assertEqual(args.device_name, "Bedroom Headphones")
        self.assertEqual(args.comfortable_volume, 0.08)
        self.assertEqual(args.cue_id, "pink-noise-test")

    def test_calibrate_volume_cli_writes_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "volume.json"
            with redirect_stdout(io.StringIO()) as output:
                exit_code = main([
                    "calibrate-volume",
                    "--device-name",
                    "Bedroom Headphones",
                    "--output",
                    str(output_path),
                    "--detectable-volume",
                    "0.02",
                    "--identifiable-volume",
                    "0.04",
                    "--comfortable-volume",
                    "0.08",
                    "--notes",
                    "pre-sleep",
                ])
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertIn("volume calibration saved", output.getvalue())
        self.assertEqual(payload["calibrations"][0]["device_name"], "Bedroom Headphones")
        self.assertEqual(payload["calibrations"][0]["comfortable_volume"], 0.08)
        self.assertEqual(payload["calibrations"][0]["scheduler_max_volume"], 0.08)

    def test_play_test_cue_cli_uses_calibrated_max_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            calibration_path = Path(tmp) / "volume.json"
            save_volume_calibration(
                VolumeCalibration(
                    "Bedroom Headphones",
                    detectable_volume=0.02,
                    identifiable_volume=0.04,
                    comfortable_volume=0.08,
                ),
                calibration_path,
            )

            with redirect_stdout(io.StringIO()) as output:
                exit_code = main([
                    "play-test-cue",
                    "--backend",
                    "dry-run",
                    "--device-name",
                    "Bedroom Headphones",
                    "--calibration",
                    str(calibration_path),
                    "--duration-seconds",
                    "0.01",
                    "--volume",
                    "0.20",
                    "--max-volume",
                    "0.20",
                ])

        self.assertEqual(exit_code, 0)
        self.assertIn("status=played", output.getvalue())
        self.assertIn("volume=0.08", output.getvalue())
        self.assertIn("requested_volume=0.2", output.getvalue())
        self.assertIn("volume_capped=True", output.getvalue())


if __name__ == "__main__":
    unittest.main()
