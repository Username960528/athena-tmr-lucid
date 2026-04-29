"""Base source contract for Muse frame producers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Mapping, Optional, Sequence

from muse_tmr.data.sample_types import MuseFrame


@dataclass(frozen=True)
class MuseDeviceInfo:
    name: str
    address: str
    rssi: int = -100
    metadata: Optional[Mapping[str, str]] = None


@dataclass(frozen=True)
class MuseSourceMetadata:
    source_name: str
    device_name: str
    device_id: str
    capabilities: Mapping[str, bool]
    metadata: Optional[Mapping[str, str]] = None


class BaseMuseSource(ABC):
    @abstractmethod
    async def discover(self) -> Sequence[MuseDeviceInfo]:
        """Discover available devices for this source."""

    @abstractmethod
    async def connect(self, device: Optional[MuseDeviceInfo] = None) -> MuseSourceMetadata:
        """Connect to the source and return device metadata."""

    @abstractmethod
    async def stream(self) -> AsyncIterator[MuseFrame]:
        """Yield Muse frames until stopped."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop streaming and release resources."""
