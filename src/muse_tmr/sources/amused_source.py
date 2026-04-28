"""Adapter around the forked amused-py BLE source."""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Callable, Optional, Sequence

from muse_realtime_decoder import DecodedData
from muse_stream_client import MuseStreamClient

from muse_tmr.data.sample_types import MuseFrame, frame_from_decoded
from muse_tmr.sources.base_source import BaseMuseSource, MuseDeviceInfo, MuseSourceMetadata


class AmusedSource(BaseMuseSource):
    """Stream MuseFrames from the existing `MuseStreamClient` implementation."""

    strategy = "forked-source"

    def __init__(
        self,
        address: Optional[str] = None,
        name_filter: str = "Muse",
        preset: str = "p1034",
        duration_seconds: int = 0,
        stream_client_factory: Callable[..., MuseStreamClient] = MuseStreamClient,
        queue_size: int = 1000,
        verbose: bool = True,
    ) -> None:
        self.address = address
        self.name_filter = name_filter
        self.preset = preset
        self.duration_seconds = duration_seconds
        self.stream_client_factory = stream_client_factory
        self.queue_size = queue_size
        self.verbose = verbose

        self.client: Optional[MuseStreamClient] = None
        self.metadata: Optional[MuseSourceMetadata] = None
        self.packet_count = 0
        self.frame_count = 0
        self.last_packet_monotonic: Optional[float] = None
        self.disconnect_reason: Optional[str] = None

        self._queue: asyncio.Queue[MuseFrame] = asyncio.Queue(maxsize=queue_size)
        self._stream_task: Optional[asyncio.Task] = None
        self._stop_requested = False

    async def discover(self) -> Sequence[MuseDeviceInfo]:
        from muse_discovery import find_muse_devices

        devices = await find_muse_devices()
        if self.name_filter:
            devices = [device for device in devices if self.name_filter in device.name]
        return [
            MuseDeviceInfo(name=device.name, address=device.address, rssi=device.rssi)
            for device in devices
        ]

    async def connect(self, device: Optional[MuseDeviceInfo] = None) -> MuseSourceMetadata:
        self._stop_requested = False
        self.disconnect_reason = None
        self.packet_count = 0
        self.frame_count = 0
        self.last_packet_monotonic = None

        if device is not None:
            self.address = device.address

        if self.address is None:
            devices = await self.discover()
            if not devices:
                raise RuntimeError("No Muse devices found")
            self.address = devices[0].address
            device = devices[0]

        device_name = device.name if device is not None else self.address
        self.client = self.stream_client_factory(
            save_raw=False,
            decode_realtime=True,
            verbose=self.verbose,
        )
        if self.client.decoder:
            self.client.decoder.register_callback("any", self._handle_decoded)
        self.client.on_packet(self._handle_packet)

        self.metadata = MuseSourceMetadata(
            source_name="amused",
            device_name=device_name or "Muse",
            device_id=self.address,
            capabilities={
                "eeg": True,
                "imu": True,
                "ppg": True,
                "heart_rate": True,
                "battery": True,
                "raw_packets": True,
            },
            metadata={"preset": self.preset, "strategy": self.strategy},
        )
        return self.metadata

    async def stream(self) -> AsyncIterator[MuseFrame]:
        if self.client is None:
            await self.connect()

        if self._stream_task is None or self._stream_task.done():
            self._stream_task = asyncio.create_task(self._run_client())

        while not self._stop_requested:
            if self._stream_task.done() and self._queue.empty():
                exc = self._stream_task.exception()
                if exc is not None:
                    raise exc
                break
            try:
                yield await asyncio.wait_for(self._queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue

    async def stop(self) -> None:
        self._stop_requested = True
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        self._stream_task = None

    async def _run_client(self) -> None:
        assert self.client is not None
        assert self.address is not None
        success = await self.client.connect_and_stream(
            self.address,
            duration_seconds=self.duration_seconds,
            preset=self.preset,
        )
        if not success and not self._stop_requested:
            self.disconnect_reason = "stream_failed"
            raise RuntimeError("amused stream failed")

    def _handle_packet(self, raw_packet: bytes) -> None:
        self.packet_count += 1
        self.last_packet_monotonic = time.monotonic()

    def _handle_decoded(self, decoded: DecodedData) -> None:
        frame = frame_from_decoded(decoded, source="amused")
        self.frame_count += 1
        try:
            self._queue.put_nowait(frame)
        except asyncio.QueueFull:
            self.disconnect_reason = "frame_queue_full"
