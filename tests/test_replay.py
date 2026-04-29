import asyncio
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import muse_athena_protocol as proto
from muse_raw_stream import MuseRawStream
from muse_tmr.data.replay import ReplayConfig, ReplaySession, resolve_raw_path


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

    metadata = {
        "source": {
            "source_name": "amused",
            "device_name": "Muse Test",
            "device_id": "test-device",
            "capabilities": {
                "eeg": True,
                "imu": True,
                "ppg": True,
                "heart_rate": True,
                "raw_packets": True,
            },
        }
    }
    (recording_dir / "metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    return raw_path


class TestReplaySession(unittest.IsolatedAsyncioTestCase):
    async def test_replay_yields_muse_frames_from_recording_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            write_synthetic_recording(recording_dir)
            session = ReplaySession(ReplayConfig(input_path=recording_dir, speed=0.0))

            metadata = await session.connect()
            frames = [frame async for frame in session.stream()]

            self.assertEqual(metadata.source_name, "replay")
            self.assertEqual(metadata.device_name, "Muse Test")
            self.assertEqual(len(frames), 3)
            self.assertIn("eeg", frames[0].modalities())
            self.assertIn("imu", frames[1].modalities())
            self.assertIn("ppg", frames[2].modalities())
            self.assertIsNotNone(frames[0].raw_packet)

    async def test_replay_filters_relative_time_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            write_synthetic_recording(recording_dir)
            session = ReplaySession(
                ReplayConfig(
                    input_path=recording_dir,
                    speed=0.0,
                    start_seconds=5,
                    end_seconds=20,
                )
            )

            frames = [frame async for frame in session.stream()]

            self.assertEqual(len(frames), 1)
            self.assertEqual(frames[0].modalities(), ("imu",))

    async def test_replay_can_feed_downstream_collectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            write_synthetic_recording(recording_dir)
            session = ReplaySession(ReplayConfig(input_path=recording_dir, speed=0.0))

            modality_counts = {}
            async for frame in session.stream():
                for modality in frame.modalities():
                    modality_counts[modality] = modality_counts.get(modality, 0) + 1

            self.assertEqual(modality_counts["eeg"], 1)
            self.assertEqual(modality_counts["imu"], 1)
            self.assertEqual(modality_counts["ppg"], 1)

    async def test_replay_speed_sleeps_between_packets(self):
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            write_synthetic_recording(recording_dir)
            session = ReplaySession(
                ReplayConfig(
                    input_path=recording_dir,
                    speed=1000.0,
                    end_seconds=12,
                )
            )

            started = asyncio.get_running_loop().time()
            frames = [frame async for frame in session.stream()]
            elapsed = asyncio.get_running_loop().time() - started

            self.assertEqual(len(frames), 2)
            self.assertGreaterEqual(elapsed, 0.005)
            self.assertLess(elapsed, 0.5)


class TestReplayHelpers(unittest.TestCase):
    def test_resolve_raw_path_accepts_directory_or_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            raw_path = write_synthetic_recording(recording_dir)

            self.assertEqual(resolve_raw_path(recording_dir), raw_path.resolve())
            self.assertEqual(resolve_raw_path(raw_path), raw_path.resolve())

    def test_config_rejects_invalid_time_range(self):
        with self.assertRaises(ValueError):
            ReplayConfig(
                input_path=Path("raw_amused.bin"),
                start_seconds=30,
                end_seconds=10,
            ).validate()


if __name__ == "__main__":
    unittest.main()
