import unittest
from unittest.mock import patch

from muse_tmr.sources.openmuse_lsl_source import (
    OpenMuseLslConfig,
    OpenMuseLslDependencyError,
    OpenMuseLslSource,
    _channel_labels,
    _load_lsl_backend,
    _MneLslBackend,
    _PylslBackend,
)


class FakeStreamInfo:
    def __init__(self, name, channel_count, stream_type="Muse", source_id=None):
        self._name = name
        self._channel_count = channel_count
        self._type = stream_type
        self._source_id = source_id or f"{name}-uid"

    def name(self):
        return self._name

    def channel_count(self):
        return self._channel_count

    def type(self):
        return self._type

    def source_id(self):
        return self._source_id


class FakeInlet:
    def __init__(self, samples):
        self.samples = list(samples)
        self.closed = False
        self.opened = False

    def open_stream(self, timeout=0.0):
        self.opened = True

    def pull_sample(self, timeout=0.0):
        if not self.samples:
            return None, None
        return self.samples.pop(0)

    def time_correction(self, timeout=0.0):
        return 0.0

    def close_stream(self):
        self.closed = True


class FakeLslBackend:
    name = "fake-lsl"

    def __init__(self, infos, inlets):
        self.infos = tuple(infos)
        self.inlets = dict(inlets)

    def resolve_streams(self, timeout_seconds):
        return self.infos

    def resolve_by_name(self, name, timeout_seconds):
        return tuple(info for info in self.infos if info.name() == name)

    def stream_inlet(self, info, *, max_buffer_seconds):
        return self.inlets[info.name()]

    def local_clock(self):
        return 10.0


class TestOpenMuseLslSource(unittest.IsolatedAsyncioTestCase):
    async def test_import_and_instantiation_do_not_require_lsl_dependency(self):
        source = OpenMuseLslSource()

        self.assertEqual(source.source_name, "openmuse")
        self.assertEqual(source.strategy, "optional-lsl")

    async def test_discover_lists_openmuse_streams(self):
        backend = FakeLslBackend(
            infos=(
                FakeStreamInfo("Muse_EEG", 4),
                FakeStreamInfo("Unrelated", 1),
            ),
            inlets={},
        )
        source = OpenMuseLslSource(lsl_backend=backend)

        devices = await source.discover()

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].name, "Muse_EEG")
        self.assertEqual(devices[0].metadata["modality"], "eeg")

    async def test_connect_and_stream_yields_eeg_and_imu_frames(self):
        eeg_info = FakeStreamInfo("Muse_EEG", 4)
        imu_info = FakeStreamInfo("Muse_ACCGYRO", 6)
        eeg_inlet = FakeInlet([([1.0, 2.0, 3.0, 4.0], 12.0)])
        imu_inlet = FakeInlet([([0.1, 0.2, 0.3, 1.1, 1.2, 1.3], 13.0)])
        backend = FakeLslBackend(
            infos=(eeg_info, imu_info),
            inlets={"Muse_EEG": eeg_inlet, "Muse_ACCGYRO": imu_inlet},
        )
        source = OpenMuseLslSource(
            OpenMuseLslConfig(required_modalities=("eeg", "imu")),
            lsl_backend=backend,
        )

        metadata = await source.connect()
        stream = source.stream().__aiter__()
        eeg_frame = await stream.__anext__()
        imu_frame = await stream.__anext__()
        await source.stop()

        self.assertEqual(metadata.source_name, "openmuse")
        self.assertTrue(metadata.capabilities["eeg"])
        self.assertTrue(metadata.capabilities["imu"])
        self.assertFalse(metadata.capabilities["raw_packets"])
        self.assertGreater(eeg_frame.timestamp, 1_000_000_000)
        self.assertEqual(eeg_frame.source, "openmuse")
        self.assertEqual(eeg_frame.eeg.channels_uv["TP9"], (1.0,))
        self.assertEqual(eeg_frame.eeg.channels_uv["TP10"], (4.0,))
        self.assertEqual(imu_frame.imu.accelerometer_g[0]["x"], 0.1)
        self.assertEqual(imu_frame.imu.gyroscope_dps[0]["z"], 1.3)
        self.assertTrue(eeg_inlet.closed)
        self.assertTrue(imu_inlet.closed)

    async def test_missing_required_stream_fails_connect(self):
        backend = FakeLslBackend(
            infos=(FakeStreamInfo("Muse_EEG", 4),),
            inlets={"Muse_EEG": FakeInlet([])},
        )
        source = OpenMuseLslSource(
            OpenMuseLslConfig(required_modalities=("eeg", "imu")),
            lsl_backend=backend,
        )

        with self.assertRaises(RuntimeError):
            await source.connect()

    async def test_connect_fails_with_actionable_error_when_no_streams_found(self):
        backend = FakeLslBackend(infos=(), inlets={})
        source = OpenMuseLslSource(lsl_backend=backend)

        with self.assertRaisesRegex(RuntimeError, "No OpenMuse LSL streams found"):
            await source.connect()

    async def test_resolve_falls_back_to_lookup_by_configured_stream_names(self):
        eeg_info = FakeStreamInfo("Muse_EEG", 4)

        class ByNameOnlyBackend(FakeLslBackend):
            def resolve_streams(self, timeout_seconds):
                return ()

        backend = ByNameOnlyBackend(
            infos=(eeg_info,),
            inlets={"Muse_EEG": FakeInlet([([1.0, 2.0, 3.0, 4.0], 12.0)])},
        )
        source = OpenMuseLslSource(lsl_backend=backend)

        metadata = await source.connect()

        self.assertTrue(metadata.capabilities["eeg"])
        self.assertFalse(metadata.capabilities["imu"])

    async def test_stream_maps_ppg_heart_rate_and_battery_modalities(self):
        infos = (
            FakeStreamInfo("Muse_PPG", 3),
            FakeStreamInfo("Muse_HR", 1),
            FakeStreamInfo("Muse_BATT", 1),
        )
        inlets = {
            "Muse_PPG": FakeInlet([([10.0, 20.0, 30.0], 12.0)]),
            "Muse_HR": FakeInlet([([62.0], 12.1)]),
            "Muse_BATT": FakeInlet([([88.0], 12.2)]),
        }
        backend = FakeLslBackend(infos=infos, inlets=inlets)
        source = OpenMuseLslSource(lsl_backend=backend)

        await source.connect()
        frames = {}
        async for frame in source.stream():
            frames[frame.modalities()[0]] = frame
            if len(frames) == 3:
                await source.stop()

        self.assertEqual(frames["ppg"].ppg.channels["PPG0"], (10.0,))
        self.assertEqual(frames["heart_rate"].heart_rate.bpm, 62.0)
        self.assertEqual(frames["battery"].battery.percent, 88.0)

    async def test_stream_auto_connects_and_respects_duration_deadline(self):
        backend = FakeLslBackend(
            infos=(FakeStreamInfo("Muse_EEG", 4),),
            inlets={"Muse_EEG": FakeInlet([([1.0, 2.0, 3.0, 4.0], 12.0)])},
        )
        source = OpenMuseLslSource(
            OpenMuseLslConfig(duration_seconds=0.05, poll_interval_seconds=0.01),
            lsl_backend=backend,
        )

        frames = [frame async for frame in source.stream()]

        self.assertEqual(len(frames), 1)
        self.assertIsNotNone(source.metadata)

    async def test_channel_labels_extend_fallback_when_stream_has_more_channels(self):
        backend = FakeLslBackend(
            infos=(FakeStreamInfo("Muse_EEG", 7),),
            inlets={
                "Muse_EEG": FakeInlet(
                    [([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0], 12.0)]
                )
            },
        )
        source = OpenMuseLslSource(lsl_backend=backend)

        await source.connect()
        stream = source.stream().__aiter__()
        frame = await stream.__anext__()
        await source.stop()

        self.assertIn("TP9", frame.eeg.channels_uv)
        self.assertIn("CH5", frame.eeg.channels_uv)
        self.assertIn("CH6", frame.eeg.channels_uv)

    async def test_pre_epoch_lsl_timestamps_fall_back_to_wall_clock(self):
        class NoClockBackend(FakeLslBackend):
            local_clock = None

        backend = NoClockBackend(
            infos=(FakeStreamInfo("Muse_EEG", 4),),
            inlets={"Muse_EEG": FakeInlet([([1.0, 2.0, 3.0, 4.0], 12.0)])},
        )
        source = OpenMuseLslSource(lsl_backend=backend)

        await source.connect()
        stream = source.stream().__aiter__()
        frame = await stream.__anext__()
        await source.stop()

        self.assertGreater(frame.timestamp, 1_000_000_000)


class TestOpenMuseLslConfigValidation(unittest.TestCase):
    def test_config_rejects_invalid_values(self):
        invalid_kwargs = (
            {"resolve_timeout_seconds": -1.0},
            {"pull_timeout_seconds": -1.0},
            {"poll_interval_seconds": 0.0},
            {"max_buffer_seconds": 0},
            {"duration_seconds": -1.0},
            {"required_modalities": ("eeg", "telepathy")},
        )
        for kwargs in invalid_kwargs:
            with self.assertRaises(ValueError):
                OpenMuseLslConfig(**kwargs)


class _KwargOnlyModule:
    """Fake LSL module whose functions accept keyword timeout arguments."""

    def __init__(self, infos):
        self.infos = tuple(infos)
        self.inlet_kwargs = None

    def resolve_streams(self, timeout=None):
        return self.infos

    def StreamInlet(self, info, **kwargs):
        self.inlet_kwargs = kwargs
        return FakeInlet([])

    def local_clock(self):
        return 10.0


class _PositionalOnlyModule:
    """Fake LSL module that rejects keyword arguments (older API style)."""

    def __init__(self, infos):
        self.infos = tuple(infos)
        self.positional_calls = []

    def resolve_streams(self, timeout_seconds):
        self.positional_calls.append(("resolve_streams", timeout_seconds))
        return self.infos

    def resolve_stream(self, prop, value, timeout_seconds):
        self.positional_calls.append(("resolve_stream", prop, value))
        return tuple(info for info in self.infos if info.name() == value)

    def StreamInlet(self, info):
        return FakeInlet([])

    def local_clock(self):
        return 10.0


class TestLslBackendWrappers(unittest.TestCase):
    def test_mne_lsl_backend_falls_back_to_positional_timeout(self):
        module = _PositionalOnlyModule((FakeStreamInfo("Muse_EEG", 4),))
        backend = _MneLslBackend(module)

        infos = backend.resolve_streams(1.0)
        by_name = backend.resolve_by_name("Muse_EEG", 1.0)
        inlet = backend.stream_inlet(infos[0], max_buffer_seconds=30)

        self.assertEqual(len(infos), 1)
        self.assertEqual(len(by_name), 1)
        self.assertIsInstance(inlet, FakeInlet)
        self.assertEqual(backend.local_clock(), 10.0)

    def test_mne_lsl_backend_supports_keyword_timeout(self):
        module = _KwargOnlyModule((FakeStreamInfo("Muse_EEG", 4),))
        backend = _MneLslBackend(module)

        infos = backend.resolve_streams(1.0)
        backend.stream_inlet(infos[0], max_buffer_seconds=30)

        self.assertEqual(len(infos), 1)
        self.assertEqual(module.inlet_kwargs, {"max_buffered": 30})

    def test_pylsl_backend_resolves_streams_and_by_name(self):
        module = _PositionalOnlyModule((FakeStreamInfo("Muse_EEG", 4),))
        backend = _PylslBackend(module)

        infos = backend.resolve_streams(1.0)
        by_name = backend.resolve_by_name("Muse_EEG", 1.0)
        inlet = backend.stream_inlet(infos[0], max_buffer_seconds=30)

        self.assertEqual(len(infos), 1)
        self.assertEqual(len(by_name), 1)
        self.assertIsInstance(inlet, FakeInlet)
        self.assertEqual(backend.local_clock(), 10.0)

    def test_pylsl_backend_returns_empty_when_resolvers_missing(self):
        class EmptyModule:
            pass

        backend = _PylslBackend(EmptyModule())

        self.assertEqual(backend.resolve_streams(1.0), ())
        self.assertEqual(backend.resolve_by_name("Muse_EEG", 1.0), ())


class _FakeXmlNode:
    def __init__(self, children=(), values=None):
        self._children = list(children)
        self._values = values or {}

    def child(self, name):
        for child_name, node in self._children:
            if child_name == name:
                return node
        return _FakeXmlNode()

    def child_value(self, name):
        return self._values.get(name, "")

    def empty(self):
        return not self._children and not self._values

    def next_sibling(self):
        return self._sibling if hasattr(self, "_sibling") else _FakeXmlNode()


class TestChannelLabelMetadata(unittest.TestCase):
    def test_labels_are_read_from_stream_xml_description(self):
        tp9 = _FakeXmlNode(values={"label": "TP9"})
        af7 = _FakeXmlNode(values={"label": "AF7"})
        tp9._sibling = af7
        af7._sibling = _FakeXmlNode()
        channels = _FakeXmlNode(children=[("channel", tp9)])
        root = _FakeXmlNode(children=[("channels", channels)])

        class InfoWithDesc(FakeStreamInfo):
            def desc(self):
                return root

        labels = _channel_labels(InfoWithDesc("Muse_EEG", 2), ("FALLBACK",))

        self.assertEqual(labels, ("TP9", "AF7"))

    def test_labels_fall_back_to_defaults_when_metadata_is_missing(self):
        labels = _channel_labels(
            FakeStreamInfo("Muse_EEG", 2),
            ("TP9", "AF7", "AF8", "TP10"),
        )

        self.assertEqual(labels, ("TP9", "AF7"))


class TestLslBackendLoading(unittest.TestCase):
    def test_missing_optional_dependencies_raise_actionable_error(self):
        with patch(
            "muse_tmr.sources.openmuse_lsl_source.importlib.import_module",
            side_effect=ImportError("no lsl"),
        ):
            with self.assertRaisesRegex(OpenMuseLslDependencyError, "mne_lsl"):
                _load_lsl_backend()


if __name__ == "__main__":
    unittest.main()
