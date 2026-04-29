# Unified Muse Data Model

`muse_tmr.data.sample_types` defines the common frame format used by live sources, recorders, replay, feature extraction, and future REM detection.

## Units

- `MuseFrame.timestamp`: Unix epoch seconds as a float.
- `EEGSample.channels_uv`: microvolts per channel. Values are stored as sample arrays, even when a packet contains a single sample.
- `IMUSample.accelerometer_g`: acceleration in g, keyed by `x`, `y`, and `z`.
- `IMUSample.gyroscope_dps`: angular velocity in degrees per second, keyed by `x`, `y`, and `z`.
- `PPGSample.channels`: raw optics values from the Muse protocol decoder.
- `HeartRateSample.bpm`: beats per minute.
- `BatterySample.percent`: battery percentage.
- `MuseFrame.raw_packet`: optional raw BLE packet bytes, serialized as `raw_packet_hex`.

Missing modalities are valid. A frame may contain only EEG, only IMU, only PPG, or any combination available from a packet.

## Serialization

Each sample type supports `to_dict()` and `from_dict()`. `MuseFrame` additionally supports `to_json()` and `from_json()`. Raw bytes are encoded as hex so frame JSON remains portable.

## Source Attribution

Every sample and frame carries a `source` string. The amused-py adapter uses `amused`; future OpenMuse and SDK adapters should use distinct source names.

## Offline Replay

`muse_tmr.data.replay.ReplaySession` reads a recording directory or `raw_amused.bin`,
decodes raw packets through the same TAG decoder used by live streaming, and emits
`MuseFrame` objects for downstream epoch building and feature extraction.

Replay speed is explicit:

- `speed=1.0` preserves real-time packet spacing.
- `speed>1.0` accelerates replay.
- `speed=0.0` disables sleeps for tests and batch processing.

`start_seconds` and `end_seconds` are relative to the raw recording start, allowing
feature code to replay a specific sleep segment without loading unrelated packets.
