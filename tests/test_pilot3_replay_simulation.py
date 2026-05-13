import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import muse_athena_protocol as proto
import numpy as np
from muse_raw_stream import MuseRawStream

from muse_tmr.audio import CueLibrary, CueMetadata
from muse_tmr.data.sample_types import EEGSample, HeartRateSample, IMUSample, MuseFrame, PPGSample
from muse_tmr.features import EpochBuilder, EpochConfig
from muse_tmr.models import RemGateConfig
from muse_tmr.protocol import (
    NightPuzzleSession,
    PuzzleCatalog,
    PuzzleCueAssignment,
    PuzzleTask,
    TmrSchedulerConfig,
)
from muse_tmr.validation import simulate_cue_plan_from_epochs, simulate_replay_cue_plan


EEG_RATE_HZ = 256
IMU_RATE_HZ = 52
PPG_RATE_HZ = 64


def sine_values(frequency_hz, *, seconds=30.0, sample_rate_hz=EEG_RATE_HZ, amplitude=10.0):
    timestamps = np.arange(0, seconds, 1 / sample_rate_hz)
    return amplitude * np.sin(2 * np.pi * frequency_hz * timestamps)


def rem_like_eeg_channels():
    theta = sine_values(6.0, amplitude=12.0)
    alpha = sine_values(10.0, amplitude=1.0)
    eye = sine_values(1.0, amplitude=4.5)
    return {
        "TP9": (theta + alpha).tolist(),
        "AF7": (theta + alpha + eye).tolist(),
        "AF8": (theta + alpha - eye).tolist(),
        "TP10": (theta + alpha).tolist(),
    }


def synthetic_ppg(heart_rate_bpm, *, seconds=30.0):
    timestamps = np.arange(0, seconds, 1 / PPG_RATE_HZ)
    heart_hz = heart_rate_bpm / 60.0
    pulse = np.sin(2 * np.pi * heart_hz * timestamps)
    harmonic = 0.25 * np.sin(4 * np.pi * heart_hz * timestamps - np.pi / 4)
    return (50000.0 + 1000.0 * (pulse + harmonic)).tolist()


def still_accel_rows():
    return [{"x": 0.0, "y": 0.0, "z": 1.0}] * (30 * IMU_RATE_HZ)


def still_gyro_rows():
    return [{"x": 0.0, "y": 0.0, "z": 0.0}] * (30 * IMU_RATE_HZ)


def build_rem_epoch(index):
    timestamp = 1000.0 + index * 30.0
    frames = [
        MuseFrame(
            timestamp=timestamp,
            eeg=EEGSample(timestamp, rem_like_eeg_channels(), source="test"),
            imu=IMUSample(
                timestamp,
                accelerometer_g=still_accel_rows(),
                gyroscope_dps=still_gyro_rows(),
                source="test",
            ),
            ppg=PPGSample(timestamp, {"LO_NIR": synthetic_ppg(72.0)}, source="test"),
            source="test",
        )
    ]
    for sample_index in range(30):
        frames.append(
            MuseFrame(
                timestamp=timestamp + sample_index,
                heart_rate=HeartRateSample(
                    timestamp + sample_index,
                    bpm=68.0 + (sample_index % 5),
                    source="test",
                ),
                source="test",
            )
        )
    return EpochBuilder(EpochConfig(epoch_seconds=30, stride_seconds=30))._build_epoch(
        index,
        timestamp,
        tuple(frames),
    )


def protocol_fixture():
    catalog = PuzzleCatalog(
        puzzles=(
            PuzzleTask("p1", "one", "one", cue_id="cue-p1"),
            PuzzleTask("p2", "two", "two", cue_id="cue-p2"),
            PuzzleTask("p3", "three", "three", cue_id="cue-p3"),
            PuzzleTask("p4", "four", "four", cue_id="cue-p4"),
        )
    )
    session = NightPuzzleSession(
        session_id="night-001",
        puzzle_ids=("p1", "p2", "p3", "p4"),
        puzzle_count=4,
    )
    assignment = PuzzleCueAssignment(
        session_id="night-001",
        cued_puzzle_ids=("p1", "p3"),
        uncued_puzzle_ids=("p2", "p4"),
        seed=17,
    )
    cue_library = CueLibrary(
        library_id="pilot3-test",
        cues=(
            CueMetadata("cue-p1", "generated_tone", 1.0, protocol="puzzle", frequency_hz=440.0),
            CueMetadata("cue-p3", "generated_tone", 1.0, protocol="puzzle", frequency_hz=660.0),
        ),
    )
    return catalog, session, assignment, cue_library


def build_tag_packet(first_tag, first_data):
    header = bytearray(14)
    header[9] = first_tag
    return bytes(header) + first_data


def write_synthetic_recording(recording_dir: Path) -> Path:
    recording_dir.mkdir(parents=True, exist_ok=True)
    raw_path = recording_dir / "raw_amused.bin"
    stream = MuseRawStream(str(raw_path))
    stream.open_write()
    base_time = stream.session_start
    stream.write_packet(build_tag_packet(proto.TAG_EEG_4CH, bytes(28)), base_time)
    stream.write_packet(
        build_tag_packet(proto.TAG_ACCGYRO, bytes(36)),
        base_time + dt.timedelta(seconds=10),
    )
    stream.write_packet(
        build_tag_packet(proto.TAG_OPTICS_8CH, bytes(60)),
        base_time + dt.timedelta(seconds=40),
    )
    stream.close()
    return raw_path


class TestPilot3ReplaySimulation(unittest.TestCase):
    def test_replay_cue_plan_uses_mock_audio_and_only_cued_puzzles(self):
        catalog, session, assignment, cue_library = protocol_fixture()
        report = simulate_cue_plan_from_epochs(
            [build_rem_epoch(index) for index in range(4)],
            catalog=catalog,
            session=session,
            assignment=assignment,
            cue_library=cue_library,
            recording_input="synthetic-replay",
            gate_config=RemGateConfig(
                enter_threshold=0.60,
                exit_threshold=0.45,
                min_stable_seconds=60.0,
                epoch_seconds=30.0,
                cooldown_seconds=0.0,
            ),
            scheduler_config=TmrSchedulerConfig(
                puzzle_cue_interval_seconds=30.0,
                cooldown_seconds=30.0,
                max_puzzle_cues_per_block=4,
                enable_tlr_block=False,
            ),
        )

        self.assertTrue(report.passed)
        self.assertFalse(report.audio_playback_executed)
        self.assertEqual(report.audio_backend, "mock")
        self.assertEqual(report.metrics["uncued_puzzle_play_count"], 0)
        self.assertEqual([event.puzzle_id for event in report.cue_plan], ["p1", "p3"])
        self.assertGreaterEqual(report.metrics["scheduler_event_count"], 4)

    def test_report_and_scheduler_events_are_inspectable_files(self):
        catalog, session, assignment, cue_library = protocol_fixture()
        report = simulate_cue_plan_from_epochs(
            [build_rem_epoch(0), build_rem_epoch(1)],
            catalog=catalog,
            session=session,
            assignment=assignment,
            cue_library=cue_library,
            gate_config=RemGateConfig(
                enter_threshold=0.60,
                exit_threshold=0.45,
                min_stable_seconds=60.0,
                epoch_seconds=30.0,
                cooldown_seconds=0.0,
            ),
            scheduler_config=TmrSchedulerConfig(enable_tlr_block=False),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = report.save(Path(tmpdir) / "pilot3_report.json")
            events_path = report.save_scheduler_events(Path(tmpdir) / "events.jsonl")

            saved = json.loads(report_path.read_text(encoding="utf-8"))
            event_lines = events_path.read_text(encoding="utf-8").splitlines()

        self.assertTrue(saved["passed"])
        self.assertEqual(saved["audio_backend"], "mock")
        self.assertFalse(saved["audio_playback_executed"])
        self.assertGreaterEqual(len(saved["scheduler_events"]), 2)
        self.assertGreaterEqual(len(event_lines), 2)

    def test_empty_replay_epochs_fail_without_calling_audio(self):
        catalog, session, assignment, cue_library = protocol_fixture()
        report = simulate_cue_plan_from_epochs(
            [],
            catalog=catalog,
            session=session,
            assignment=assignment,
            cue_library=cue_library,
        )

        self.assertFalse(report.passed)
        self.assertIn("epochs_present", report.failed_criteria)
        self.assertFalse(report.audio_playback_executed)


class TestPilot3ReplayPipeline(unittest.IsolatedAsyncioTestCase):
    async def test_replay_recording_generates_mocked_plan_report(self):
        catalog, session, assignment, cue_library = protocol_fixture()
        with tempfile.TemporaryDirectory() as tmpdir:
            recording_dir = Path(tmpdir) / "recording"
            write_synthetic_recording(recording_dir)

            report = await simulate_replay_cue_plan(
                recording_dir,
                catalog=catalog,
                session=session,
                assignment=assignment,
                cue_library=cue_library,
                scheduler_config=TmrSchedulerConfig(enable_tlr_block=False),
            )

        self.assertTrue(report.passed)
        self.assertGreater(report.metrics["epoch_count"], 0)
        self.assertGreater(report.metrics["scheduler_event_count"], 0)
        self.assertFalse(report.audio_playback_executed)


if __name__ == "__main__":
    unittest.main()
